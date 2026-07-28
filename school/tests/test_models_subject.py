from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from school.models import (
    Course, ScoreConversionTable, StudentProfile, StudentSubjectGoal, Subject,
)
from school.services.analytics import convert_to_test_score


class SubjectTests(TestCase):
    def test_course_works_without_subject_ref(self):
        """Legacy-поле продолжает работать (ТЗ п.14)."""
        c = Course.objects.create(title='Русский язык ЕГЭ', subject='Русский язык')
        self.assertIsNone(c.subject_ref)
        self.assertEqual(c.subject, 'Русский язык')

    def test_course_can_link_subject(self):
        s = Subject.objects.create(code='russian', name='Русский язык')
        c = Course.objects.create(title='ЕГЭ', subject='Русский язык', subject_ref=s)
        self.assertEqual(s.courses.count(), 1)

    def test_deleting_subject_keeps_course(self):
        s = Subject.objects.create(code='math', name='Математика')
        c = Course.objects.create(title='ЕГЭ математика', subject_ref=s)
        s.delete()
        c.refresh_from_db()
        self.assertIsNone(c.subject_ref)


class StudentProfileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='s1', password='x')
        cls.profile = StudentProfile.objects.create(user=cls.user, exam_year=2027)
        cls.russian = Subject.objects.create(code='russian', name='Русский язык')
        cls.math = Subject.objects.create(code='math', name='Математика')

    def test_defaults(self):
        self.assertFalse(self.profile.onboarding_completed)
        self.assertEqual(self.profile.timezone, 'Europe/Moscow')
        self.assertEqual(self.profile.available_days_per_week, 5)

    def test_multiple_goals_for_different_subjects(self):
        StudentSubjectGoal.objects.create(
            student=self.profile, subject=self.russian,
            target_test_score=85, exam_year=2027,
        )
        StudentSubjectGoal.objects.create(
            student=self.profile, subject=self.math,
            target_test_score=70, exam_year=2027,
        )
        self.assertEqual(self.profile.goals.count(), 2)

    def test_duplicate_goal_rejected(self):
        StudentSubjectGoal.objects.create(
            student=self.profile, subject=self.russian,
            target_test_score=85, exam_year=2027,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StudentSubjectGoal.objects.create(
                    student=self.profile, subject=self.russian,
                    target_test_score=90, exam_year=2027,
                )

    def test_same_subject_different_year_allowed(self):
        StudentSubjectGoal.objects.create(
            student=self.profile, subject=self.russian,
            target_test_score=85, exam_year=2027,
        )
        StudentSubjectGoal.objects.create(
            student=self.profile, subject=self.russian,
            target_test_score=95, exam_year=2028,
        )
        self.assertEqual(self.profile.goals.count(), 2)

    def test_target_score_above_100_invalid(self):
        goal = StudentSubjectGoal(
            student=self.profile, subject=self.math,
            target_test_score=120, exam_year=2027,
        )
        with self.assertRaises(ValidationError):
            goal.full_clean()


class ConversionTableValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.subject = Subject.objects.create(code='russian', name='Русский язык')

    def make(self, table, is_active=False, version=1, year=2027):
        return ScoreConversionTable(
            subject=self.subject, exam_type='ege', exam_year=year,
            version=version, is_active=is_active,
            valid_from=date(2026, 9, 1), table=table,
        )

    def test_valid_table_passes(self):
        self.make({'0': 0, '10': 33, '20': 57, '30': 78}).full_clean()

    def test_non_integer_key_rejected(self):
        with self.assertRaises(ValidationError):
            self.make({'десять': 30}).full_clean()

    def test_score_above_100_rejected(self):
        with self.assertRaises(ValidationError):
            self.make({'0': 0, '10': 140}).full_clean()

    def test_negative_primary_score_rejected(self):
        with self.assertRaises(ValidationError):
            self.make({'-5': 10}).full_clean()

    def test_decreasing_scale_rejected(self):
        with self.assertRaises(ValidationError):
            self.make({'0': 0, '10': 50, '20': 40}).full_clean()

    def test_empty_table_cannot_be_active(self):
        with self.assertRaises(ValidationError):
            self.make({}, is_active=True).full_clean()

    def test_empty_table_allowed_when_inactive(self):
        self.make({}, is_active=False).full_clean()


class ConversionTableSelectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.russian = Subject.objects.create(code='russian', name='Русский язык')
        cls.math = Subject.objects.create(code='math', name='Математика')
        cls.t2027 = ScoreConversionTable.objects.create(
            subject=cls.russian, exam_type='ege', exam_year=2027, version=1,
            is_active=True, valid_from=date(2026, 9, 1),
            table={'0': 0, '20': 55, '40': 95},
        )
        cls.t2028 = ScoreConversionTable.objects.create(
            subject=cls.russian, exam_type='ege', exam_year=2028, version=1,
            is_active=True, valid_from=date(2027, 9, 1),
            table={'0': 0, '20': 60, '40': 97},
        )

    def test_selects_by_subject_and_year(self):
        found = ScoreConversionTable.get_active(self.russian, 'ege', 2027)
        self.assertEqual(found, self.t2027)

    def test_year_change_gives_different_scale(self):
        """ТЗ 25: смена экзаменационного года."""
        a = ScoreConversionTable.get_active(self.russian, 'ege', 2027).as_mapping()
        b = ScoreConversionTable.get_active(self.russian, 'ege', 2028).as_mapping()
        self.assertNotEqual(
            convert_to_test_score(20, a), convert_to_test_score(20, b)
        )

    def test_missing_table_returns_none(self):
        self.assertIsNone(ScoreConversionTable.get_active(self.math, 'ege', 2027))

    def test_inactive_table_not_selected(self):
        ScoreConversionTable.objects.create(
            subject=self.math, exam_type='oge', exam_year=2027, version=1,
            is_active=False, valid_from=date(2026, 9, 1), table={'0': 0, '10': 30},
        )
        self.assertIsNone(ScoreConversionTable.get_active(self.math, 'oge', 2027))

    def test_two_active_tables_rejected_by_db(self):
        """Защита на уровне БД, а не только формы."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ScoreConversionTable.objects.create(
                    subject=self.russian, exam_type='ege', exam_year=2027, version=2,
                    is_active=True, valid_from=date(2026, 10, 1),
                    table={'0': 0, '20': 56},
                )

    def test_second_inactive_version_allowed(self):
        ScoreConversionTable.objects.create(
            subject=self.russian, exam_type='ege', exam_year=2027, version=2,
            is_active=False, valid_from=date(2026, 10, 1),
            table={'0': 0, '20': 56},
        )
        self.assertEqual(
            ScoreConversionTable.objects.filter(
                subject=self.russian, exam_year=2027
            ).count(), 2
        )

    def test_as_mapping_normalizes_string_keys(self):
        mapping = self.t2027.as_mapping()
        self.assertEqual(mapping[20], 55)
        self.assertIsInstance(list(mapping)[0], int)

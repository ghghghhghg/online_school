from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from school.migrations import (  # noqa: F401  — проверяем, что модуль импортируется
    __name__ as _migrations_pkg,
)
from school.models import (
    Answer, Course, Lesson, Question, Review, Subject, TeacherProfile, Test,
    TestAnswerLog, TestResult,
)

# Функции миграций импортируем напрямую по имени модуля
import importlib


def load_migration(name):
    return importlib.import_module(f'school.migrations.{name}')


class SubjectBackfillTests(TestCase):
    """Ветвь: строковый subject -> нормализованный Subject."""

    def setUp(self):
        self.mod = load_migration('0044_backfill_subjects')

    def _apps(self):
        from django.apps import apps as global_apps
        return global_apps

    def test_creates_subjects_from_courses(self):
        Course.objects.create(title='ЕГЭ русский', subject='Русский язык')
        Course.objects.create(title='ОГЭ русский', subject='Русский язык')
        Course.objects.create(title='ЕГЭ математика', subject='Математика')

        self.mod.create_subjects(self._apps(), None)

        self.assertEqual(Subject.objects.count(), 2)
        self.assertTrue(Subject.objects.filter(name='Русский язык').exists())

    def test_links_courses_to_subject(self):
        c = Course.objects.create(title='ЕГЭ русский', subject='Русский язык')
        self.mod.create_subjects(self._apps(), None)
        c.refresh_from_db()
        self.assertEqual(c.subject_ref.name, 'Русский язык')

    def test_transliterated_code(self):
        Course.objects.create(title='ЕГЭ', subject='Русский язык')
        self.mod.create_subjects(self._apps(), None)
        code = Subject.objects.get(name='Русский язык').code
        self.assertTrue(code.isascii())
        self.assertTrue(code)

    def test_idempotent(self):
        Course.objects.create(title='ЕГЭ', subject='Русский язык')
        self.mod.create_subjects(self._apps(), None)
        self.mod.create_subjects(self._apps(), None)
        self.assertEqual(Subject.objects.count(), 1)

    def test_empty_subject_ignored(self):
        Course.objects.create(title='Без предмета', subject='')
        self.mod.create_subjects(self._apps(), None)
        self.assertEqual(Subject.objects.count(), 0)

    def test_collects_from_reviews_and_teachers(self):
        Review.objects.create(student_name='Аня', text='Хорошо', subject='Литература')
        self.mod.create_subjects(self._apps(), None)
        self.assertTrue(Subject.objects.filter(name='Литература').exists())


class TestResultBackfillTests(TestCase):
    """Ветви A / B / C восстановления первичных баллов."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='s1', password='x')
        cls.course = Course.objects.create(title='ЕГЭ русский')
        cls.lesson = Lesson.objects.create(course=cls.course, title='Тема', order=1)
        cls.test = Test.objects.create(lesson=cls.lesson, title='Тест', pass_score=70)

    def setUp(self):
        self.mod = load_migration('0045_backfill_primary_scores')

    def _apps(self):
        from django.apps import apps as global_apps
        return global_apps

    def _question(self, points=1, order=1):
        return Question.objects.create(
            test=self.test, text=f'Вопрос {order}', order=order, points=points
        )

    def test_branch_a_reconstructed_from_logs(self):
        q1 = self._question(points=1, order=1)
        q2 = self._question(points=3, order=2)
        result = TestResult.objects.create(
            student=self.user, test=self.test, score=25, passed=False
        )
        TestAnswerLog.objects.create(result=result, question=q1, is_correct=True)
        TestAnswerLog.objects.create(result=result, question=q2, is_correct=False)

        self.mod.backfill_test_results(self._apps(), None)
        result.refresh_from_db()

        self.assertEqual(result.earned_points, Decimal('1.00'))
        self.assertEqual(result.max_points, Decimal('4.00'))
        self.assertEqual(result.analytics_data_quality, 'reconstructed')

    def test_branch_a_respects_question_points(self):
        """Баллы берутся из Question.points, а не из числа вопросов."""
        q1 = self._question(points=5, order=1)
        result = TestResult.objects.create(
            student=self.user, test=self.test, score=100, passed=True
        )
        TestAnswerLog.objects.create(result=result, question=q1, is_correct=True)

        self.mod.backfill_test_results(self._apps(), None)
        result.refresh_from_db()
        self.assertEqual(result.max_points, Decimal('5.00'))

    def test_branch_b_estimated_from_percent(self):
        self._question(points=1, order=1)
        self._question(points=1, order=2)
        self._question(points=1, order=3)
        self._question(points=1, order=4)
        result = TestResult.objects.create(
            student=self.user, test=self.test, score=75, passed=True
        )

        self.mod.backfill_test_results(self._apps(), None)
        result.refresh_from_db()

        self.assertEqual(result.max_points, Decimal('4.00'))
        self.assertEqual(result.earned_points, Decimal('3.00'))
        self.assertEqual(result.analytics_data_quality, 'estimated')

    def test_branch_c_stays_legacy_without_questions(self):
        result = TestResult.objects.create(
            student=self.user, test=self.test, score=80, passed=True
        )
        self.mod.backfill_test_results(self._apps(), None)
        result.refresh_from_db()

        self.assertIsNone(result.earned_points)
        self.assertEqual(result.analytics_data_quality, 'legacy')

    def test_no_artificial_score_100_pair(self):
        """ТЗ-уточнение 5: пара earned=score, max=100 без маркировки запрещена."""
        self._question(points=1, order=1)
        self._question(points=1, order=2)
        result = TestResult.objects.create(
            student=self.user, test=self.test, score=50, passed=False
        )
        self.mod.backfill_test_results(self._apps(), None)
        result.refresh_from_db()

        self.assertNotEqual(result.max_points, Decimal('100.00'))
        self.assertEqual(result.analytics_data_quality, 'estimated')

    def test_idempotent(self):
        q = self._question(points=2, order=1)
        result = TestResult.objects.create(
            student=self.user, test=self.test, score=100, passed=True
        )
        TestAnswerLog.objects.create(result=result, question=q, is_correct=True)

        self.mod.backfill_test_results(self._apps(), None)
        result.refresh_from_db()
        first = result.earned_points

        self.mod.backfill_test_results(self._apps(), None)
        result.refresh_from_db()
        self.assertEqual(result.earned_points, first)

    def test_does_not_touch_exact_records(self):
        """Записи, заполненные при прохождении, не переписываются."""
        q = self._question(points=1, order=1)
        result = TestResult.objects.create(
            student=self.user, test=self.test, score=100, passed=True,
            earned_points=Decimal('7'), max_points=Decimal('7'),
            analytics_data_quality='exact',
        )
        TestAnswerLog.objects.create(result=result, question=q, is_correct=True)

        self.mod.backfill_test_results(self._apps(), None)
        result.refresh_from_db()
        self.assertEqual(result.earned_points, Decimal('7.00'))
        self.assertEqual(result.analytics_data_quality, 'exact')
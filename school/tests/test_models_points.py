from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from school.models import (
    AnalyticsDataQuality, Course, Lesson, Question, Test, TestResult,
)


class PointsFieldTests(TestCase):
    """Поля первичных баллов заданий (шаг 3.2.1)."""

    @classmethod
    def setUpTestData(cls):
        cls.course = Course.objects.create(title='Русский язык ЕГЭ')
        cls.lesson = Lesson.objects.create(course=cls.course, title='Орфография', order=1)
        cls.test = Test.objects.create(lesson=cls.lesson, title='Проверка', pass_score=70)

    def test_question_points_default_is_one(self):
        q = Question.objects.create(test=self.test, text='Вопрос', order=1)
        self.assertEqual(q.points, 1)

    def test_question_points_can_be_increased(self):
        q = Question.objects.create(test=self.test, text='Сочинение', order=2, points=5)
        q.refresh_from_db()
        self.assertEqual(q.points, 5)

    def test_question_points_zero_is_invalid(self):
        q = Question(test=self.test, text='Вопрос', order=3, points=0)
        with self.assertRaises(ValidationError):
            q.full_clean()


class PrimaryScoreMixinTests(TestCase):
    """Баллы и качество данных попыток."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='student1', password='x')
        cls.course = Course.objects.create(title='Русский язык ЕГЭ')
        cls.lesson = Lesson.objects.create(course=cls.course, title='Пунктуация', order=1)
        cls.test = Test.objects.create(lesson=cls.lesson, title='Проверка', pass_score=70)

    def test_new_result_has_nullable_points(self):
        """Старая логика создания результата не ломается — поля пустые."""
        r = TestResult.objects.create(
            student=self.user, test=self.test, score=80, passed=True
        )
        self.assertIsNone(r.earned_points)
        self.assertIsNone(r.max_points)

    def test_default_data_quality_is_legacy(self):
        """Записи без явных баллов не должны выдавать себя за точные."""
        r = TestResult.objects.create(
            student=self.user, test=self.test, score=80, passed=True
        )
        self.assertEqual(r.analytics_data_quality, AnalyticsDataQuality.LEGACY)

    def test_can_store_exact_points(self):
        r = TestResult.objects.create(
            student=self.user, test=self.test, score=75, passed=True,
            earned_points=Decimal('3'), max_points=Decimal('4'),
            analytics_data_quality=AnalyticsDataQuality.EXACT,
        )
        r.refresh_from_db()
        self.assertEqual(r.earned_points, Decimal('3.00'))
        self.assertEqual(r.max_points, Decimal('4.00'))

    def test_supports_fractional_points(self):
        """Критериальные проверки дают дробные баллы."""
        r = TestResult.objects.create(
            student=self.user, test=self.test, score=62, passed=False,
            earned_points=Decimal('2.5'), max_points=Decimal('4'),
        )
        r.refresh_from_db()
        self.assertEqual(r.earned_points, Decimal('2.50'))

    def test_negative_points_invalid(self):
        r = TestResult(
            student=self.user, test=self.test, score=0, passed=False,
            earned_points=Decimal('-1'), max_points=Decimal('4'),
        )
        with self.assertRaises(ValidationError):
            r.full_clean()

    def test_legacy_score_field_untouched(self):
        """score продолжает работать как раньше (ТЗ п.14 совместимость)."""
        r = TestResult.objects.create(
            student=self.user, test=self.test, score=91, passed=True
        )
        self.assertEqual(r.score, 91)

class AnalyticsQualityMixinTests(TestCase):
    """Качество данных живёт на попытках, не на ответах (шаг 3.2.1)."""

    def test_all_attempt_models_have_quality_field(self):
        from school.models import (
            CheckpointAttempt, ExamAttempt, HomeworkSubmission, TestResult,
        )
        for model in (TestResult, ExamAttempt, CheckpointAttempt, HomeworkSubmission):
            with self.subTest(model=model.__name__):
                field = model._meta.get_field('analytics_data_quality')
                self.assertEqual(field.default, AnalyticsDataQuality.LEGACY)

    def test_answer_models_have_no_quality_field(self):
        from django.core.exceptions import FieldDoesNotExist
        from school.models import CheckpointAnswer, ExamAnswer, TestAnswerLog
        for model in (TestAnswerLog, ExamAnswer, CheckpointAnswer):
            with self.subTest(model=model.__name__):
                with self.assertRaises(FieldDoesNotExist):
                    model._meta.get_field('analytics_data_quality')

    def test_reconstructed_and_estimated_are_distinct(self):
        """Ветви A и B backfill должны различаться (ТЗ-уточнение 5)."""
        self.assertNotEqual(
            AnalyticsDataQuality.RECONSTRUCTED, AnalyticsDataQuality.ESTIMATED
        )
        self.assertEqual(len(AnalyticsDataQuality.choices), 4)
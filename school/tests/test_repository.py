from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from school.models import (
    Course, ErrorRecord, ErrorStatus, Lesson, PlanItem, PlanStatus, Question,
    StudyPlan, Subject, Test, TestResult,
)
from school.services import analytics_repository as repo


class RepositoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='s1', password='x')
        cls.subject = Subject.objects.create(code='russian', name='Русский язык')
        cls.course = Course.objects.create(title='ЕГЭ', subject_ref=cls.subject)
        cls.lessons = [
            Lesson.objects.create(course=cls.course, title=f'Тема {i}', order=i)
            for i in range(1, 6)
        ]
        for lesson in cls.lessons:
            test = Test.objects.create(lesson=lesson, title='Тест', pass_score=70)
            Question.objects.create(test=test, text='В1', order=1, points=2)
            TestResult.objects.create(
                student=cls.user, test=test, score=75, passed=True,
                earned_points=Decimal('1.5'), max_points=Decimal('2'),
                analytics_data_quality='exact',
            )

    def test_lesson_attempts_returned(self):
        attempts = repo.get_lesson_attempts(self.user, self.lessons[0])
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].max_points, 2.0)

    def test_legacy_records_excluded(self):
        """Записи без достоверных баллов не попадают в расчёт."""
        lesson = Lesson.objects.create(course=self.course, title='Пустая', order=99)
        test = Test.objects.create(lesson=lesson, title='Тест', pass_score=70)
        TestResult.objects.create(
            student=self.user, test=test, score=80, passed=True,
            analytics_data_quality='legacy',
        )
        self.assertEqual(repo.get_lesson_attempts(self.user, lesson), [])

    def test_course_attempts_no_n_plus_one(self):
        """5 уроков — фиксированное число запросов, а не 5+."""
        with self.assertNumQueries(3):
            result = repo.get_course_attempts_by_lesson(self.user, self.course)
        self.assertEqual(len(result), 5)

    def test_course_attempts_flat_includes_exams(self):
        with self.assertNumQueries(5):
            attempts = repo.get_course_attempts(self.user, self.course)
        self.assertEqual(len(attempts), 5)

    def test_program_progress_counts(self):
        done, total = repo.get_program_progress_counts(self.user, self.course)
        self.assertEqual(done, 5)          # 5 сданных тестов
        self.assertEqual(total, 10)        # 5 уроков + 5 тестов

    def test_error_stats_grouped(self):
        for status in (ErrorStatus.NOT_ANALYZED, ErrorStatus.REINFORCED,
                       ErrorStatus.REINFORCED):
            ErrorRecord.objects.create(
                student=self.user, lesson=self.lessons[0], status=status
            )
        with self.assertNumQueries(1):
            stats = repo.get_error_stats(self.user)
        self.assertEqual(stats['reinforced'], 2)
        self.assertEqual(stats['total'], 3)

    def test_plan_counts_separate_cancelled(self):
        plan = StudyPlan.objects.create(
            student=self.user, subject=self.subject,
            start_date=timezone.now().date(), end_date=timezone.now().date(),
        )
        due = timezone.now()
        for status in (PlanStatus.DONE_ON_TIME, PlanStatus.DONE_ON_TIME,
                       PlanStatus.CANCELLED_BY_TEACHER, PlanStatus.SKIPPED):
            PlanItem.objects.create(
                plan=plan, item_type='lesson', title='Задача',
                due_at=due, status=status,
            )
        counts = repo.get_plan_counts(self.user)
        self.assertEqual(counts['total_due'], 4)
        self.assertEqual(counts['completed_on_time'], 2)
        self.assertEqual(counts['cancelled'], 1)
        self.assertEqual(counts['skipped'], 1)

    def test_empty_course_returns_zeros(self):
        empty = Course.objects.create(title='Пустой курс')
        self.assertEqual(repo.get_program_progress_counts(self.user, empty), (0, 0))
        self.assertEqual(repo.get_course_attempts(self.user, empty), [])
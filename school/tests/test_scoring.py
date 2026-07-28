from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from school.models import (
    Answer, Course, ErrorCorrectionAttempt, ErrorRecord, ErrorStatus, Lesson,
    Question, Subject, Test, TestAnswerLog, TestResult,
)
from school.services.scoring import (
    record_answer_points, record_test_attempt, register_errors,
    resolve_errors_on_success,
)


class TestScoringTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='s1', password='x')
        cls.subject = Subject.objects.create(code='russian', name='Русский язык')
        cls.course = Course.objects.create(title='ЕГЭ', subject_ref=cls.subject)
        cls.lesson = Lesson.objects.create(course=cls.course, title='Тема', order=1)
        cls.test = Test.objects.create(lesson=cls.lesson, title='Тест', pass_score=70)
        cls.q1 = Question.objects.create(test=cls.test, text='В1', order=1, points=1)
        cls.q2 = Question.objects.create(test=cls.test, text='В2', order=2, points=3)

    def _result(self, score=50):
        return TestResult.objects.create(
            student=self.user, test=self.test, score=score, passed=False
        )

    def test_records_exact_points(self):
        result = self._result()
        log = [(self.q1, None, True), (self.q2, None, False)]
        record_test_attempt(result, log)
        result.refresh_from_db()

        self.assertEqual(result.earned_points, Decimal('1.00'))
        self.assertEqual(result.max_points, Decimal('4.00'))
        self.assertEqual(result.analytics_data_quality, 'exact')

    def test_weighted_question_counted_by_points(self):
        """Задание на 3 балла весит втрое, а не как одно из двух."""
        result = self._result()
        record_test_attempt(result, [(self.q1, None, False), (self.q2, None, True)])
        result.refresh_from_db()
        self.assertEqual(result.earned_points, Decimal('3.00'))

    def test_answer_log_gets_points(self):
        result = self._result()
        log = TestAnswerLog.objects.create(
            result=result, question=self.q2, is_correct=True
        )
        record_answer_points(log, self.q2, True)
        log.refresh_from_db()
        self.assertEqual(log.earned_points, Decimal('3.00'))
        self.assertEqual(log.max_points, Decimal('3.00'))


class ErrorRegistrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='s1', password='x')
        cls.subject = Subject.objects.create(code='russian', name='Русский язык')
        cls.course = Course.objects.create(title='ЕГЭ', subject_ref=cls.subject)
        cls.lesson = Lesson.objects.create(course=cls.course, title='Тема', order=1)
        cls.test = Test.objects.create(lesson=cls.lesson, title='Тест', pass_score=70)
        cls.q1 = Question.objects.create(test=cls.test, text='В1', order=1)
        cls.q2 = Question.objects.create(test=cls.test, text='В2', order=2)

    def _result(self):
        return TestResult.objects.create(
            student=self.user, test=self.test, score=50, passed=False
        )

    def test_creates_error_for_wrong_answer(self):
        register_errors(self.user, self._result(), [(self.q1, None, False)])
        self.assertEqual(ErrorRecord.objects.filter(student=self.user).count(), 1)

    def test_correct_answer_creates_no_error(self):
        register_errors(self.user, self._result(), [(self.q1, None, True)])
        self.assertEqual(ErrorRecord.objects.count(), 0)

    def test_error_links_lesson_and_subject(self):
        register_errors(self.user, self._result(), [(self.q1, None, False)])
        record = ErrorRecord.objects.get(student=self.user)
        self.assertEqual(record.lesson, self.lesson)
        self.assertEqual(record.subject, self.subject)

    def test_repeat_increments_counter_not_duplicates(self):
        register_errors(self.user, self._result(), [(self.q1, None, False)])
        register_errors(self.user, self._result(), [(self.q1, None, False)])
        records = ErrorRecord.objects.filter(student=self.user, question=self.q1)
        self.assertEqual(records.count(), 1)
        self.assertEqual(records.first().repeated_count, 2)

    def test_correct_answer_moves_status_forward(self):
        register_errors(self.user, self._result(), [(self.q1, None, False)])
        resolve_errors_on_success(self.user, [(self.q1, None, True)], session_key='s1')
        record = ErrorRecord.objects.get(student=self.user)
        self.assertEqual(record.status, ErrorStatus.IN_PROGRESS)
        self.assertEqual(record.correction_attempts.count(), 1)

    def test_two_corrections_same_session_not_reinforced(self):
        """ТЗ 11: без второй сессии закрепления быть не может."""
        register_errors(self.user, self._result(), [(self.q1, None, False)])
        record = ErrorRecord.objects.get(student=self.user)
        record.explanation_viewed_at = timezone.now()
        record.save()

        resolve_errors_on_success(self.user, [(self.q1, None, True)], session_key='same')
        resolve_errors_on_success(self.user, [(self.q1, None, True)], session_key='same')

        record.refresh_from_db()
        self.assertNotEqual(record.status, ErrorStatus.REINFORCED)

    def test_reinforced_after_two_sessions(self):
        register_errors(self.user, self._result(), [(self.q1, None, False)])
        record = ErrorRecord.objects.get(student=self.user)
        record.explanation_viewed_at = timezone.now()
        record.save()

        resolve_errors_on_success(self.user, [(self.q1, None, True)], session_key='s1')
        resolve_errors_on_success(self.user, [(self.q1, None, True)], session_key='s2')

        record.refresh_from_db()
        self.assertEqual(record.status, ErrorStatus.REINFORCED)
        self.assertIsNotNone(record.reinforced_at)

    def test_reinforced_error_not_touched_again(self):
        register_errors(self.user, self._result(), [(self.q1, None, False)])
        record = ErrorRecord.objects.get(student=self.user)
        record.status = ErrorStatus.REINFORCED
        record.save()

        resolve_errors_on_success(self.user, [(self.q1, None, True)], session_key='s3')
        record.refresh_from_db()
        self.assertEqual(record.correction_attempts.count(), 0)
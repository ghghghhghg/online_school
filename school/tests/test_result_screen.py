from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from school.models import (
    Answer, Course, Lesson, LessonProgress, Question, Test, TestAnswerLog, TestResult,
)
from school.services.test_result import build_test_result, choose_next_step


class NextStepTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.course = Course.objects.create(title='ЕГЭ', slug='ege')
        cls.lesson = Lesson.objects.create(course=cls.course, title='Тема 1', order=1)
        cls.next_lesson = Lesson.objects.create(course=cls.course, title='Тема 2', order=2)

    def test_errors_lead_to_error_work(self):
        """ТЗ 10: есть существенные ошибки -> разобрать ошибки."""
        step = choose_next_step(None, self.lesson, wrong_count=2, passed=True, score=80)
        self.assertEqual(step.label, 'Разобрать ошибки')

    def test_weak_result_leads_to_reinforcement(self):
        step = choose_next_step(None, self.lesson, wrong_count=0, passed=False, score=40)
        self.assertEqual(step.label, 'Пройти закрепление')

    def test_clean_result_leads_to_next_topic(self):
        step = choose_next_step(
            None, self.lesson, wrong_count=0, passed=True, score=100,
            next_lesson=self.next_lesson,
        )
        self.assertEqual(step.label, 'Перейти к следующей теме')
        self.assertIn(str(self.next_lesson.pk), step.url)

    def test_last_lesson_returns_to_course(self):
        step = choose_next_step(None, self.lesson, wrong_count=0, passed=True, score=100)
        self.assertEqual(step.label, 'Вернуться к урокам')

    def test_errors_take_priority_over_weak_score(self):
        """При ошибках и низком балле сначала разбор, потом закрепление."""
        step = choose_next_step(None, self.lesson, wrong_count=3, passed=False, score=30)
        self.assertEqual(step.label, 'Разобрать ошибки')

    def test_every_step_has_reason(self):
        """ТЗ 26.12: ученик видит причину."""
        for wrong, score in [(2, 80), (0, 40), (0, 100)]:
            step = choose_next_step(None, self.lesson, wrong, True, score)
            self.assertTrue(step.reason)


class BuildResultTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='s1', password='pass12345')
        cls.course = Course.objects.create(title='ЕГЭ', slug='ege')
        cls.lesson = Lesson.objects.create(course=cls.course, title='Тема', order=1)
        cls.test = Test.objects.create(lesson=cls.lesson, title='Т', pass_score=70)
        cls.q1 = Question.objects.create(test=cls.test, text='В1', order=1, points=1)
        cls.q2 = Question.objects.create(test=cls.test, text='В2', order=2, points=3)

    def _result(self, score, passed=True, earned=None, maximum=None):
        return TestResult.objects.create(
            student=self.user, test=self.test, score=score, passed=passed,
            earned_points=earned, max_points=maximum,
            analytics_data_quality='exact' if earned else 'legacy',
        )

    def test_counts_correct_and_wrong(self):
        result = self._result(50, passed=False)
        logs = [
            TestAnswerLog.objects.create(result=result, question=self.q1, is_correct=True),
            TestAnswerLog.objects.create(result=result, question=self.q2, is_correct=False),
        ]
        data = build_test_result(self.user, self.lesson, result, logs)
        self.assertEqual(data.correct_count, 1)
        self.assertEqual(data.wrong_count, 1)
        self.assertEqual(data.total_count, 2)

    def test_shows_primary_points(self):
        result = self._result(25, passed=False, earned=Decimal('1'), maximum=Decimal('4'))
        data = build_test_result(self.user, self.lesson, result, [])
        self.assertTrue(data.has_points)
        self.assertEqual(data.earned_points, Decimal('1.00'))

    def test_no_points_for_legacy_result(self):
        data = build_test_result(self.user, self.lesson, self._result(80), [])
        self.assertFalse(data.has_points)

    def test_compares_with_previous(self):
        previous = self._result(60, passed=False)
        current = self._result(85)
        data = build_test_result(
            self.user, self.lesson, current, [], previous_result=previous
        )
        self.assertEqual(data.previous_score, 60)
        self.assertEqual(data.score_delta, 25)
        self.assertTrue(data.improved)

    def test_negative_delta(self):
        previous = self._result(90)
        current = self._result(70)
        data = build_test_result(
            self.user, self.lesson, current, [], previous_result=previous
        )
        self.assertEqual(data.score_delta, -20)
        self.assertFalse(data.improved)

    def test_first_attempt_has_no_comparison(self):
        data = build_test_result(self.user, self.lesson, self._result(75), [])
        self.assertIsNone(data.previous_score)
        self.assertIsNone(data.score_delta)

    def test_weak_flag(self):
        self.assertTrue(build_test_result(self.user, self.lesson, self._result(45, False), []).is_weak)
        self.assertFalse(build_test_result(self.user, self.lesson, self._result(75), []).is_weak)


class ResultViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='s1', password='pass12345')
        cls.course = Course.objects.create(title='ЕГЭ', slug='ege')
        cls.lesson = Lesson.objects.create(course=cls.course, title='Тема', order=1)
        cls.test = Test.objects.create(lesson=cls.lesson, title='Т', pass_score=70)
        cls.question = Question.objects.create(test=cls.test, text='Вопрос', order=1)
        Answer.objects.create(question=cls.question, text='Верно', is_correct=True)
        Answer.objects.create(question=cls.question, text='Неверно', is_correct=False)

    def setUp(self):
        self.client.login(username='s1', password='pass12345')

    def test_redirects_without_result(self):
        response = self.client.get(reverse('test_result', kwargs={'pk': self.lesson.pk}))
        self.assertEqual(response.status_code, 302)

    def test_renders_result(self):
        TestResult.objects.create(
            student=self.user, test=self.test, score=80, passed=True
        )
        response = self.client.get(reverse('test_result', kwargs={'pk': self.lesson.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Тест сдан')

    def test_shows_error_review_button(self):
        result = TestResult.objects.create(
            student=self.user, test=self.test, score=0, passed=False
        )
        TestAnswerLog.objects.create(
            result=result, question=self.question, is_correct=False
        )
        response = self.client.get(reverse('test_result', kwargs={'pk': self.lesson.pk}))
        self.assertContains(response, 'Разобрать ошибки')

    def test_shows_latest_attempt(self):
        TestResult.objects.create(student=self.user, test=self.test, score=40, passed=False)
        TestResult.objects.create(student=self.user, test=self.test, score=90, passed=True)
        response = self.client.get(reverse('test_result', kwargs={'pk': self.lesson.pk}))
        self.assertEqual(response.context['data'].score, 90)
        self.assertEqual(response.context['data'].previous_score, 40)
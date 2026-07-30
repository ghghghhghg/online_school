from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from school.models import (
    Course, Enrollment, ErrorRecord, ErrorStatus, Lesson, LessonProgress,
    Question, Subject, Test, TestResult,
)
from school.services.analytics_page import build_analytics


class AnalyticsPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='s1', password='pass12345')
        cls.subject = Subject.objects.create(code='rus', name='Русский язык')
        cls.course = Course.objects.create(
            title='ЕГЭ', slug='ege', subject_ref=cls.subject
        )
        cls.lessons = [
            Lesson.objects.create(course=cls.course, title=f'Тема {i}', order=i)
            for i in range(1, 4)
        ]
        cls.tests = [
            Test.objects.create(lesson=l, title='Т', pass_score=70) for l in cls.lessons
        ]
        for t in cls.tests:
            Question.objects.create(test=t, text='В', order=1, points=4)

    def _enroll(self):
        Enrollment.objects.create(
            student=self.user, course=self.course, status=Enrollment.STATUS_APPROVED
        )

    def _result(self, test, score, earned, maximum=4):
        return TestResult.objects.create(
            student=self.user, test=test, score=score, passed=score >= 70,
            earned_points=Decimal(str(earned)), max_points=Decimal(str(maximum)),
            analytics_data_quality='exact',
        )

    def test_no_courses(self):
        data = build_analytics(self.user)
        self.assertFalse(data.has_data)
        self.assertEqual(data.courses, [])

    def test_no_attempts_gives_no_data(self):
        self._enroll()
        self.assertFalse(build_analytics(self.user).has_data)

    def test_accuracy_by_points_not_by_count(self):
        """ТЗ 15.2: точность считается по баллам."""
        self._enroll()
        self._result(self.tests[0], 100, earned=4)
        self._result(self.tests[1], 25, earned=1)
        data = build_analytics(self.user)
        self.assertEqual(data.overall_accuracy, 62)  # 5 из 8

    def test_program_progress(self):
        self._enroll()
        self._result(self.tests[0], 100, earned=4)
        LessonProgress.objects.create(student=self.user, lesson=self.lessons[0])
        block = build_analytics(self.user).courses[0]
        self.assertEqual(block.total, 6)      # 3 урока + 3 теста
        self.assertEqual(block.completed, 2)  # 1 урок + 1 тест
        self.assertEqual(block.progress_percent, 33)

    def test_weak_topic_detected(self):
        self._enroll()
        for _ in range(5):
            self._result(self.tests[0], 25, earned=1)
        block = build_analytics(self.user).courses[0]
        self.assertTrue(block.weak_topics)
        self.assertEqual(block.weak_topics[0].lesson, self.lessons[0])

    def test_low_confidence_topic_not_reliable(self):
        """ТЗ 15.6: при малых данных процент не показываем."""
        self._enroll()
        self._result(self.tests[0], 25, earned=1)
        topic = build_analytics(self.user).courses[0].topics[0]
        self.assertFalse(topic.is_reliable)
        self.assertEqual(topic.label, 'Мало данных')

    def test_error_correction_rate(self):
        self._enroll()
        self._result(self.tests[0], 50, earned=2)
        for status in (ErrorStatus.NOT_ANALYZED, ErrorStatus.REINFORCED,
                       ErrorStatus.REINFORCED, ErrorStatus.IN_PROGRESS):
            ErrorRecord.objects.create(
                student=self.user, lesson=self.lessons[0], status=status
            )
        data = build_analytics(self.user)
        self.assertEqual(data.errors['total'], 4)
        self.assertEqual(data.errors['reinforced'], 2)
        self.assertEqual(data.correction_percent, 50)

    def test_stability_needs_enough_results(self):
        self._enroll()
        self._result(self.tests[0], 80, earned=3)
        self.assertEqual(build_analytics(self.user).stability_label, 'Мало данных')

    def test_prediction_unavailable_without_tables(self):
        self._enroll()
        self._result(self.tests[0], 80, earned=3)
        self.assertFalse(build_analytics(self.user).prediction_available)

    def test_adherence_none_without_plan(self):
        self._enroll()
        self._result(self.tests[0], 80, earned=3)
        self.assertIsNone(build_analytics(self.user).adherence)

    def test_topics_sorted_weakest_first(self):
        self._enroll()
        for _ in range(4):
            self._result(self.tests[0], 100, earned=4)
            self._result(self.tests[1], 25, earned=1)
        topics = build_analytics(self.user).courses[0].topics
        self.assertLess(topics[0].mastery, topics[-1].mastery)


class AnalyticsViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='s1', password='pass12345')
        cls.staff = User.objects.create_user(
            username='t1', password='pass12345', is_staff=True
        )

    def test_requires_login(self):
        self.assertEqual(
            self.client.get(reverse('student_analytics')).status_code, 302
        )

    def test_renders_empty_state(self):
        self.client.login(username='s1', password='pass12345')
        response = self.client.get(reverse('student_analytics'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Пока нет данных')

    def test_staff_redirected(self):
        self.client.login(username='t1', password='pass12345')
        self.assertEqual(
            self.client.get(reverse('student_analytics')).status_code, 302
        )
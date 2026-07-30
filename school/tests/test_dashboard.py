from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from school.models import (
    Course, Enrollment, Lesson, LessonProgress, Question, Subject, Test, TestResult,
)
from school.services.dashboard import build_dashboard


class DashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='s1', password='x', first_name='Иван'
        )
        cls.subject = Subject.objects.create(code='russian', name='Русский язык')
        cls.course = Course.objects.create(
            title='ЕГЭ русский', slug='ege-rus', subject_ref=cls.subject
        )
        cls.lessons = [
            Lesson.objects.create(course=cls.course, title=f'Тема {i}', order=i)
            for i in range(1, 4)
        ]

    def _enroll(self):
        return Enrollment.objects.create(
            student=self.user, course=self.course,
            status=Enrollment.STATUS_APPROVED,
        )

    def test_no_courses_gives_empty_state(self):
        data = build_dashboard(self.user)
        self.assertFalse(data.has_courses)
        self.assertIsNone(data.day_state.next_action)

    def test_recommends_first_lesson(self):
        self._enroll()
        data = build_dashboard(self.user)
        self.assertTrue(data.has_courses)
        self.assertEqual(data.day_state.next_action.title, 'Тема 1')
        self.assertEqual(data.day_state.next_action.button_label, 'Смотреть урок')

    def test_recommends_next_after_completed(self):
        self._enroll()
        LessonProgress.objects.create(student=self.user, lesson=self.lessons[0])
        data = build_dashboard(self.user)
        self.assertEqual(data.day_state.next_action.title, 'Тема 2')

    def test_reason_is_shown(self):
        """ТЗ 26.12: ученик видит причину рекомендации."""
        self._enroll()
        data = build_dashboard(self.user)
        self.assertTrue(data.day_state.next_action.reason)

    def test_course_progress_calculated(self):
        self._enroll()
        LessonProgress.objects.create(student=self.user, lesson=self.lessons[0])
        data = build_dashboard(self.user)
        card = data.courses[0]
        self.assertEqual(card.total, 3)
        self.assertEqual(card.completed, 1)
        self.assertEqual(card.percent, 33)

    def test_subject_name_from_reference(self):
        self._enroll()
        data = build_dashboard(self.user)
        self.assertEqual(data.courses[0].subject_name, 'Русский язык')

    def test_best_mock_result(self):
        from school.models import ExamAttempt, ExamMock
        from django.utils import timezone

        self._enroll()
        exam = ExamMock.objects.create(
            course=self.course, title='Пробник', duration_minutes=210
        )
        ExamAttempt.objects.create(
            student=self.user, exam=exam, submitted_at=timezone.now(),
            earned_points=Decimal('30'), max_points=Decimal('50'),
            analytics_data_quality='exact',
        )
        self.assertEqual(build_dashboard(self.user).best_score, 60)

    def test_no_mock_gives_no_best_score(self):
        self._enroll()
        self.assertIsNone(build_dashboard(self.user).best_score)

    def test_weak_topic_detected(self):
        self._enroll()
        test = Test.objects.create(lesson=self.lessons[0], title='Т', pass_score=70)
        Question.objects.create(test=test, text='В', order=1, points=4)
        for _ in range(4):
            TestResult.objects.create(
                student=self.user, test=test, score=30, passed=False,
                earned_points=Decimal('1'), max_points=Decimal('4'),
                analytics_data_quality='exact',
            )
        weak = build_dashboard(self.user).weak_topics
        self.assertTrue(weak)
        self.assertEqual(weak[0].lesson, self.lessons[0])
        self.assertLess(weak[0].mastery, 60)

    def test_strong_topic_not_in_weak_list(self):
        self._enroll()
        test = Test.objects.create(lesson=self.lessons[0], title='Т', pass_score=70)
        for _ in range(5):
            TestResult.objects.create(
                student=self.user, test=test, score=95, passed=True,
                earned_points=Decimal('19'), max_points=Decimal('20'),
                analytics_data_quality='exact',
            )
        self.assertEqual(build_dashboard(self.user).weak_topics, [])

    def test_prediction_marked_unavailable(self):
        """Без шкал и данных прогноз честно недоступен (ТЗ 26.9)."""
        self._enroll()
        self.assertFalse(build_dashboard(self.user).prediction_available)


class DashboardViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='s1', password='pass12345', first_name='Иван'
        )
        cls.staff = User.objects.create_user(
            username='t1', password='pass12345', is_staff=True
        )

    def test_requires_login(self):
        response = self.client.get(reverse('student_profile'))
        self.assertEqual(response.status_code, 302)

    def test_renders_for_student(self):
        self.client.login(username='s1', password='pass12345')
        response = self.client.get(reverse('student_profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Иван')

    def test_staff_redirected_to_teacher_panel(self):
        self.client.login(username='t1', password='pass12345')
        response = self.client.get(reverse('student_profile'))
        self.assertEqual(response.status_code, 302)

    def test_empty_state_explains_next_step(self):
        """ТЗ 20: пустое состояние объясняет, что делать."""
        self.client.login(username='s1', password='pass12345')
        response = self.client.get(reverse('student_profile'))
        self.assertContains(response, 'Выбрать курс')
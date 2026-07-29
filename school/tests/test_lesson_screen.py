from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from school.models import (
    Course, Homework, HomeworkSubmission, Lesson, LessonViewProgress,
    Question, Test, TestResult,
)
from school.services.lesson_flow import choose_lesson_step


class LessonStepTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='s1', password='pass12345')
        cls.course = Course.objects.create(title='ЕГЭ', slug='ege')
        cls.lesson = Lesson.objects.create(
            course=cls.course, title='Тема 1', order=1,
            video_url='https://vk.com/video1',
        )
        cls.next_lesson = Lesson.objects.create(course=cls.course, title='Тема 2', order=2)

    def _progress(self, percent=0, manual=False):
        return LessonViewProgress.objects.create(
            student=self.user, lesson=self.lesson,
            watched_percent=percent, marked_manually=manual,
        )

    def test_unwatched_video_gives_watch_step(self):
        step = choose_lesson_step(self.lesson, self._progress(0), None, None, None, None)
        self.assertEqual(step.label, 'Смотреть урок')

    def test_partially_watched_gives_continue(self):
        step = choose_lesson_step(self.lesson, self._progress(40), None, None, None, None)
        self.assertEqual(step.label, 'Продолжить урок')

    def test_watched_at_threshold(self):
        """ТЗ 7: 85% считается просмотром."""
        progress = self._progress(85)
        self.assertTrue(progress.is_watched)

    def test_manual_mark_counts_as_watched(self):
        progress = self._progress(0, manual=True)
        self.assertTrue(progress.is_watched)

    def test_watched_video_leads_to_test(self):
        test = Test.objects.create(lesson=self.lesson, title='Т', pass_score=70)
        self.lesson.refresh_from_db()
        step = choose_lesson_step(
            self.lesson, self._progress(90), None, None, None, None
        )
        self.assertEqual(step.label, 'Пройти мини-проверку')

    def test_failed_test_still_offers_test(self):
        test = Test.objects.create(lesson=self.lesson, title='Т', pass_score=70)
        self.lesson.refresh_from_db()
        result = TestResult.objects.create(
            student=self.user, test=test, score=40, passed=False
        )
        step = choose_lesson_step(
            self.lesson, self._progress(90), result, None, None, None
        )
        self.assertEqual(step.label, 'Пройти мини-проверку')

    def test_passed_test_leads_to_homework(self):
        test = Test.objects.create(lesson=self.lesson, title='Т', pass_score=70)
        self.lesson.refresh_from_db()
        result = TestResult.objects.create(
            student=self.user, test=test, score=90, passed=True
        )
        homework = Homework.objects.create(lesson=self.lesson, title='ДЗ')
        step = choose_lesson_step(
            self.lesson, self._progress(90), result, homework, None, None
        )
        self.assertEqual(step.label, 'Сдать домашнюю работу')

    def test_all_done_leads_to_next_lesson(self):
        step = choose_lesson_step(
            self.lesson, self._progress(0, manual=True), None, None, None,
            self.next_lesson,
        )
        self.assertEqual(step.label, 'Перейти к следующей теме')

    def test_last_lesson_returns_to_course(self):
        step = choose_lesson_step(
            self.lesson, self._progress(0, manual=True), None, None, None, None
        )
        self.assertEqual(step.label, 'Вернуться к урокам')

    def test_lesson_without_video_skips_watching(self):
        no_video = Lesson.objects.create(course=self.course, title='Текст', order=3)
        step = choose_lesson_step(no_video, None, None, None, None, self.next_lesson)
        self.assertEqual(step.label, 'Перейти к следующей теме')


class LessonViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='s1', password='pass12345')
        cls.course = Course.objects.create(title='ЕГЭ', slug='ege')
        cls.lesson = Lesson.objects.create(
            course=cls.course, title='Тема', order=1,
            learning_goal='Различать приставки пре- и при-',
            duration_minutes=18,
        )

    def setUp(self):
        self.client.login(username='s1', password='pass12345')

    def test_renders_goal_and_duration(self):
        response = self.client.get(reverse('lesson', kwargs={'pk': self.lesson.pk}))
        self.assertContains(response, 'Различать приставки')
        self.assertContains(response, '18')

    def test_creates_view_progress_on_open(self):
        self.client.get(reverse('lesson', kwargs={'pk': self.lesson.pk}))
        self.assertTrue(
            LessonViewProgress.objects.filter(
                student=self.user, lesson=self.lesson
            ).exists()
        )

    def test_counts_returns(self):
        url = reverse('lesson', kwargs={'pk': self.lesson.pk})
        self.client.get(url)
        self.client.get(url)
        progress = LessonViewProgress.objects.get(student=self.user, lesson=self.lesson)
        self.assertEqual(progress.returns_count, 1)

    def test_video_progress_saved(self):
        self.client.post(
            reverse('lesson_video_progress', kwargs={'pk': self.lesson.pk}),
            {'position': 120, 'percent': 45},
        )
        progress = LessonViewProgress.objects.get(student=self.user, lesson=self.lesson)
        self.assertEqual(progress.position_seconds, 120)
        self.assertEqual(progress.watched_percent, 45)

    def test_progress_never_decreases(self):
        """Перемотка назад не сбрасывает достигнутый процент."""
        url = reverse('lesson_video_progress', kwargs={'pk': self.lesson.pk})
        self.client.post(url, {'position': 200, 'percent': 80})
        self.client.post(url, {'position': 10, 'percent': 5})
        progress = LessonViewProgress.objects.get(student=self.user, lesson=self.lesson)
        self.assertEqual(progress.watched_percent, 80)
        self.assertEqual(progress.position_seconds, 10)

    def test_completed_at_set_at_threshold(self):
        self.client.post(
            reverse('lesson_video_progress', kwargs={'pk': self.lesson.pk}),
            {'position': 500, 'percent': 90},
        )
        progress = LessonViewProgress.objects.get(student=self.user, lesson=self.lesson)
        self.assertIsNotNone(progress.completed_at)

    def test_mark_watched_manually(self):
        self.client.post(reverse('lesson_mark_watched', kwargs={'pk': self.lesson.pk}))
        progress = LessonViewProgress.objects.get(student=self.user, lesson=self.lesson)
        self.assertTrue(progress.marked_manually)
        self.assertTrue(progress.is_watched)

    def test_invalid_payload_rejected(self):
        response = self.client.post(
            reverse('lesson_video_progress', kwargs={'pk': self.lesson.pk}),
            {'position': 'abc', 'percent': 'xyz'},
        )
        self.assertEqual(response.status_code, 400)
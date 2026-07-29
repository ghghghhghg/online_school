from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from school.models import (
    Course, ErrorCorrectionAttempt, ErrorRecord, ErrorStatus, Lesson,
    Question, Subject, Test,
)
from school.services import analytics_repository as repo

from django.db import connection
from django.test.utils import CaptureQueriesContext


class ErrorRepositoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='s1', password='pass12345')
        cls.subject = Subject.objects.create(code='rus', name='Русский язык')
        cls.course = Course.objects.create(title='ЕГЭ', slug='ege', subject_ref=cls.subject)
        cls.l1 = Lesson.objects.create(course=cls.course, title='Орфография', order=1)
        cls.l2 = Lesson.objects.create(course=cls.course, title='Пунктуация', order=2)

    def test_groups_by_lesson(self):
        ErrorRecord.objects.create(student=self.user, lesson=self.l1)
        ErrorRecord.objects.create(student=self.user, lesson=self.l1)
        ErrorRecord.objects.create(student=self.user, lesson=self.l2)
        groups = repo.get_error_records(self.user)
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]['count'], 2)

    def test_filters_by_status(self):
        ErrorRecord.objects.create(student=self.user, lesson=self.l1)
        ErrorRecord.objects.create(
            student=self.user, lesson=self.l1, status=ErrorStatus.REINFORCED
        )
        groups = repo.get_error_records(self.user, status=ErrorStatus.REINFORCED)
        self.assertEqual(sum(g['count'] for g in groups), 1)

    def test_other_student_errors_hidden(self):
        other = User.objects.create_user(username='s2', password='x')
        ErrorRecord.objects.create(student=other, lesson=self.l1)
        self.assertEqual(repo.get_error_records(self.user), [])

    def test_no_n_plus_one(self):
        """Число запросов не зависит от количества ошибок."""
        for _ in range(3):
            ErrorRecord.objects.create(student=self.user, lesson=self.l1)

        with CaptureQueriesContext(connection) as ctx:
            groups = repo.get_error_records(self.user)
            [r.lesson.title for g in groups for r in g['records']]
        few = len(ctx)

        for _ in range(10):
            ErrorRecord.objects.create(student=self.user, lesson=self.l2)

        with CaptureQueriesContext(connection) as ctx:
            groups = repo.get_error_records(self.user)
            [r.lesson.title for g in groups for r in g['records']]
        many = len(ctx)

        self.assertEqual(few, many)


class ErrorViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='s1', password='pass12345')
        cls.course = Course.objects.create(title='ЕГЭ', slug='ege')
        cls.lesson = Lesson.objects.create(course=cls.course, title='Тема', order=1)
        cls.test = Test.objects.create(lesson=cls.lesson, title='Т', pass_score=70)
        cls.question = Question.objects.create(
            test=cls.test, text='Вопрос', order=1, explanation='Пояснение',
        )

    def setUp(self):
        self.client.login(username='s1', password='pass12345')
        self.record = ErrorRecord.objects.create(
            student=self.user, lesson=self.lesson, question=self.question
        )

    def test_notebook_renders(self):
        response = self.client.get(reverse('error_notebook'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Работа над ошибками')

    def test_detail_shows_explanation(self):
        response = self.client.get(reverse('error_detail', kwargs={'pk': self.record.pk}))
        self.assertContains(response, 'Пояснение')

    def test_cannot_open_other_student_error(self):
        other = User.objects.create_user(username='s2', password='x')
        foreign = ErrorRecord.objects.create(student=other, lesson=self.lesson)
        response = self.client.get(reverse('error_detail', kwargs={'pk': foreign.pk}))
        self.assertEqual(response.status_code, 302)

    def test_mark_explained_sets_timestamp(self):
        self.client.post(reverse('error_mark_explained', kwargs={'pk': self.record.pk}))
        self.record.refresh_from_db()
        self.assertIsNotNone(self.record.explanation_viewed_at)
        self.assertEqual(self.record.status, ErrorStatus.IN_PROGRESS)

    def test_mark_explained_alone_does_not_reinforce(self):
        """ТЗ 11: одного изучения объяснения недостаточно."""
        self.client.post(reverse('error_mark_explained', kwargs={'pk': self.record.pk}))
        self.record.refresh_from_db()
        self.assertNotEqual(self.record.status, ErrorStatus.REINFORCED)

    def test_reinforces_when_conditions_already_met(self):
        for key in ('s1', 's2'):
            ErrorCorrectionAttempt.objects.create(
                error_record=self.record, is_correct=True,
                is_similar_task=True, session_key=key,
            )
        self.client.post(reverse('error_mark_explained', kwargs={'pk': self.record.pk}))
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, ErrorStatus.REINFORCED)

    def test_progress_shown_in_detail(self):
        self.record.explanation_viewed_at = timezone.now()
        self.record.save()
        response = self.client.get(reverse('error_detail', kwargs={'pk': self.record.pk}))
        self.assertTrue(response.context['progress']['explanation_viewed'])
        self.assertFalse(response.context['progress']['can_reinforce'])
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from school.models import (
    Answer, Course, Enrollment, ErrorRecord, ErrorStatus, Lesson,
    PracticeAnswer, PracticeSession, Question, Subject,
)
from school.services.practice import (
    create_session, finish_session, select_tasks, skip_answer, submit_answer,
)


class AnswerCheckTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.course = Course.objects.create(title='ЕГЭ', slug='ege')
        cls.lesson = Lesson.objects.create(course=cls.course, title='Тема', order=1)

    def _single(self):
        q = Question.objects.create(
            text='Вопрос', order=1, points=1, answer_type='single',
            lesson=self.lesson, is_in_bank=True,
        )
        right = Answer.objects.create(question=q, text='Верно', is_correct=True)
        Answer.objects.create(question=q, text='Неверно', is_correct=False)
        return q, right

    def test_single_correct(self):
        q, right = self._single()
        correct, earned = q.check_answer(right.pk)
        self.assertTrue(correct)
        self.assertEqual(earned, 1)

    def test_single_wrong(self):
        q, right = self._single()
        wrong = q.answers.filter(is_correct=False).first()
        correct, earned = q.check_answer(wrong.pk)
        self.assertFalse(correct)
        self.assertEqual(earned, 0)

    def test_text_answer_normalized(self):
        """Регистр, пробелы и ё не должны влиять."""
        q = Question.objects.create(
            text='Впишите слово', order=1, answer_type='text',
            correct_text='приём', lesson=self.lesson, is_in_bank=True,
        )
        for given in ('приём', 'Прием', ' ПРИЕМ '):
            with self.subTest(given=given):
                self.assertTrue(q.check_answer(given)[0])

    def test_text_multiple_variants(self):
        q = Question.objects.create(
            text='Ответ', order=1, answer_type='text',
            correct_text='два; 2', lesson=self.lesson, is_in_bank=True,
        )
        self.assertTrue(q.check_answer('2')[0])
        self.assertTrue(q.check_answer('два')[0])
        self.assertFalse(q.check_answer('три')[0])

    def test_empty_text_is_wrong(self):
        q = Question.objects.create(
            text='Ответ', order=1, answer_type='text',
            correct_text='да', lesson=self.lesson, is_in_bank=True,
        )
        self.assertFalse(q.check_answer('')[0])

    def test_multiple_partial_points(self):
        """ТЗ 9: частичные баллы при множественном выборе."""
        q = Question.objects.create(
            text='Выберите', order=1, points=4, answer_type='multiple',
            lesson=self.lesson, is_in_bank=True,
        )
        a1 = Answer.objects.create(question=q, text='A', is_correct=True)
        a2 = Answer.objects.create(question=q, text='B', is_correct=True)
        Answer.objects.create(question=q, text='C', is_correct=False)

        correct, earned = q.check_answer([a1.pk])
        self.assertFalse(correct)
        self.assertEqual(earned, 2.0)

        correct, earned = q.check_answer([a1.pk, a2.pk])
        self.assertTrue(correct)
        self.assertEqual(earned, 4.0)

    def test_multiple_penalizes_wrong_choice(self):
        q = Question.objects.create(
            text='Выберите', order=1, points=2, answer_type='multiple',
            lesson=self.lesson, is_in_bank=True,
        )
        a1 = Answer.objects.create(question=q, text='A', is_correct=True)
        wrong = Answer.objects.create(question=q, text='C', is_correct=False)
        _, earned = q.check_answer([a1.pk, wrong.pk])
        self.assertEqual(earned, 0.0)


class SelectTasksTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='s1', password='pass12345')
        cls.course = Course.objects.create(title='ЕГЭ', slug='ege')
        cls.l1 = Lesson.objects.create(course=cls.course, title='Тема 1', order=1)
        cls.l2 = Lesson.objects.create(course=cls.course, title='Тема 2', order=2)
        for i in range(5):
            Question.objects.create(
                text=f'Задание {i}', order=i, lesson=cls.l1, is_in_bank=True
            )
        for i in range(3):
            Question.objects.create(
                text=f'Другое {i}', order=i, lesson=cls.l2, is_in_bank=True
            )
        Question.objects.create(text='Не в банке', order=1, lesson=cls.l1)

    def test_bank_only(self):
        tasks = select_tasks(self.user, 'mixed', count=20)
        self.assertEqual(len(tasks), 8)

    def test_topic_mode_filters(self):
        tasks = select_tasks(self.user, 'topic', lesson=self.l1, count=20)
        self.assertEqual(len(tasks), 5)

    def test_count_limited(self):
        self.assertEqual(len(select_tasks(self.user, 'mixed', count=3)), 3)

    def test_errors_mode_without_errors_is_empty(self):
        self.assertEqual(select_tasks(self.user, 'errors'), [])

    def test_errors_mode_picks_error_lessons(self):
        ErrorRecord.objects.create(student=self.user, lesson=self.l2)
        tasks = select_tasks(self.user, 'errors', count=20)
        self.assertEqual(len(tasks), 3)

    def test_reinforced_errors_excluded(self):
        ErrorRecord.objects.create(
            student=self.user, lesson=self.l2, status=ErrorStatus.REINFORCED
        )
        self.assertEqual(select_tasks(self.user, 'errors'), [])


class SessionFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='s1', password='pass12345')
        cls.course = Course.objects.create(title='ЕГЭ', slug='ege')
        cls.lesson = Lesson.objects.create(course=cls.course, title='Тема', order=1)
        for i in range(3):
            q = Question.objects.create(
                text=f'Задание {i}', order=i, points=2,
                lesson=cls.lesson, is_in_bank=True,
            )
            Answer.objects.create(question=q, text='Верно', is_correct=True)
            Answer.objects.create(question=q, text='Неверно', is_correct=False)

    def test_creates_session_with_tasks(self):
        session = create_session(self.user, 'mixed', count=3)
        self.assertEqual(session.total_count, 3)
        self.assertEqual(session.answered_count, 0)

    def test_returns_none_without_tasks(self):
        Question.objects.update(is_in_bank=False)
        self.assertIsNone(create_session(self.user, 'mixed'))

    def test_submit_records_points(self):
        session = create_session(self.user, 'mixed', count=3)
        answer = session.next_answer()
        right = answer.question.answers.filter(is_correct=True).first()
        correct, earned, maximum = submit_answer(answer, right.pk)
        self.assertTrue(correct)
        self.assertEqual(earned, 2)
        answer.refresh_from_db()
        self.assertEqual(answer.earned_points, Decimal('2.00'))

    def test_wrong_answer_creates_error(self):
        session = create_session(self.user, 'mixed', count=3)
        answer = session.next_answer()
        wrong = answer.question.answers.filter(is_correct=False).first()
        submit_answer(answer, wrong.pk)
        self.assertTrue(
            ErrorRecord.objects.filter(
                student=self.user, question=answer.question
            ).exists()
        )

    def test_skip_marks_answered(self):
        session = create_session(self.user, 'mixed', count=3)
        answer = session.next_answer()
        skip_answer(answer)
        answer.refresh_from_db()
        self.assertTrue(answer.skipped)
        self.assertEqual(session.answered_count, 1)

    def test_next_answer_moves_forward(self):
        session = create_session(self.user, 'mixed', count=3)
        first = session.next_answer()
        skip_answer(first)
        self.assertNotEqual(session.next_answer().pk, first.pk)

    def test_finish_sums_points(self):
        session = create_session(self.user, 'mixed', count=3)
        for _ in range(3):
            answer = session.next_answer()
            right = answer.question.answers.filter(is_correct=True).first()
            submit_answer(answer, right.pk)
        earned, maximum = finish_session(session)
        self.assertEqual(earned, 6)
        self.assertEqual(maximum, 6)
        session.refresh_from_db()
        self.assertEqual(session.analytics_data_quality, 'exact')

    def test_correct_answer_advances_error_status(self):
        """Практика двигает статус ошибки по теме."""
        record = ErrorRecord.objects.create(student=self.user, lesson=self.lesson)
        session = create_session(self.user, 'mixed', count=3)
        answer = session.next_answer()
        right = answer.question.answers.filter(is_correct=True).first()
        submit_answer(answer, right.pk)
        record.refresh_from_db()
        self.assertEqual(record.status, ErrorStatus.IN_PROGRESS)

    def test_two_sessions_reinforce_error(self):
        """ТЗ 11: закрепление требует двух разных сессий."""
        from django.utils import timezone

        record = ErrorRecord.objects.create(
            student=self.user, lesson=self.lesson,
            explanation_viewed_at=timezone.now(),
        )
        for _ in range(2):
            session = create_session(self.user, 'mixed', count=1)
            answer = session.next_answer()
            right = answer.question.answers.filter(is_correct=True).first()
            submit_answer(answer, right.pk)

        record.refresh_from_db()
        self.assertEqual(record.status, ErrorStatus.REINFORCED)


class PracticeViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='s1', password='pass12345')
        cls.course = Course.objects.create(title='ЕГЭ', slug='ege')
        cls.lesson = Lesson.objects.create(course=cls.course, title='Тема', order=1)
        Enrollment.objects.create(
            student=cls.user, course=cls.course, status=Enrollment.STATUS_APPROVED
        )
        q = Question.objects.create(
            text='Задание', order=1, lesson=cls.lesson, is_in_bank=True
        )
        Answer.objects.create(question=q, text='Верно', is_correct=True)

    def setUp(self):
        self.client.login(username='s1', password='pass12345')

    def test_home_renders(self):
        response = self.client.get(reverse('practice_home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Практика')

    def test_empty_bank_state(self):
        Question.objects.update(is_in_bank=False)
        response = self.client.get(reverse('practice_home'))
        self.assertContains(response, 'Банк заданий пока пуст')

    def test_start_creates_session(self):
        response = self.client.post(reverse('practice_start'), {'mode': 'mixed'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(PracticeSession.objects.filter(student=self.user).exists())

    def test_start_without_tasks_redirects_back(self):
        Question.objects.update(is_in_bank=False)
        response = self.client.post(reverse('practice_start'), {'mode': 'mixed'})
        self.assertRedirects(response, reverse('practice_home'))

    def test_cannot_open_foreign_session(self):
        other = User.objects.create_user(username='s2', password='x')
        session = create_session(other, 'mixed', count=1)
        response = self.client.get(
            reverse('practice_session', kwargs={'pk': session.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_finished_session_redirects_to_result(self):
        session = create_session(self.user, 'mixed', count=1)
        finish_session(session)
        response = self.client.get(
            reverse('practice_session', kwargs={'pk': session.pk})
        )
        self.assertRedirects(
            response, reverse('practice_result', kwargs={'pk': session.pk})
        )

class CourseFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='s1', password='pass12345')
        cls.rus = Course.objects.create(title='Русский', slug='rus')
        cls.math = Course.objects.create(title='Математика', slug='math')
        l1 = Lesson.objects.create(course=cls.rus, title='Тема рус', order=1)
        l2 = Lesson.objects.create(course=cls.math, title='Тема мат', order=1)
        Question.objects.create(text='Рус вопрос', order=1, lesson=l1, is_in_bank=True)
        Question.objects.create(text='Мат вопрос', order=1, lesson=l2, is_in_bank=True)
        Enrollment.objects.create(
            student=cls.user, course=cls.rus, status=Enrollment.STATUS_APPROVED
        )
        Enrollment.objects.create(
            student=cls.user, course=cls.math, status=Enrollment.STATUS_APPROVED
        )

    def test_mixed_mode_respects_course_filter(self):
        """Смешанный режим не должен смешивать предметы."""
        tasks = select_tasks(self.user, 'mixed', course=self.rus, count=20)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].text, 'Рус вопрос')

    def setUp(self):
        self.client.login(username='s1', password='pass12345')

    def test_start_passes_course_from_form(self):
        self.client.post(reverse('practice_start'), {
            'mode': 'mixed', 'course': self.rus.pk,
        })
        session = PracticeSession.objects.filter(student=self.user).first()
        self.assertEqual(session.course_id, self.rus.pk)
        self.assertEqual(session.answers.first().question.text, 'Рус вопрос')
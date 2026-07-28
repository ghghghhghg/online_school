from datetime import date, datetime, timedelta, timezone as dt_tz

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from school.models import (
    Course, ErrorCorrectionAttempt, ErrorRecord, ErrorStatus, PlanItem,
    PlanStatus, StudyPlan, StudySession, Subject,
)
from school.services.analytics import plan_adherence
from school.services.study_time import current_streak, is_active_day, seconds_to_add


class ErrorRecordTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='s1', password='x')

    def _record(self):
        return ErrorRecord.objects.create(student=self.user)

    def test_default_status(self):
        self.assertEqual(self._record().status, ErrorStatus.NOT_ANALYZED)

    def test_cannot_reinforce_without_explanation(self):
        r = self._record()
        for key in ('a', 'b'):
            ErrorCorrectionAttempt.objects.create(
                error_record=r, is_correct=True, is_similar_task=True, session_key=key
            )
        self.assertFalse(r.try_reinforce())
        self.assertNotEqual(r.status, ErrorStatus.REINFORCED)

    def test_cannot_reinforce_with_single_correct(self):
        r = self._record()
        r.explanation_viewed_at = timezone.now()
        r.save()
        ErrorCorrectionAttempt.objects.create(
            error_record=r, is_correct=True, is_similar_task=True, session_key='a'
        )
        self.assertFalse(r.try_reinforce())

    def test_cannot_reinforce_in_same_session(self):
        """ТЗ 11: второе задание должно быть в другой учебной сессии."""
        r = self._record()
        r.explanation_viewed_at = timezone.now()
        r.save()
        for _ in range(2):
            ErrorCorrectionAttempt.objects.create(
                error_record=r, is_correct=True, is_similar_task=True, session_key='same'
            )
        self.assertFalse(r.try_reinforce())

    def test_reinforce_when_all_conditions_met(self):
        r = self._record()
        r.explanation_viewed_at = timezone.now()
        r.save()
        ErrorCorrectionAttempt.objects.create(
            error_record=r, is_correct=True, is_similar_task=True, session_key='s1'
        )
        ErrorCorrectionAttempt.objects.create(
            error_record=r, is_correct=True, is_similar_task=False, session_key='s2'
        )
        self.assertTrue(r.try_reinforce())
        r.refresh_from_db()
        self.assertEqual(r.status, ErrorStatus.REINFORCED)
        self.assertIsNotNone(r.reinforced_at)

    def test_wrong_attempts_do_not_count(self):
        r = self._record()
        r.explanation_viewed_at = timezone.now()
        r.save()
        for key in ('s1', 's2', 's3'):
            ErrorCorrectionAttempt.objects.create(
                error_record=r, is_correct=False, session_key=key
            )
        self.assertFalse(r.try_reinforce())

    def test_repeat_after_reinforce_gives_regressed(self):
        r = self._record()
        r.status = ErrorStatus.REINFORCED
        r.reinforced_at = timezone.now()
        r.save()
        r.register_repeat()
        r.refresh_from_db()
        self.assertEqual(r.status, ErrorStatus.REGRESSED)
        self.assertIsNone(r.reinforced_at)
        self.assertEqual(r.repeated_count, 2)


class StudySessionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='s1', password='x')

    def test_duplicate_client_session_rejected(self):
        """Защита от двойного учёта одной вкладки."""
        StudySession.objects.create(student=self.user, client_session_id='tab-1')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StudySession.objects.create(student=self.user, client_session_id='tab-1')

    def test_two_tabs_are_separate_sessions(self):
        StudySession.objects.create(student=self.user, client_session_id='tab-1')
        StudySession.objects.create(student=self.user, client_session_id='tab-2')
        self.assertEqual(StudySession.objects.filter(student=self.user).count(), 2)

    def test_seconds_counted_within_timeout(self):
        now = datetime(2026, 7, 28, 12, 0, tzinfo=dt_tz.utc)
        self.assertEqual(seconds_to_add(now - timedelta(seconds=45), now), 45)

    def test_idle_over_timeout_not_counted(self):
        """ТЗ 15.11: простой дольше 5 минут не идёт в зачёт."""
        now = datetime(2026, 7, 28, 12, 0, tzinfo=dt_tz.utc)
        self.assertEqual(seconds_to_add(now - timedelta(minutes=20), now), 0)

    def test_negative_delta_ignored(self):
        now = datetime(2026, 7, 28, 12, 0, tzinfo=dt_tz.utc)
        self.assertEqual(seconds_to_add(now + timedelta(seconds=30), now), 0)


class ActiveDayTests(TestCase):
    def test_by_time(self):
        self.assertTrue(is_active_day(active_seconds=16 * 60))

    def test_by_completed_item(self):
        self.assertTrue(is_active_day(active_seconds=60, completed_required_items=1))

    def test_by_solved_tasks(self):
        self.assertTrue(is_active_day(active_seconds=60, solved_tasks=5))

    def test_not_active(self):
        self.assertFalse(is_active_day(active_seconds=300, solved_tasks=2))

    def test_streak_counts_consecutive_days(self):
        today = date(2026, 7, 28)
        days = {today, date(2026, 7, 27), date(2026, 7, 26), date(2026, 7, 24)}
        self.assertEqual(current_streak(days, today), 3)

    def test_streak_zero_without_today(self):
        today = date(2026, 7, 28)
        self.assertEqual(current_streak({date(2026, 7, 27)}, today), 0)


class PlanTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='s1', password='x')
        cls.subject = Subject.objects.create(code='russian', name='Русский язык')
        cls.plan = StudyPlan.objects.create(
            student=cls.user, subject=cls.subject,
            start_date=date(2026, 9, 1), end_date=date(2027, 5, 31),
        )

    def _item(self, due, **kwargs):
        return PlanItem.objects.create(
            plan=self.plan, item_type='lesson', title='Урок', due_at=due, **kwargs
        )

    def test_completed_on_time(self):
        due = timezone.now() + timedelta(days=1)
        item = self._item(due)
        item.mark_completed(when=timezone.now())
        self.assertEqual(item.status, PlanStatus.DONE_ON_TIME)

    def test_completed_late(self):
        due = timezone.now() - timedelta(days=1)
        item = self._item(due)
        item.mark_completed(when=timezone.now())
        self.assertEqual(item.status, PlanStatus.DONE_LATE)

    def test_cancelled_statuses_are_distinct(self):
        """Отмена преподавателем и системой различаются (ТЗ 15.10)."""
        self.assertNotEqual(
            PlanStatus.CANCELLED_BY_TEACHER, PlanStatus.CANCELLED_BY_SYSTEM
        )
        self.assertEqual(len(PlanStatus.cancelled()), 2)
        self.assertNotIn(PlanStatus.SKIPPED, PlanStatus.cancelled())

    def test_adherence_excludes_cancelled(self):
        """8 задач, 2 отменены, 6 сделаны вовремя -> 100%."""
        self.assertEqual(
            plan_adherence(completed_on_time=6, total_due=8, cancelled=2), 100
        )

    def test_adherence_counts_skipped_against_student(self):
        """Пропуск учеником ухудшает показатель, отмена — нет."""
        self.assertLess(
            plan_adherence(completed_on_time=6, total_due=8, cancelled=0), 100
        )
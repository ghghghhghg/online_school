from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from school.models import (
    Course, Enrollment, Homework, Lesson, PlanItem, PlanStatus, StudentProfile,
    StudyPlan, Subject, Test,
)
from school.services.planner import (
    PlannedTask, available_dates, build_plan_for_student, day_load_minutes, distribute,
)


def task(minutes, title='Задача'):
    return PlannedTask(item_type='lesson', title=title, estimated_minutes=minutes)


class AvailableDatesTests(TestCase):
    def test_seven_days_gives_every_day(self):
        days = available_dates(date(2026, 8, 3), 7, 5)
        self.assertEqual(len(days), 5)
        self.assertEqual(days[1], date(2026, 8, 4))

    def test_five_days_skips_weekend(self):
        days = available_dates(date(2026, 8, 3), 5, 7)  # понедельник
        self.assertNotIn(date(2026, 8, 8), days)   # суббота
        self.assertNotIn(date(2026, 8, 9), days)   # воскресенье

    def test_zero_days_gives_nothing(self):
        self.assertEqual(available_dates(date(2026, 8, 3), 0, 5), [])

    def test_requested_count_respected(self):
        self.assertEqual(len(available_dates(date(2026, 8, 3), 3, 6)), 6)


class DistributeTests(TestCase):
    def test_respects_daily_limit(self):
        """ТЗ 18: не больше задач, чем позволяет время."""
        tasks = [task(30), task(30), task(30)]
        dates = available_dates(date(2026, 8, 3), 7, 5)
        schedule = distribute(tasks, dates, daily_minutes=60)
        self.assertEqual(len(schedule[0][1]), 2)
        self.assertLessEqual(day_load_minutes(schedule[0][1]), 60)

    def test_spills_to_next_day(self):
        tasks = [task(45), task(45)]
        dates = available_dates(date(2026, 8, 3), 7, 5)
        schedule = distribute(tasks, dates, daily_minutes=60)
        self.assertEqual(len(schedule), 2)

    def test_oversized_task_still_scheduled(self):
        """Задача длиннее лимита не должна выпасть из плана."""
        schedule = distribute([task(210)], available_dates(date(2026, 8, 3), 7, 3), 60)
        self.assertEqual(len(schedule), 1)

    def test_empty_input(self):
        self.assertEqual(distribute([], available_dates(date(2026, 8, 3), 7, 3), 60), [])
        self.assertEqual(distribute([task(10)], [], 60), [])

    def test_order_preserved(self):
        tasks = [task(20, 'A'), task(20, 'B'), task(20, 'C')]
        schedule = distribute(tasks, available_dates(date(2026, 8, 3), 7, 5), 40)
        self.assertEqual(schedule[0][1][0].title, 'A')
        self.assertEqual(schedule[0][1][1].title, 'B')


class BuildPlanTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='s1', password='pass12345')
        cls.subject = Subject.objects.create(code='rus', name='Русский язык')
        cls.course = Course.objects.create(title='ЕГЭ', slug='ege', subject_ref=cls.subject)
        for i in range(1, 4):
            lesson = Lesson.objects.create(
                course=cls.course, title=f'Тема {i}', order=i, duration_minutes=20
            )
            Test.objects.create(lesson=lesson, title='Т', pass_score=70)

    def test_creates_plan_with_items(self):
        plan = build_plan_for_student(self.user, self.course)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.items.count(), 6)  # 3 урока + 3 проверки

    def test_creates_profile_if_missing(self):
        build_plan_for_student(self.user, self.course)
        self.assertTrue(StudentProfile.objects.filter(user=self.user).exists())

    def test_respects_daily_minutes(self):
        profile, _ = StudentProfile.objects.get_or_create(user=self.user)
        profile.daily_minutes = 30
        profile.save()
        plan = build_plan_for_student(self.user, self.course)
        first_day = plan.items.order_by('due_at', 'order').first().due_at.date()
        minutes = sum(
            i.estimated_minutes for i in plan.items.filter(due_at__date=first_day)
        )
        self.assertLessEqual(minutes, 30)

    def test_regeneration_keeps_completed(self):
        plan = build_plan_for_student(self.user, self.course)
        item = plan.items.first()
        item.mark_completed()
        build_plan_for_student(self.user, self.course)
        item.refresh_from_db()
        self.assertIn(item.status, PlanStatus.completed())

    def test_empty_course_gives_no_items(self):
        empty = Course.objects.create(title='Пустой', slug='empty')
        plan = build_plan_for_student(self.user, empty)
        self.assertEqual(plan.items.count() if plan else 0, 0)


class PlanViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='s1', password='pass12345')
        cls.course = Course.objects.create(title='ЕГЭ', slug='ege')
        cls.lesson = Lesson.objects.create(
            course=cls.course, title='Тема', order=1, duration_minutes=20
        )
        Enrollment.objects.create(
            student=cls.user, course=cls.course, status=Enrollment.STATUS_APPROVED
        )

    def setUp(self):
        self.client.login(username='s1', password='pass12345')

    def test_empty_state_offers_generation(self):
        response = self.client.get(reverse('study_plan'))
        self.assertContains(response, 'Составить план')

    def test_generation_creates_plan(self):
        self.client.post(reverse('plan_generate'))
        self.assertTrue(StudyPlan.objects.filter(student=self.user).exists())

    def test_complete_marks_on_time(self):
        self.client.post(reverse('plan_generate'))
        item = PlanItem.objects.filter(plan__student=self.user).first()
        self.client.post(reverse('plan_item_complete', kwargs={'pk': item.pk}))
        item.refresh_from_db()
        self.assertIn(item.status, PlanStatus.completed())

    def test_cannot_complete_foreign_item(self):
        other = User.objects.create_user(username='s2', password='x')
        plan = StudyPlan.objects.create(
            student=other, start_date=timezone.localdate(),
            end_date=timezone.localdate(),
        )
        item = PlanItem.objects.create(
            plan=plan, item_type='lesson', title='Чужая', due_at=timezone.now()
        )
        response = self.client.post(
            reverse('plan_item_complete', kwargs={'pk': item.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_overdue_marked_automatically(self):
        plan = StudyPlan.objects.create(
            student=self.user, start_date=timezone.localdate(),
            end_date=timezone.localdate(),
        )
        item = PlanItem.objects.create(
            plan=plan, item_type='lesson', title='Вчерашняя',
            due_at=timezone.now() - timedelta(days=1),
        )
        self.client.get(reverse('study_plan'))
        item.refresh_from_db()
        self.assertEqual(item.status, PlanStatus.OVERDUE)
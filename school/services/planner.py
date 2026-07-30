"""
Генерация учебного плана (ТЗ 18).

Чистая часть — распределение задач по дням с учётом доступного времени.
Сборка задач из БД — в build_plan_for_student().
"""
from dataclasses import dataclass
from datetime import date, timedelta

from .constants import PLANNER_DEFAULT_DAILY_MINUTES, PLANNER_MAX_DAYS_AHEAD


@dataclass(frozen=True)
class PlannedTask:
    """Задача до попадания в базу."""
    item_type: str
    title: str
    estimated_minutes: int
    required: bool = True
    priority: int = 5
    target_object: object = None


def available_dates(start: date, days_per_week: int, count: int) -> list[date]:
    """
    Учебные дни начиная с start.
    При 7 днях — каждый день, при 5 — пропускаем выходные,
    при меньшем — равномерно разреживаем неделю.
    """
    if days_per_week <= 0:
        return []

    result = []
    day = start
    guard = 0
    while len(result) < count and guard < PLANNER_MAX_DAYS_AHEAD:
        guard += 1
        weekday = day.weekday()
        if days_per_week >= 7:
            take = True
        elif days_per_week == 5:
            take = weekday < 5
        elif days_per_week == 6:
            take = weekday < 6
        else:
            # равномерно: например 3 дня -> пн, ср, пт
            step = 7 / days_per_week
            take = any(round(i * step) == weekday for i in range(days_per_week))
        if take:
            result.append(day)
        day += timedelta(days=1)
    return result


def distribute(tasks, dates, daily_minutes: int) -> list[tuple[date, list]]:
    """
    Раскладывает задачи по дням, не превышая дневной лимит времени.

    Задача, которая одна длиннее лимита, всё равно ставится в день —
    иначе она никогда не попадёт в план.
    """
    if not tasks or not dates:
        return []

    limit = daily_minutes or PLANNER_DEFAULT_DAILY_MINUTES
    schedule = []
    day_index = 0
    current, current_minutes = [], 0

    for task in tasks:
        if day_index >= len(dates):
            break
        fits = current_minutes + task.estimated_minutes <= limit
        if current and not fits:
            schedule.append((dates[day_index], current))
            day_index += 1
            current, current_minutes = [], 0
            if day_index >= len(dates):
                break
        current.append(task)
        current_minutes += task.estimated_minutes

    if current and day_index < len(dates):
        schedule.append((dates[day_index], current))

    return schedule


def day_load_minutes(tasks) -> int:
    return sum(t.estimated_minutes for t in tasks)

def collect_tasks(student, course):
    """Что осталось пройти в курсе — в порядке программы."""
    from school.models import (
        Homework, HomeworkSubmission, LessonProgress, TestResult,
    )
    from .constants import (
        MINUTES_ERROR_WORK, MINUTES_HOMEWORK, MINUTES_LESSON, MINUTES_TEST,
    )

    completed_lessons = set(
        LessonProgress.objects
        .filter(student=student, lesson__course=course)
        .values_list('lesson_id', flat=True)
    )
    passed_tests = set(
        TestResult.objects
        .filter(student=student, test__lesson__course=course, passed=True)
        .values_list('test__lesson_id', flat=True)
    )
    submitted_homework = set(
        HomeworkSubmission.objects
        .filter(student=student, homework__lesson__course=course)
        .values_list('homework__lesson_id', flat=True)
    )
    homework_by_lesson = {
        hw.lesson_id: hw
        for hw in Homework.objects.filter(lesson__course=course)
    }

    lessons = (
        course.lessons
        .select_related('module')
        .prefetch_related('test')
        .order_by('module__order', 'order')
    )

    tasks = []
    for lesson in lessons:
        if lesson.id not in completed_lessons:
            tasks.append(PlannedTask(
                item_type='lesson',
                title=f'Урок: {lesson.title}',
                estimated_minutes=lesson.duration_minutes or MINUTES_LESSON,
                priority=3,
                target_object=lesson,
            ))
        if hasattr(lesson, 'test') and lesson.id not in passed_tests:
            tasks.append(PlannedTask(
                item_type='mini_check',
                title=f'Проверка: {lesson.title}',
                estimated_minutes=MINUTES_TEST,
                priority=2,
                target_object=lesson,
            ))
        homework = homework_by_lesson.get(lesson.id)
        if homework and lesson.id not in submitted_homework:
            tasks.append(PlannedTask(
                item_type='homework',
                title=homework.title,
                estimated_minutes=MINUTES_HOMEWORK,
                priority=1,
                target_object=lesson,
            ))
    return tasks


def build_plan_for_student(student, course, start=None, horizon_days=None):
    """
    Создаёт или пересобирает активный план по курсу.
    Выполненные задачи сохраняются, пересобирается только незавершённое.
    """
    from django.contrib.contenttypes.models import ContentType
    from django.utils import timezone as tz

    from school.models import PlanItem, PlanStatus, StudentProfile, StudyPlan
    from .constants import PLANNER_HORIZON_DAYS

    start = start or tz.localdate()
    horizon = horizon_days or PLANNER_HORIZON_DAYS

    profile, _ = StudentProfile.objects.get_or_create(user=student)
    dates = available_dates(start, profile.available_days_per_week, horizon)
    if not dates:
        return None

    plan, _ = StudyPlan.objects.get_or_create(
        student=student,
        subject=course.subject_ref,
        status='active',
        defaults={'start_date': start, 'end_date': dates[-1], 'source': 'system'},
    )

    # Незавершённые задачи пересобираем, выполненные не трогаем
    plan.items.filter(
        status__in=[PlanStatus.PLANNED, PlanStatus.IN_PROGRESS, PlanStatus.OVERDUE]
    ).delete()

    tasks = collect_tasks(student, course)
    if not tasks:
        return plan

    schedule = distribute(tasks, dates, profile.daily_minutes)
    lesson_ct = ContentType.objects.get_for_model(
        tasks[0].target_object.__class__
    ) if tasks[0].target_object else None

    order = 0
    for day, day_tasks in schedule:
        due = tz.make_aware(
            tz.datetime.combine(day, tz.datetime.min.time().replace(hour=23, minute=59))
        ) if tz.is_naive(tz.datetime.combine(day, tz.datetime.min.time())) else None

        from datetime import datetime, time
        due_at = tz.make_aware(datetime.combine(day, time(23, 59)))

        for task in day_tasks:
            order += 1
            PlanItem.objects.create(
                plan=plan,
                item_type=task.item_type,
                content_type=lesson_ct,
                object_id=task.target_object.pk if task.target_object else None,
                title=task.title,
                due_at=due_at,
                estimated_minutes=task.estimated_minutes,
                required=task.required,
                priority=task.priority,
                order=order,
            )

    plan.end_date = schedule[-1][0]
    plan.save(update_fields=['end_date'])
    return plan
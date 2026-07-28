"""
Доступ к данным для расчётного слоя.

Только выборки и нормализация в DTO. Формул здесь нет — они в analytics.py.
Все запросы оптимизированы под отсутствие N+1 (ТЗ-уточнение 12).
"""
from collections import defaultdict
from datetime import date, timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone

from school.models import (
    Course, ErrorRecord, ErrorStatus, Enrollment, ExamAttempt, Homework,
    HomeworkSubmission, Lesson, LessonProgress, PlanItem, PlanStatus,
    StudySession, TestResult,
)
from .analytics import AttemptData
from .constants import MASTERY_WINDOW_DAYS

# Качество данных, пригодное для расчётов
USABLE_QUALITY = ('exact', 'reconstructed', 'estimated')
# Для прогноза первичного балла оценочные данные не годятся
PRECISE_QUALITY = ('exact', 'reconstructed')


def _window_start(now=None):
    return (now or timezone.now()) - timedelta(days=MASTERY_WINDOW_DAYS)


def get_lesson_attempts(student, lesson, now=None) -> list[AttemptData]:
    """
    Все попытки ученика, относящиеся к одному уроку.
    Один запрос на источник, без обращения к связанным объектам в цикле.
    """
    since = _window_start(now)
    attempts = []

    test_results = TestResult.objects.filter(
        student=student, test__lesson=lesson,
        analytics_data_quality__in=USABLE_QUALITY,
        max_points__gt=0, created_at__gte=since,
    ).only('earned_points', 'max_points', 'created_at')

    for r in test_results:
        attempts.append(AttemptData(
            earned_points=float(r.earned_points),
            max_points=float(r.max_points),
            activity_type='mini_check',
            completed_at=r.created_at,
        ))

    submissions = HomeworkSubmission.objects.filter(
        student=student, homework__lesson=lesson,
        analytics_data_quality__in=USABLE_QUALITY,
        max_points__gt=0, checked_at__gte=since,
    ).only('earned_points', 'max_points', 'checked_at')

    for s in submissions:
        attempts.append(AttemptData(
            earned_points=float(s.earned_points),
            max_points=float(s.max_points),
            activity_type='homework',
            completed_at=s.checked_at,
        ))

    return attempts


def get_course_attempts_by_lesson(student, course, now=None) -> dict[int, list[AttemptData]]:
    """
    Попытки по всем урокам курса разом — три запроса вместо N.
    Используется страницей аналитики, где нужен разрез по темам.
    """
    since = _window_start(now)
    by_lesson = defaultdict(list)

    test_results = TestResult.objects.filter(
        student=student, test__lesson__course=course,
        analytics_data_quality__in=USABLE_QUALITY,
        max_points__gt=0, created_at__gte=since,
    ).values('test__lesson_id', 'earned_points', 'max_points', 'created_at')

    for r in test_results:
        by_lesson[r['test__lesson_id']].append(AttemptData(
            earned_points=float(r['earned_points']),
            max_points=float(r['max_points']),
            activity_type='mini_check',
            completed_at=r['created_at'],
        ))

    submissions = HomeworkSubmission.objects.filter(
        student=student, homework__lesson__course=course,
        analytics_data_quality__in=USABLE_QUALITY,
        max_points__gt=0, checked_at__gte=since,
    ).values('homework__lesson_id', 'earned_points', 'max_points', 'checked_at')

    for s in submissions:
        by_lesson[s['homework__lesson_id']].append(AttemptData(
            earned_points=float(s['earned_points']),
            max_points=float(s['max_points']),
            activity_type='homework',
            completed_at=s['checked_at'],
        ))

    return dict(by_lesson)


def get_course_attempts(student, course, now=None) -> list[AttemptData]:
    """Все попытки курса плоским списком, включая пробники."""
    since = _window_start(now)
    attempts = []

    for lesson_attempts in get_course_attempts_by_lesson(student, course, now).values():
        attempts.extend(lesson_attempts)

    exam_attempts = ExamAttempt.objects.filter(
        student=student, exam__course=course,
        analytics_data_quality__in=USABLE_QUALITY,
        max_points__gt=0, submitted_at__gte=since,
    ).values('earned_points', 'max_points', 'submitted_at')

    for e in exam_attempts:
        attempts.append(AttemptData(
            earned_points=float(e['earned_points']),
            max_points=float(e['max_points']),
            activity_type='mock_exam',
            completed_at=e['submitted_at'],
        ))

    return attempts


def get_program_progress_counts(student, course) -> tuple[int, int]:
    """
    (выполнено обязательных, всего обязательных).
    Обязательные элементы: урок, тест урока, домашка урока.
    """
    lessons = list(course.lessons.values_list('id', flat=True))
    if not lessons:
        return 0, 0

    total = len(lessons)
    completed = LessonProgress.objects.filter(
        student=student, lesson_id__in=lessons
    ).count()

    tests_total = Lesson.objects.filter(
        id__in=lessons, test__isnull=False
    ).count()
    tests_passed = TestResult.objects.filter(
        student=student, test__lesson_id__in=lessons, passed=True
    ).values('test_id').distinct().count()

    homework_total = Homework.objects.filter(lesson_id__in=lessons).count()
    homework_done = HomeworkSubmission.objects.filter(
        student=student, homework__lesson_id__in=lessons, status='checked'
    ).values('homework_id').distinct().count()

    return (
        completed + tests_passed + homework_done,
        total + tests_total + homework_total,
    )


def get_error_stats(student, course=None) -> dict:
    """Разбивка ошибок по статусам для errorCorrectionRate (ТЗ 15.9)."""
    qs = ErrorRecord.objects.filter(student=student)
    if course:
        qs = qs.filter(lesson__course=course)

    rows = qs.values('status').annotate(n=Count('id'))
    counts = {row['status']: row['n'] for row in rows}

    return {
        'not_analyzed': counts.get(ErrorStatus.NOT_ANALYZED, 0),
        'in_progress': counts.get(ErrorStatus.IN_PROGRESS, 0),
        'corrected_once': counts.get(ErrorStatus.CORRECTED_ONCE, 0),
        'reinforced': counts.get(ErrorStatus.REINFORCED, 0),
        'regressed': counts.get(ErrorStatus.REGRESSED, 0),
        'total': sum(counts.values()),
    }


def get_plan_counts(student, period_start=None, period_end=None) -> dict:
    """
    Счётчики для plan_adherence. Отменённые считаются отдельно —
    они вычитаются из знаменателя (ТЗ 15.10).
    """
    qs = PlanItem.objects.filter(plan__student=student, required=True)
    if period_start:
        qs = qs.filter(due_at__gte=period_start)
    if period_end:
        qs = qs.filter(due_at__lte=period_end)

    rows = qs.values('status').annotate(n=Count('id'))
    counts = {row['status']: row['n'] for row in rows}

    cancelled = sum(counts.get(s, 0) for s in PlanStatus.cancelled())

    return {
        'total_due': sum(counts.values()),
        'completed_on_time': counts.get(PlanStatus.DONE_ON_TIME, 0),
        'completed_late': counts.get(PlanStatus.DONE_LATE, 0),
        'overdue': counts.get(PlanStatus.OVERDUE, 0),
        'skipped': counts.get(PlanStatus.SKIPPED, 0),
        'cancelled': cancelled,
    }


def get_study_time(student, since=None) -> dict:
    """Активное время: сегодня, неделя, месяц."""
    now = timezone.now()
    today = now.date()

    def total(start_date):
        result = StudySession.objects.filter(
            student=student, start_at__date__gte=start_date
        ).aggregate(s=Sum('active_seconds'))
        return result['s'] or 0

    return {
        'today_seconds': total(today),
        'week_seconds': total(today - timedelta(days=6)),
        'month_seconds': total(today - timedelta(days=29)),
    }


def get_active_days(student, days=60) -> set[date]:
    """Дни с учебной активностью — для расчёта серии."""
    since = timezone.now().date() - timedelta(days=days)
    return set(
        StudySession.objects
        .filter(student=student, start_at__date__gte=since, active_seconds__gt=0)
        .values_list('start_at__date', flat=True)
    )


def get_enrolled_courses(student):
    """Курсы с одобренной заявкой, одним запросом со связями."""
    return (
        Course.objects
        .filter(enrollments__student=student,
                enrollments__status=Enrollment.STATUS_APPROVED)
        .select_related('subject_ref')
        .prefetch_related('modules', 'lessons')
        .distinct()
    )

"""
Сборка страницы «Результаты» (ТЗ 14).
Все показатели берутся из единого расчётного слоя — своих формул здесь нет.
"""
from dataclasses import dataclass, field

from django.utils import timezone

from . import analytics_repository as repo
from .analytics import (
    accuracy, classify_topic, confidence_label, error_correction_rate,
    error_rate, mastery_confidence, mastery_label, plan_adherence,
    program_progress, score_trend, stability, topic_mastery,
)
from .study_time import current_streak


@dataclass
class TopicRow:
    lesson: object
    mastery: int | None
    label: str
    confidence: int
    status: str
    attempts: int

    @property
    def is_reliable(self) -> bool:
        return self.confidence >= 30


@dataclass
class CourseAnalytics:
    course: object
    subject_name: str
    progress_percent: int
    completed: int
    total: int
    accuracy_percent: int | None
    error_percent: int | None
    topics: list = field(default_factory=list)
    weak_topics: list = field(default_factory=list)
    strong_topics: list = field(default_factory=list)


@dataclass
class AnalyticsData:
    courses: list = field(default_factory=list)
    has_data: bool = False

    # Сводные показатели
    overall_accuracy: int | None = None
    errors: dict = field(default_factory=dict)
    correction_percent: int = 0
    trend: float | None = None
    stability_label: str = 'Мало данных'
    stability_value: float | None = None
    adherence: int | None = None
    plan_counts: dict = field(default_factory=dict)

    # Время и активность
    today_minutes: int = 0
    week_minutes: int = 0
    month_minutes: int = 0
    streak_days: int = 0

    # Прогноз
    prediction_available: bool = False
    predicted_score: int | None = None


def _topic_rows(student, course, now):
    """Освоение по каждой теме курса."""
    attempts_by_lesson = repo.get_course_attempts_by_lesson(student, course, now)
    lessons = {l.id: l for l in course.lessons.select_related('module').all()}

    rows = []
    for lesson_id, attempts in attempts_by_lesson.items():
        lesson = lessons.get(lesson_id)
        if not lesson:
            continue
        mastery = topic_mastery(attempts, now)
        confidence = mastery_confidence(attempts, now)
        rows.append(TopicRow(
            lesson=lesson,
            mastery=int(mastery) if mastery is not None else None,
            label=mastery_label(mastery, confidence),
            confidence=int(confidence),
            status=classify_topic(mastery, confidence),
            attempts=len(attempts),
        ))

    rows.sort(key=lambda r: (r.mastery if r.mastery is not None else 999))
    return rows


def _recent_scores(student, days=14, now=None):
    """Проценты последних результатов для тренда и стабильности."""
    from datetime import timedelta

    from school.models import TestResult

    now = now or timezone.now()
    since = now - timedelta(days=days)
    return list(
        TestResult.objects
        .filter(student=student, created_at__gte=since)
        .order_by('created_at')
        .values_list('score', flat=True)
    )


def build_analytics(student, now=None) -> AnalyticsData:
    now = now or timezone.now()
    courses = list(repo.get_enrolled_courses(student))

    if not courses:
        return AnalyticsData(has_data=False)

    course_blocks = []
    all_attempts = []

    for course in courses:
        done, total = repo.get_program_progress_counts(student, course)
        attempts = repo.get_course_attempts(student, course, now)
        all_attempts.extend(attempts)

        topics = _topic_rows(student, course, now)
        course_accuracy = accuracy(attempts)

        course_blocks.append(CourseAnalytics(
            course=course,
            subject_name=(
                course.subject_ref.name if course.subject_ref else course.subject
            ),
            progress_percent=int(program_progress(done, total)),
            completed=done,
            total=total,
            accuracy_percent=int(course_accuracy) if course_accuracy is not None else None,
            error_percent=(
                int(error_rate(attempts)) if error_rate(attempts) is not None else None
            ),
            topics=topics,
            weak_topics=[t for t in topics if t.status in ('weak', 'critical')],
            strong_topics=[t for t in topics if t.status == 'strong'],
        ))

    # Сводные
    overall = accuracy(all_attempts)
    error_stats = repo.get_error_stats(student)
    plan_counts = repo.get_plan_counts(student)
    study_time = repo.get_study_time(student)

    last_14 = [float(s) for s in _recent_scores(student, 14, now)]
    prev_14 = [
        float(s) for s in _recent_scores(student, 28, now)[:-len(last_14)]
    ] if last_14 else []

    sd_value, sd_label = stability(last_14)

    return AnalyticsData(
        courses=course_blocks,
        has_data=bool(all_attempts) or bool(error_stats.get('total')),
        overall_accuracy=int(overall) if overall is not None else None,
        errors=error_stats,
        correction_percent=int(error_correction_rate(
            error_stats.get('reinforced', 0), error_stats.get('total', 0)
        )),
        trend=score_trend(last_14, prev_14),
        stability_label=sd_label,
        stability_value=sd_value,
        adherence=(
            int(plan_adherence(
                plan_counts['completed_on_time'],
                plan_counts['total_due'],
                plan_counts['cancelled'],
            )) if plan_counts['total_due'] else None
        ),
        plan_counts=plan_counts,
        today_minutes=study_time['today_seconds'] // 60,
        week_minutes=study_time['week_seconds'] // 60,
        month_minutes=study_time['month_seconds'] // 60,
        streak_days=current_streak(repo.get_active_days(student), now.date()),
        prediction_available=False,
    )
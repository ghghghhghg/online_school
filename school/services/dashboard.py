"""
Сборка данных Главной страницы.
Вьюха только вызывает build_dashboard() и отдаёт результат в шаблон (ТЗ 24.3).
"""
from dataclasses import dataclass, field

from django.utils import timezone

from . import analytics_repository as repo
from .analytics import (
    classify_topic, confidence_label, mastery_confidence, mastery_label,
    program_progress, topic_mastery,
)
from .recommendations import build_day_state


@dataclass
class CourseProgressCard:
    course: object
    percent: int
    completed: int
    total: int
    subject_name: str
    best_score: int | None = None


@dataclass
class WeakTopicCard:
    lesson: object
    mastery: int
    label: str
    confidence: int
    is_reliable: bool


@dataclass
class DashboardData:
    day_state: object
    courses: list = field(default_factory=list)
    weak_topics: list = field(default_factory=list)
    best_score: int | None = None
    has_courses: bool = False
    prediction_available: bool = False


def _weak_topics_for_course(student, course, now, limit=3):
    """Слабые темы курса с учётом достоверности (ТЗ 16)."""
    attempts_by_lesson = repo.get_course_attempts_by_lesson(student, course, now)
    if not attempts_by_lesson:
        return []

    lessons = {l.id: l for l in course.lessons.all()}
    result = []

    for lesson_id, attempts in attempts_by_lesson.items():
        lesson = lessons.get(lesson_id)
        if not lesson:
            continue
        mastery = topic_mastery(attempts, now)
        if mastery is None:
            continue
        confidence = mastery_confidence(attempts, now)
        status = classify_topic(mastery, confidence)
        if status not in ('weak', 'critical', 'insufficient_data'):
            continue
        result.append(WeakTopicCard(
            lesson=lesson,
            mastery=int(mastery),
            label=mastery_label(mastery, confidence),
            confidence=int(confidence),
            is_reliable=confidence >= 30,
        ))

    result.sort(key=lambda t: t.mastery)
    return result[:limit]


def build_dashboard(student, now=None) -> DashboardData:
    now = now or timezone.now()

    courses = list(repo.get_enrolled_courses(student))
    if not courses:
        return DashboardData(
            day_state=build_day_state([], 0, 0),
            has_courses=False,
        )

    course_cards = []
    weak_topics = []

    for course in courses:
        done, total = repo.get_program_progress_counts(student, course)
        course_cards.append(CourseProgressCard(
            course=course,
            percent=int(program_progress(done, total)),
            completed=done,
            total=total,
            subject_name=(
                course.subject_ref.name if course.subject_ref else course.subject
            ),
        ))
        weak_topics.extend(_weak_topics_for_course(student, course, now))

    weak_topics.sort(key=lambda t: t.mastery)

    candidates = repo.build_recommendation_candidates(student, now)
    completed_today, total_today = repo.get_today_task_counts(student, now)

    return DashboardData(
        day_state=build_day_state(candidates, completed_today, total_today),
        courses=course_cards,
        weak_topics=weak_topics[:3],
        best_score=repo.get_best_mock_result(student),
        has_courses=True,
        prediction_available=False,  # включится после внесения шкал и накопления данных
    )
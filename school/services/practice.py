"""
Практика: подбор заданий по режимам и проверка ответов (ТЗ 9).
"""
from dataclasses import dataclass

from django.db.models import Q
from django.utils import timezone

DEFAULT_TASK_COUNT = 7
MAX_TASK_COUNT = 20


@dataclass(frozen=True)
class ModeDescription:
    code: str
    title: str
    description: str
    icon: str


MODE_DESCRIPTIONS = [
    ModeDescription('recommended', 'Персональная подборка',
                    'Задания по вашим слабым местам и ошибкам', 'target'),
    ModeDescription('errors', 'Работа над ошибками',
                    'Задания на темы, где вы ошибались', 'refresh'),
    ModeDescription('weak', 'Слабые темы',
                    'То, что освоено хуже всего', 'flag'),
    ModeDescription('topic', 'По теме',
                    'Выберите конкретную тему курса', 'book'),
    ModeDescription('mixed', 'Смешанная',
                    'Случайные задания по всему курсу', 'grid'),
]


def _bank_queryset():
    from school.models import Question
    return (
        Question.objects
        .filter(is_in_bank=True)
        .prefetch_related('answers')
        .select_related('lesson', 'test__lesson')
    )


def select_tasks(student, mode, course=None, lesson=None,
                 exam_task_number=None, count=DEFAULT_TASK_COUNT, now=None):
    """
    Подбирает задания под режим. Возвращает список Question.
    Пустой список означает, что банк не наполнен под этот запрос.
    """
    from school.models import ErrorRecord, ErrorStatus
    from . import analytics_repository as repo
    from .analytics import classify_topic, mastery_confidence, topic_mastery

    now = now or timezone.now()
    count = min(count, MAX_TASK_COUNT)
    qs = _bank_queryset()

    if course:
        qs = qs.filter(
            Q(lesson__course=course) | Q(test__lesson__course=course)
        )

    if mode == 'topic' and lesson:
        return list(qs.filter(
            Q(lesson=lesson) | Q(test__lesson=lesson)
        ).order_by('?')[:count])

    if mode == 'exam_number' and exam_task_number:
        return list(qs.filter(exam_task_number=exam_task_number).order_by('?')[:count])

    if mode == 'errors':
        error_lessons = set(
            ErrorRecord.objects
            .filter(student=student)
            .exclude(status=ErrorStatus.REINFORCED)
            .values_list('lesson_id', flat=True)
        )
        error_lessons.discard(None)
        if not error_lessons:
            return []
        return list(qs.filter(
            Q(lesson_id__in=error_lessons) | Q(test__lesson_id__in=error_lessons)
        ).order_by('?')[:count])

    if mode in ('weak', 'recommended'):
        weak_lessons = []
        courses = [course] if course else list(repo.get_enrolled_courses(student))
        for c in courses:
            by_lesson = repo.get_course_attempts_by_lesson(student, c, now)
            for lesson_id, attempts in by_lesson.items():
                mastery = topic_mastery(attempts, now)
                confidence = mastery_confidence(attempts, now)
                if classify_topic(mastery, confidence) in ('weak', 'critical'):
                    weak_lessons.append(lesson_id)

        if mode == 'recommended':
            error_lessons = set(
                ErrorRecord.objects
                .filter(student=student)
                .exclude(status=ErrorStatus.REINFORCED)
                .values_list('lesson_id', flat=True)
            )
            error_lessons.discard(None)
            weak_lessons = list(set(weak_lessons) | error_lessons)

        if not weak_lessons:
            return list(qs.order_by('?')[:count])

        return list(qs.filter(
            Q(lesson_id__in=weak_lessons) | Q(test__lesson_id__in=weak_lessons)
        ).order_by('?')[:count])

    if mode == 'review':
        review_lessons = set(
            ErrorRecord.objects
            .filter(student=student, status=ErrorStatus.CORRECTED_ONCE)
            .values_list('lesson_id', flat=True)
        )
        review_lessons.discard(None)
        if not review_lessons:
            return []
        return list(qs.filter(
            Q(lesson_id__in=review_lessons) | Q(test__lesson_id__in=review_lessons)
        ).order_by('?')[:count])

    return list(qs.order_by('?')[:count])


def create_session(student, mode, course=None, lesson=None,
                   exam_task_number=None, count=DEFAULT_TASK_COUNT):
    """Создаёт сессию с набором заданий. None — если заданий не нашлось."""
    from school.models import PracticeAnswer, PracticeSession

    tasks = select_tasks(
        student, mode, course=course, lesson=lesson,
        exam_task_number=exam_task_number, count=count,
    )
    if not tasks:
        return None

    session = PracticeSession.objects.create(
        student=student, course=course, lesson=lesson,
        mode=mode, exam_task_number=exam_task_number,
    )
    PracticeAnswer.objects.bulk_create([
        PracticeAnswer(session=session, question=q, order=i)
        for i, q in enumerate(tasks, start=1)
    ])
    return session


def submit_answer(practice_answer, payload, time_spent=0):
    """
    Проверяет ответ, записывает баллы, двигает статусы ошибок.
    Возвращает (верно, набранные_баллы, максимум).

    Идемпотентно (ТЗ 4.8): повторный POST по уже отвеченному заданию
    возвращает сохранённый результат и не трогает статусы ошибок —
    иначе двойное нажатие удвоило бы этапы закрепления ошибки.
    """
    from decimal import Decimal

    from .scoring import register_practice_error, resolve_practice_error

    if practice_answer.answered_at is not None:
        return (
            practice_answer.is_correct,
            float(practice_answer.earned_points or 0),
            float(practice_answer.max_points or 0),
        )

    question = practice_answer.question
    is_correct, earned = question.check_answer(payload)
    max_points = float(question.points or 1)

    practice_answer.student_answer = (
        ', '.join(str(p) for p in payload) if isinstance(payload, (list, tuple))
        else str(payload)
    )
    practice_answer.is_correct = is_correct
    practice_answer.earned_points = Decimal(str(earned))
    practice_answer.max_points = Decimal(str(max_points))
    practice_answer.answered_at = timezone.now()
    practice_answer.time_spent_seconds = max(0, min(time_spent, 3600))
    practice_answer.save()

    session = practice_answer.session
    if is_correct:
        resolve_practice_error(session.student, question, session.session_key)
    else:
        register_practice_error(session.student, question, session)

    return is_correct, earned, max_points


def skip_answer(practice_answer):
    """Пропуск задания. Уже отвеченное задание не перезаписывается (ТЗ 4.8)."""
    if practice_answer.answered_at is not None:
        return

    practice_answer.skipped = True
    practice_answer.answered_at = timezone.now()
    practice_answer.earned_points = 0
    practice_answer.max_points = practice_answer.question.points or 1
    practice_answer.save()


def finish_session(session):
    """
    Подводит итог сессии, записывает первичные баллы.

    Идемпотентно (ТЗ 4.8): у завершённой сессии дата не переписывается,
    иначе повторное нажатие омолодило бы попытку в recencyWeight.
    """
    from decimal import Decimal

    if session.finished_at is not None:
        return (
            float(session.earned_points or 0),
            float(session.max_points or 0),
        )

    answered = session.answers.filter(answered_at__isnull=False)
    earned = sum(float(a.earned_points or 0) for a in answered)
    maximum = sum(float(a.max_points or 0) for a in answered)

    session.earned_points = Decimal(str(earned))
    session.max_points = Decimal(str(maximum))
    session.analytics_data_quality = 'exact'
    session.finished_at = timezone.now()
    session.save(update_fields=[
        'earned_points', 'max_points', 'analytics_data_quality', 'finished_at',
    ])
    return earned, maximum
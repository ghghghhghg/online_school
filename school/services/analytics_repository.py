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
    StudySession, TestResult, ExamMock, TestAnswerLog, PracticeAnswer, Question,
)
from .analytics import AttemptData
from .constants import MASTERY_WINDOW_DAYS
from .recommendations import PRIORITY_NEAREST_DEADLINE, PRIORITY_REQUIRED_UNDATED, PRIORITY_PLANNED_TODAY

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


def build_recommendation_candidates(student, now=None) -> list:
    """
    Собирает кандидатов для движка рекомендаций из реальных данных.
    Здесь — только выборки и построение DTO, ранжирование в recommendations.py.
    """
    from django.urls import reverse

    from school.models import Enrollment, ExamAttempt, HomeworkSubmission
    from .recommendations import (
        ActionType, PRIORITY_CRITICAL_ERROR, PRIORITY_EXTRA_PRACTICE,
        PRIORITY_NEXT_TOPIC, PRIORITY_OVERDUE_REQUIRED, PRIORITY_STARTED_REQUIRED,
        Recommendation,
    )

    now = now or timezone.now()
    candidates = []

    courses = list(get_enrolled_courses(student))
    if not courses:
        return []

    course_ids = [c.id for c in courses]
    course_by_id = {c.id: c for c in courses}

    # 1. Незавершённый пробник — начатая обязательная работа
    unfinished = (
        ExamAttempt.objects
        .filter(student=student, submitted_at__isnull=True, exam__course_id__in=course_ids)
        .select_related('exam', 'exam__course')
    )
    for attempt in unfinished:
        candidates.append(Recommendation(
            action_type=ActionType.CONTINUE_MOCK,
            priority=PRIORITY_STARTED_REQUIRED,
            title=attempt.exam.title,
            reason='Вы начали пробник и не завершили его',
            url=reverse('exam_attempt', kwargs={'pk': attempt.pk}),
            course_title=attempt.exam.course.title,
            estimated_minutes=attempt.exam.duration_minutes,
        ))

    # 2. Несданные домашние работы
    submitted_ids = set(
        HomeworkSubmission.objects
        .filter(student=student, homework__lesson__course_id__in=course_ids)
        .values_list('homework_id', flat=True)
    )
    pending_homework = (
        Homework.objects
        .filter(lesson__course_id__in=course_ids)
        .exclude(id__in=submitted_ids)
        .select_related('lesson', 'lesson__course')[:5]
    )
    for hw in pending_homework:
        due_at = getattr(hw, 'due_at', None)
        if due_at and due_at < now:
            priority = PRIORITY_OVERDUE_REQUIRED
            reason = f'Срок сдачи истёк {due_at:%d.%m}'
        elif due_at:
            priority = PRIORITY_NEAREST_DEADLINE
            reason = f'Сдать до {due_at:%d.%m}'
        else:
            priority = PRIORITY_REQUIRED_UNDATED
            reason = f'Домашняя работа к уроку «{hw.lesson.title}» ещё не сдана'

        candidates.append(Recommendation(
            action_type=ActionType.SUBMIT_HOMEWORK,
            priority=priority,
            title=hw.title,
            reason=reason,
            url=reverse('homework', kwargs={'pk': hw.lesson.pk}),
            course_title=hw.lesson.course.title,
            estimated_minutes=30,
            due_at=due_at,
        ))

    # 3. Неразобранные ошибки
    unresolved = (
        ErrorRecord.objects
        .filter(student=student, status__in=[
            ErrorStatus.NOT_ANALYZED, ErrorStatus.REGRESSED,
        ])
        .select_related('lesson', 'lesson__course')
    )
    error_count = unresolved.count()
    if error_count:
        first = unresolved.first()
        repeated = unresolved.filter(repeated_count__gte=2).count()
        reason = (
            f'Одна и та же ошибка повторилась несколько раз'
            if repeated else
            f'Накопилось ошибок для разбора: {error_count}'
        )
        candidates.append(Recommendation(
            action_type=ActionType.REVIEW_ERRORS,
            priority=PRIORITY_CRITICAL_ERROR,
            title='Работа над ошибками',
            reason=reason,
            url=reverse('error_notebook'),
            course_title=first.lesson.course.title if first and first.lesson else '',
            estimated_minutes=min(60, error_count * 5),
            task_count=error_count,
        ))

    # 4. Следующий непройденный урок в каждом курсе
    completed_lesson_ids = set(
        LessonProgress.objects
        .filter(student=student, lesson__course_id__in=course_ids)
        .values_list('lesson_id', flat=True)
    )
    for course in courses:
        next_lesson = (
            course.lessons
            .exclude(id__in=completed_lesson_ids)
            .order_by('module__order', 'order')
            .first()
        )
        if not next_lesson:
            continue
        candidates.append(Recommendation(
            action_type=ActionType.WATCH_LESSON,
            priority=PRIORITY_NEXT_TOPIC,
            title=next_lesson.title,
            reason='Следующая тема программы',
            url=reverse('lesson', kwargs={'pk': next_lesson.pk}),
            subject_name=course.subject_ref.name if course.subject_ref else course.subject,
            course_title=course.title,
            estimated_minutes=20,
        ))

    # 5. Доступные пробники — дополнительная практика
    available_exams = (
        ExamMock.objects
        .filter(course_id__in=course_ids)
        .exclude(attempts__student=student)
        .select_related('course')[:2]
    )
    for exam in available_exams:
        candidates.append(Recommendation(
            action_type=ActionType.START_MOCK,
            priority=PRIORITY_EXTRA_PRACTICE,
            title=exam.title,
            reason='Проверьте себя в формате реального экзамена',
            url=reverse('exam_start', kwargs={'pk': exam.pk}),
            course_title=exam.course.title,
            estimated_minutes=exam.duration_minutes,
        ))
        # Задачи плана на сегодня
        today_items = (
            PlanItem.objects
            .filter(plan__student=student, required=True, due_at__date=now.date())
            .filter(status__in=[PlanStatus.PLANNED, PlanStatus.IN_PROGRESS])
            .select_related('plan')[:3]
        )
        for item in today_items:
            candidates.append(Recommendation(
                action_type=ActionType.PRACTICE,
                priority=PRIORITY_PLANNED_TODAY,
                title=item.title,
                reason='Задача из плана на сегодня',
                url=reverse('study_plan'),
                estimated_minutes=item.estimated_minutes,
                due_at=item.due_at,
            ))

    return candidates

def get_best_mock_result(student):
    """
    Лучший результат пробника в процентах первичных баллов.
    Именно пробник, а не мини-проверка урока: он показывает
    готовность к экзамену, а не усвоение одной темы.
    """
    from school.models import ExamAttempt

    best = (
        ExamAttempt.objects
        .filter(
            student=student,
            submitted_at__isnull=False,
            analytics_data_quality__in=PRECISE_QUALITY,
            max_points__gt=0,
        )
        .order_by('-earned_points')
        .values('earned_points', 'max_points')
        .first()
    )
    if not best:
        return None
    return int(float(best['earned_points']) / float(best['max_points']) * 100)


def get_today_task_counts(student, now=None) -> tuple[int, int]:
    """
    (выполнено сегодня, запланировано на сегодня).
    До появления раздела «План» второе значение — 0,
    поэтому состояние «план выполнен» пока не наступает.
    """
    now = now or timezone.now()
    today = now.date()

    completed = TestResult.objects.filter(
        student=student, created_at__date=today, passed=True
    ).count()
    completed += LessonProgress.objects.filter(
        student=student, completed_at__date=today
    ).count()

    planned = PlanItem.objects.filter(
        plan__student=student, required=True, due_at__date=today,
    ).exclude(status__in=PlanStatus.cancelled()).count()

    return completed, planned

def get_error_records(student, course=None, status=None, group_by='lesson'):
    """
    Ошибки ученика для экрана разбора. Группировка по теме или по типу (ТЗ 11).
    Один запрос со связями, N+1 исключён.
    """
    qs = (
        ErrorRecord.objects
        .filter(student=student)
        .select_related('lesson', 'lesson__course', 'question', 'question__test', 'subject')
        .prefetch_related('question__answers', 'correction_attempts')
    )
    if course:
        qs = qs.filter(lesson__course=course)
    if status:
        qs = qs.filter(status=status)

    records = list(qs)

    groups = defaultdict(list)
    for record in records:
        if group_by == 'error_type':
            key = record.get_error_type_display()
        else:
            key = record.lesson.title if record.lesson else 'Без темы'
        groups[key].append(record)

    return [
        {'title': title, 'records': items, 'count': len(items)}
        for title, items in sorted(groups.items(), key=lambda kv: -len(kv[1]))
    ]


def get_error_record_for_student(student, pk):
    """Одна ошибка с полным контекстом."""
    return (
        ErrorRecord.objects
        .filter(student=student, pk=pk)
        .select_related('lesson', 'lesson__course', 'question', 'question__test')
        .prefetch_related('question__answers', 'correction_attempts')
        .first()
    )

def get_task_max_points_by_number(course):
    """
    Максимум баллов за каждый номер задания ЕГЭ — по банку заданий курса.
    Берётся наибольший points среди вопросов с этим номером
    (разные формулировки одного номера обычно равнозначны).
    """
    from django.db.models import Max

    rows = (
        Question.objects
        .filter(
            Q(lesson__course=course) | Q(test__lesson__course=course),
            exam_task_number__isnull=False,
        )
        .values('exam_task_number')
        .annotate(max_points=Max('points'))
    )
    return {row['exam_task_number']: float(row['max_points']) for row in rows}


def get_attempts_by_exam_number(student, course, now=None):
    """
    Агрегированные earned/max по каждому номеру задания —
    из практики и мини-проверок вместе.
    """
    since = _window_start(now)
    result = defaultdict(lambda: {'earned': 0.0, 'max': 0.0})

    practice_rows = (
        PracticeAnswer.objects
        .filter(
            session__student=student,
            question__exam_task_number__isnull=False,
            answered_at__isnull=False,
            answered_at__gte=since,
        )
        .filter(
            Q(question__lesson__course=course) | Q(question__test__lesson__course=course)
        )
        .values('question__exam_task_number', 'earned_points', 'max_points')
    )
    for row in practice_rows:
        n = row['question__exam_task_number']
        result[n]['earned'] += float(row['earned_points'] or 0)
        result[n]['max'] += float(row['max_points'] or 0)

    log_rows = (
        TestAnswerLog.objects
        .filter(
            result__student=student,
            question__exam_task_number__isnull=False,
            result__test__lesson__course=course,
            result__created_at__gte=since,
        )
        .values('question__exam_task_number', 'earned_points', 'max_points')
    )
    for row in log_rows:
        n = row['question__exam_task_number']
        result[n]['earned'] += float(row['earned_points'] or 0)
        result[n]['max'] += float(row['max_points'] or 0)

    return dict(result)

def get_mocks_overview(student):
    """
    Пробники по всем курсам ученика с историей попыток.
    Один запрос на курс вместо N+1 на каждый пробник.
    """
    from school.models import ExamMock

    courses = list(get_enrolled_courses(student))
    course_ids = [c.id for c in courses]

    mocks = (
        ExamMock.objects
        .filter(course_id__in=course_ids)
        .select_related('course')
        .order_by('course__title', 'order')
    )

    all_attempts = (
        ExamAttempt.objects
        .filter(student=student, exam__in=mocks)
        .order_by('exam_id', 'started_at')
    )
    by_exam = defaultdict(list)
    for a in all_attempts:
        by_exam[a.exam_id].append(a)

    result = []
    for mock in mocks:
        attempts = by_exam.get(mock.id, [])
        finished = [a for a in attempts if a.submitted_at]
        unfinished = [a for a in attempts if not a.submitted_at]

        scores = []
        for a in finished:
            if a.max_points and a.max_points > 0:
                scores.append(round(float(a.earned_points) / float(a.max_points) * 100))

        trend = None
        if len(scores) >= 2:
            trend = scores[-1] - scores[-2]

        result.append({
            'mock': mock,
            'attempts': finished,
            'attempts_count': len(finished),
            'unfinished': unfinished[0] if unfinished else None,
            'best_score': max(scores) if scores else None,
            'last_score': scores[-1] if scores else None,
            'trend': trend,
        })
    return result
"""
Запись первичных баллов и регистрация ошибок при прохождении активностей.
Вьюхи вызывают эти функции, но не считают баллы сами (ТЗ 24.3).
"""
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone


def record_test_attempt(result, answers_log):
    """
    Проставляет первичные баллы результату теста.

    answers_log: [(question, chosen_answer|None, is_correct), ...]
    Возвращает (earned, max_points).
    """
    earned = Decimal('0')
    max_points = Decimal('0')

    for question, _chosen, is_correct in answers_log:
        points = Decimal(str(question.points or 1))
        max_points += points
        if is_correct:
            earned += points

    result.earned_points = earned
    result.max_points = max_points
    result.analytics_data_quality = 'exact'
    result.save(update_fields=['earned_points', 'max_points', 'analytics_data_quality'])
    return earned, max_points


def record_answer_points(log, question, is_correct):
    """Баллы отдельного ответа в логе."""
    points = Decimal(str(question.points or 1))
    log.earned_points = points if is_correct else Decimal('0')
    log.max_points = points
    log.save(update_fields=['earned_points', 'max_points'])


def register_errors(student, result, answers_log):
    """
    Создаёт или обновляет ErrorRecord по неверным ответам.
    Повтор той же ошибки увеличивает счётчик и снимает статус «Закреплено».
    """
    from school.models import ErrorRecord, ErrorType

    lesson = result.test.lesson
    subject = getattr(lesson.course, 'subject_ref', None)
    source_ct = ContentType.objects.get_for_model(result.__class__)

    created_count = 0
    for question, _chosen, is_correct in answers_log:
        if is_correct:
            continue

        record = ErrorRecord.objects.filter(student=student, question=question).first()
        if record:
            record.register_repeat()
        else:
            ErrorRecord.objects.create(
                student=student,
                subject=subject,
                lesson=lesson,
                question=question,
                source_content_type=source_ct,
                source_object_id=result.pk,
                error_type=ErrorType.UNCLASSIFIED,
            )
            created_count += 1

    return created_count


def resolve_errors_on_success(student, answers_log, session_key=''):
    """
    Верный ответ на задание, где раньше была ошибка, — попытка исправления.
    Статус «Закреплено» ставится только при выполнении всех трёх условий.
    """
    from school.models import ErrorCorrectionAttempt, ErrorRecord, ErrorStatus

    for question, _chosen, is_correct in answers_log:
        if not is_correct:
            continue

        record = ErrorRecord.objects.filter(
            student=student, question=question,
        ).exclude(status=ErrorStatus.REINFORCED).first()
        if not record:
            continue

        ErrorCorrectionAttempt.objects.create(
            error_record=record,
            is_correct=True,
            is_similar_task=True,
            session_key=session_key,
        )
        if record.status == ErrorStatus.NOT_ANALYZED:
            record.status = ErrorStatus.IN_PROGRESS
            record.save(update_fields=['status'])
        elif record.status == ErrorStatus.IN_PROGRESS:
            record.status = ErrorStatus.CORRECTED_ONCE
            record.save(update_fields=['status'])

        record.try_reinforce()


def record_checkpoint_attempt(attempt):
    """Баллы контрольной точки. Непроверенные задания оставляют попытку legacy."""
    answers = list(attempt.answers.select_related('task'))
    if not answers or any(a.passed is None for a in answers):
        return None

    earned = Decimal('0')
    max_points = Decimal('0')
    for answer in answers:
        points = Decimal(str(answer.task.points or 1))
        max_points += points
        if answer.passed:
            earned += points
        answer.earned_points = points if answer.passed else Decimal('0')
        answer.max_points = points
        answer.save(update_fields=['earned_points', 'max_points'])

    attempt.earned_points = earned
    attempt.max_points = max_points
    attempt.analytics_data_quality = 'exact'
    attempt.save(update_fields=['earned_points', 'max_points', 'analytics_data_quality'])
    return earned, max_points


def record_exam_attempt(attempt):
    """
    Баллы пробника. Если часть заданий ещё на ручной проверке —
    качество данных estimated, после проверки пересчитается в exact.
    """
    answers = list(attempt.answers.select_related('task'))
    checked = [a for a in answers if a.passed is not None]
    if not checked:
        return None

    earned = Decimal('0')
    max_points = Decimal('0')
    for answer in checked:
        points = Decimal(str(answer.task.points or 1))
        max_points += points
        if answer.passed:
            earned += points
        answer.earned_points = points if answer.passed else Decimal('0')
        answer.max_points = points
        answer.save(update_fields=['earned_points', 'max_points'])

    attempt.earned_points = earned
    attempt.max_points = max_points
    attempt.analytics_data_quality = 'exact' if len(checked) == len(answers) else 'estimated'
    attempt.save(update_fields=['earned_points', 'max_points', 'analytics_data_quality'])
    return earned, max_points


def record_homework_submission(submission):
    """
    Оценка преподавателя 0-100 — не первичные баллы ЕГЭ,
    поэтому качество данных всегда estimated.
    """
    if submission.score is not None:
        earned, max_points = Decimal(str(submission.score)), Decimal('100')
    elif submission.passed is not None:
        earned, max_points = (Decimal('1') if submission.passed else Decimal('0')), Decimal('1')
    else:
        return None

    submission.earned_points = earned
    submission.max_points = max_points
    submission.analytics_data_quality = 'estimated'
    submission.checked_at = submission.checked_at or timezone.now()
    submission.save(update_fields=[
        'earned_points', 'max_points', 'analytics_data_quality', 'checked_at',
    ])
    return earned, max_points

def register_practice_error(student, question, session):
    """Неверный ответ в практике — фиксируем или повторяем ошибку."""
    from django.contrib.contenttypes.models import ContentType

    from school.models import ErrorRecord, ErrorType

    lesson = question.effective_lesson
    subject = None
    if lesson and lesson.course_id:
        subject = getattr(lesson.course, 'subject_ref', None)

    record = ErrorRecord.objects.filter(student=student, question=question).first()
    if record:
        record.register_repeat()
        return record

    return ErrorRecord.objects.create(
        student=student,
        subject=subject,
        lesson=lesson,
        question=question,
        source_content_type=ContentType.objects.get_for_model(session.__class__),
        source_object_id=session.pk,
        error_type=ErrorType.UNCLASSIFIED,
    )


def resolve_practice_error(student, question, session_key):
    """
    Верный ответ в практике засчитывается как попытка исправления
    по этой же теме — механика закрепления из ТЗ 11.
    """
    from school.models import ErrorCorrectionAttempt, ErrorRecord, ErrorStatus

    lesson = question.effective_lesson
    if not lesson:
        return

    records = (
        ErrorRecord.objects
        .filter(student=student, lesson=lesson)
        .exclude(status=ErrorStatus.REINFORCED)
    )

    for record in records:
        is_same_task = record.question_id == question.id
        ErrorCorrectionAttempt.objects.create(
            error_record=record,
            is_correct=True,
            is_similar_task=not is_same_task or True,
            session_key=session_key,
        )
        if record.status == ErrorStatus.NOT_ANALYZED:
            record.status = ErrorStatus.IN_PROGRESS
            record.save(update_fields=['status'])
        elif record.status == ErrorStatus.IN_PROGRESS:
            record.status = ErrorStatus.CORRECTED_ONCE
            record.save(update_fields=['status'])
        record.try_reinforce()
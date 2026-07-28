from decimal import Decimal

from django.db import migrations

BATCH = 500


def backfill_test_results(apps, schema_editor):
    """
    Ветви восстановления (ТЗ-уточнение 5):
      A reconstructed — есть логи ответов, баллы точны;
      B estimated     — логов нет, но известно число вопросов;
      C legacy        — восстановить нечем.
    """
    TestResult = apps.get_model('school', 'TestResult')
    Question = apps.get_model('school', 'Question')

    # Суммы баллов по тестам одним запросом
    test_totals = {}
    for test_id, points in Question.objects.values_list('test_id', 'points'):
        test_totals[test_id] = test_totals.get(test_id, 0) + (points or 1)

    updated = []
    queryset = (
        TestResult.objects
        .filter(analytics_data_quality='legacy', earned_points__isnull=True)
        .prefetch_related('answer_logs__question')
    )

    for result in queryset.iterator(chunk_size=BATCH):
        logs = list(result.answer_logs.all())

        if logs:
            # A: считаем по фактическим ответам
            max_points = sum((log.question.points or 1) for log in logs)
            earned = sum(
                (log.question.points or 1) for log in logs if log.is_correct
            )
            quality = 'reconstructed'
        elif test_totals.get(result.test_id):
            # B: восстанавливаем из процента
            max_points = test_totals[result.test_id]
            earned = round(max_points * (result.score or 0) / 100, 2)
            quality = 'estimated'
        else:
            # C: данных нет — оставляем пустыми
            continue

        if max_points <= 0:
            continue

        result.earned_points = Decimal(str(earned))
        result.max_points = Decimal(str(max_points))
        result.analytics_data_quality = quality
        updated.append(result)

        if len(updated) >= BATCH:
            TestResult.objects.bulk_update(
                updated, ['earned_points', 'max_points', 'analytics_data_quality']
            )
            updated = []

    if updated:
        TestResult.objects.bulk_update(
            updated, ['earned_points', 'max_points', 'analytics_data_quality']
        )


def backfill_checkpoint_attempts(apps, schema_editor):
    """
    Контрольные точки: passed=None означает «на проверке», а не «неверно».
    Такие попытки остаются legacy, иначе освоение занизится.
    """
    CheckpointAttempt = apps.get_model('school', 'CheckpointAttempt')

    updated = []
    queryset = (
        CheckpointAttempt.objects
        .filter(analytics_data_quality='legacy', earned_points__isnull=True)
        .prefetch_related('answers__task')
    )

    for attempt in queryset.iterator(chunk_size=BATCH):
        answers = list(attempt.answers.all())
        if not answers:
            continue
        if any(a.passed is None for a in answers):
            continue  # ещё проверяется преподавателем

        max_points = sum((a.task.points or 1) for a in answers)
        earned = sum((a.task.points or 1) for a in answers if a.passed)
        if max_points <= 0:
            continue

        attempt.earned_points = Decimal(str(earned))
        attempt.max_points = Decimal(str(max_points))
        attempt.analytics_data_quality = 'reconstructed'
        updated.append(attempt)

        if len(updated) >= BATCH:
            CheckpointAttempt.objects.bulk_update(
                updated, ['earned_points', 'max_points', 'analytics_data_quality']
            )
            updated = []

    if updated:
        CheckpointAttempt.objects.bulk_update(
            updated, ['earned_points', 'max_points', 'analytics_data_quality']
        )


def backfill_exam_attempts(apps, schema_editor):
    """Пробники: считаем только по автопроверяемым заданиям с известным passed."""
    ExamAttempt = apps.get_model('school', 'ExamAttempt')

    updated = []
    queryset = (
        ExamAttempt.objects
        .filter(analytics_data_quality='legacy', earned_points__isnull=True,
                submitted_at__isnull=False)
        .prefetch_related('answers__task')
    )

    for attempt in queryset.iterator(chunk_size=BATCH):
        answers = [a for a in attempt.answers.all() if a.passed is not None]
        if not answers:
            continue

        max_points = sum((a.task.points or 1) for a in answers)
        earned = sum((a.task.points or 1) for a in answers if a.passed)
        if max_points <= 0:
            continue

        # Часть заданий может быть ещё не проверена — данные неполные
        total_answers = attempt.answers.count()
        quality = 'reconstructed' if len(answers) == total_answers else 'estimated'

        attempt.earned_points = Decimal(str(earned))
        attempt.max_points = Decimal(str(max_points))
        attempt.analytics_data_quality = quality
        updated.append(attempt)

        if len(updated) >= BATCH:
            ExamAttempt.objects.bulk_update(
                updated, ['earned_points', 'max_points', 'analytics_data_quality']
            )
            updated = []

    if updated:
        ExamAttempt.objects.bulk_update(
            updated, ['earned_points', 'max_points', 'analytics_data_quality']
        )


def backfill_homework(apps, schema_editor):
    """
    HomeworkSubmission.score — оценка преподавателя 0–100, не первичные баллы ЕГЭ.
    Помечаем estimated; в прогноз первичного балла такие данные не пойдут (3.2.6).
    """
    HomeworkSubmission = apps.get_model('school', 'HomeworkSubmission')

    updated = []
    queryset = HomeworkSubmission.objects.filter(
        analytics_data_quality='legacy',
        earned_points__isnull=True,
        status='checked',
    )

    for submission in queryset.iterator(chunk_size=BATCH):
        if submission.score is not None:
            earned, max_points = submission.score, 100
        elif submission.passed is not None:
            earned, max_points = (1 if submission.passed else 0), 1
        else:
            continue

        submission.earned_points = Decimal(str(earned))
        submission.max_points = Decimal(str(max_points))
        submission.analytics_data_quality = 'estimated'
        updated.append(submission)

        if len(updated) >= BATCH:
            HomeworkSubmission.objects.bulk_update(
                updated, ['earned_points', 'max_points', 'analytics_data_quality']
            )
            updated = []

    if updated:
        HomeworkSubmission.objects.bulk_update(
            updated, ['earned_points', 'max_points', 'analytics_data_quality']
        )


def backfill_all(apps, schema_editor):
    backfill_test_results(apps, schema_editor)
    backfill_checkpoint_attempts(apps, schema_editor)
    backfill_exam_attempts(apps, schema_editor)
    backfill_homework(apps, schema_editor)


def reverse_backfill(apps, schema_editor):
    """Откат: обнуляем только восстановленное, вручную внесённое не трогаем."""
    for name in ('TestResult', 'CheckpointAttempt', 'ExamAttempt', 'HomeworkSubmission'):
        model = apps.get_model('school', name)
        model.objects.filter(
            analytics_data_quality__in=['reconstructed', 'estimated']
        ).update(earned_points=None, max_points=None, analytics_data_quality='legacy')


class Migration(migrations.Migration):

    dependencies = [
        ('school', '0044_backfill_subjects'),
    ]

    operations = [
        migrations.RunPython(backfill_all, reverse_backfill),
    ]
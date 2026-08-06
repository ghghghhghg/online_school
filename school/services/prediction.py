"""
Прогноз тестового балла по номерам заданий ЕГЭ (ТЗ 15.13).

Расчёт точный: для каждого номера задания считается вероятность
получить балл на основе истории ответов именно по этому номеру.
Если у заданий не проставлен exam_task_number — прогноз недоступен,
это состояние показывается честно, а не подменяется приближением.
"""
from dataclasses import dataclass
from datetime import datetime
from django.utils import timezone

from .analytics import (
    TaskStats, confidence_label, convert_to_test_score,
    expected_primary_score, prediction_confidence,
)


@dataclass
class PredictionResult:
    available: bool
    predicted_test_score: int | None = None
    expected_primary: float | None = None
    max_primary: float | None = None
    covered_numbers: int = 0
    total_numbers: int = 0
    confidence_percent: int = 0
    confidence_label: str = 'Мало данных'
    reason: str = ''

    @property
    def coverage_percent(self) -> int:
        if not self.total_numbers:
            return 0
        return int(self.covered_numbers / self.total_numbers * 100)


def build_task_stats(attempts_by_number: dict[int, dict], task_max_points: dict[int, float]):
    """
    attempts_by_number: {номер: {'earned': X, 'max': Y}} — агрегат из репозитория
    task_max_points: {номер: сколько баллов задание даёт на реальном экзамене}
    """
    stats = []
    for number, points in task_max_points.items():
        agg = attempts_by_number.get(number) or {'earned': 0, 'max': 0}
        stats.append(TaskStats(
            max_primary_points=points,
            total_earned_points=agg['earned'],
            total_max_points=agg['max'],
        ))
    return stats


def predict_test_score(
    attempts_by_number, task_max_points, conversion_table, now: datetime | None = None,
) -> PredictionResult:
    if not task_max_points:
        return PredictionResult(
            available=False,
            reason='Заданиям курса не проставлены номера ЕГЭ',
        )

    if not conversion_table:
        return PredictionResult(
            available=False,
            reason='Не внесена шкала перевода баллов для этого предмета',
        )

    covered = sum(1 for n in task_max_points if attempts_by_number.get(n, {}).get('max', 0) > 0)
    total = len(task_max_points)

    if covered == 0:
        return PredictionResult(
            available=False,
            total_numbers=total,
            reason='Пока нет данных ни по одному номеру задания',
        )

    stats = build_task_stats(attempts_by_number, task_max_points)
    expected = expected_primary_score(stats)
    max_primary = sum(task_max_points.values())
    test_score = convert_to_test_score(expected, conversion_table)

    confidence = prediction_confidence(
        attempts_by_number, task_max_points, now or timezone.now(),
    )

    return PredictionResult(
        available=test_score is not None,
        predicted_test_score=test_score,
        expected_primary=expected,
        max_primary=max_primary,
        covered_numbers=covered,
        total_numbers=total,
        confidence_percent=int(confidence),
        confidence_label=confidence_label(confidence),
        reason='' if test_score is not None else 'Первичный балл вне диапазона шкалы',
    )
"""
Единый слой расчётов ABS SCHOOL.

Все показатели считаются здесь и только здесь (ТЗ п.24.19-24.20).
Функции чистые: принимают простые структуры, не обращаются к БД.
Слой доступа к данным — в analytics_repository.py (этап 3.2).
"""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Sequence
import logging
import math

from .constants import (
    ACTIVITY_WEIGHTS, CONFIDENCE_TARGET_ATTEMPTS, DEFAULT_ACTIVITY_WEIGHT,
    EVIDENCE_WEIGHT_CAP, MASTERY_HALF_LIFE_DAYS, MASTERY_MAX_ATTEMPTS,
    MASTERY_WINDOW_DAYS, PREDICTION_PRIOR_PROBABILITY, PREDICTION_PRIOR_STRENGTH,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AttemptData:
    """
    Одна попытка для расчёта освоения темы.
    max_points выполняет две роли и только их:
      1) знаменатель activity_score (качество ответа);
      2) источник evidence_weight (объём доказательств, ограничен сверху).
    Отдельного task_point_weight нет — он давал двойной учёт.
    """
    earned_points: float
    max_points: float
    activity_type: str
    completed_at: datetime


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


# --- 15.1 Нормализованный результат активности ---
def activity_score(earned_points: float, max_points: float) -> float | None:
    """Возвращает % или None, если max_points некорректен (ТЗ 15.1)."""
    if not max_points or max_points <= 0:
        logger.warning('activity_score: некорректный max_points=%s', max_points)
        return None
    return clamp(earned_points / max_points * 100)


# --- 15.2 Точность ---
def accuracy(attempts: Iterable[AttemptData]) -> float | None:
    total_earned = 0.0
    total_max = 0.0
    for a in attempts:
        if a.max_points and a.max_points > 0:
            total_earned += a.earned_points
            total_max += a.max_points
    if total_max <= 0:
        return None
    return clamp(total_earned / total_max * 100)


# --- 15.3 / 15.4 Прогресс программы и темы ---
def program_progress(completed_required: int, total_required: int) -> float | None:
    """
    None — программа ещё не сконфигурирована (обязательных элементов нет).
    Ноль возвращается только когда элементы есть, но ни один не выполнен (ТЗ 4.3).
    """
    if total_required <= 0:
        return None
    return clamp(completed_required / total_required * 100)


topic_progress = program_progress  # та же формула, другая область (ТЗ 15.4)


# --- 15.5 Освоение темы ---
def recency_weight(completed_at: datetime, now: datetime) -> float:
    age_days = max(0.0, (now - completed_at).total_seconds() / 86400)
    return 0.5 ** (age_days / MASTERY_HALF_LIFE_DAYS)


def evidence_weight(max_points: float) -> float:
    """Объём доказательств с потолком (ТЗ-уточнение 3)."""
    if not max_points or max_points <= 0:
        return 0.0
    return min(float(max_points), EVIDENCE_WEIGHT_CAP)


def attempt_weight(attempt: AttemptData, now: datetime) -> float:
    return (
        ACTIVITY_WEIGHTS.get(attempt.activity_type, DEFAULT_ACTIVITY_WEIGHT)
        * recency_weight(attempt.completed_at, now)
        * evidence_weight(attempt.max_points)
    )


def _relevant_attempts(attempts: Sequence[AttemptData], now: datetime) -> list[AttemptData]:
    """Окно 90 дней И не более 30 самых свежих попыток (ТЗ 15.5)."""
    in_window = [
        a for a in attempts
        if a.max_points and a.max_points > 0
        and (now - a.completed_at).days <= MASTERY_WINDOW_DAYS
    ]
    in_window.sort(key=lambda a: a.completed_at, reverse=True)
    return in_window[:MASTERY_MAX_ATTEMPTS]


def topic_mastery(attempts: Sequence[AttemptData], now: datetime) -> float | None:
    weighted_sum = 0.0
    weight_sum = 0.0
    for a in _relevant_attempts(attempts, now):
        score = activity_score(a.earned_points, a.max_points)
        if score is None:
            continue
        w = attempt_weight(a, now)
        weighted_sum += score * w
        weight_sum += w
    if weight_sum <= 0:
        return None
    return clamp(weighted_sum / weight_sum)


def mastery_confidence(attempts: Sequence[AttemptData], now: datetime) -> float:
    effective = sum(attempt_weight(a, now) for a in _relevant_attempts(attempts, now))
    return clamp(effective / CONFIDENCE_TARGET_ATTEMPTS * 100)


def confidence_label(confidence: float) -> str:
    if confidence < 30:
        return 'Мало данных'
    if confidence < 60:
        return 'Предварительная оценка'
    if confidence < 80:
        return 'Достаточно данных'
    return 'Высокая достоверность'


# --- 15.7 Уровни освоения ---
def mastery_label(mastery: float | None, confidence: float) -> str:
    if mastery is None:
        return 'Мало данных'
    if confidence < 30:
        return 'Мало данных'
    if mastery >= 85:
        return 'Уверенное освоение'
    if mastery >= 70:
        return 'Хороший уровень'
    if mastery >= 60:
        return 'Требуется закрепление'
    if mastery >= 40:
        return 'Слабая тема'
    return 'Критическая тема'


# --- 15.8 Доля ошибок ---
def error_rate(attempts: Iterable[AttemptData]) -> float | None:
    acc = accuracy(attempts)
    return None if acc is None else clamp(100 - acc)


# --- 15.9 Исправление ошибок ---
def error_correction_rate(reinforced: int, total_unique: int) -> float | None:
    """None — ошибок нет вообще, измерять нечего (ТЗ 4.3)."""
    if total_unique <= 0:
        return None
    return clamp(reinforced / total_unique * 100)


# --- 15.10 Выполнение плана ---
def plan_adherence(completed_on_time: int, total_due: int, cancelled: int = 0) -> float | None:
    """
    Отменённые задачи не ухудшают показатель (ТЗ 15.10).
    None — измеримых задач нет: план пуст или все задачи отменены (ТЗ 4.3).
    """
    effective_total = total_due - cancelled
    if effective_total <= 0:
        return None
    return clamp(completed_on_time / effective_total * 100)


@dataclass(frozen=True)
class TaskStats:
    """Агрегированная статистика по одному номеру/типу задания ЕГЭ."""
    max_primary_points: float      # сколько баллов даёт задание на экзамене
    total_earned_points: float     # набрано учеником суммарно
    total_max_points: float        # было доступно суммарно


def task_success_probability(total_earned_points: float, total_max_points: float) -> float:
    """
    Сглаживание к нейтральной оценке. Сила сглаживания зависит только
    от объёма доступных первичных баллов (ТЗ-уточнение 4).
    """
    if total_max_points <= 0:
        return PREDICTION_PRIOR_PROBABILITY
    k = PREDICTION_PRIOR_STRENGTH
    return (
        (total_earned_points + PREDICTION_PRIOR_PROBABILITY * k)
        / (total_max_points + k)
    )


def expected_primary_score(task_stats: Iterable[TaskStats]) -> float:
    total = 0.0
    for t in task_stats:
        p = task_success_probability(t.total_earned_points, t.total_max_points)
        total += t.max_primary_points * p
    return round(total, 2)


def convert_to_test_score(primary_score: float, conversion_table: dict[int, int]) -> int | None:
    """Шкала приходит из конфигурации, не хардкодится (ТЗ 13, 24.18)."""
    if not conversion_table:
        return None
    key = int(round(primary_score))
    if key in conversion_table:
        return conversion_table[key]
    available = sorted(conversion_table)
    if key < available[0]:
        return conversion_table[available[0]]
    if key > available[-1]:
        return conversion_table[available[-1]]
    lower = max(k for k in available if k <= key)
    return conversion_table[lower]


# --- 15.14 Разрыв до цели ---
def score_gap(target: int, predicted: int | None) -> tuple[int | None, str]:
    if predicted is None:
        return None, 'Недостаточно данных для прогноза'
    gap = target - predicted
    if gap <= 0:
        return gap, 'Цель достигнута по текущему прогнозу'
    if gap <= 10:
        return gap, 'Небольшой разрыв'
    if gap <= 20:
        return gap, 'Средний разрыв'
    return gap, 'Высокий разрыв'


# --- 15.15 Динамика ---
def score_trend(last_14: Sequence[float], previous_14: Sequence[float]) -> float | None:
    if not last_14 or not previous_14:
        return None
    return round(sum(last_14) / len(last_14) - sum(previous_14) / len(previous_14), 1)


# --- 15.16 Стабильность ---
def stability(scores: Sequence[float]) -> tuple[float | None, str]:
    if len(scores) < 3:
        return None, 'Мало данных'
    mean = sum(scores) / len(scores)
    variance = sum((s - mean) ** 2 for s in scores) / len(scores)
    sd = math.sqrt(variance)
    if sd < 7:
        return round(sd, 1), 'Высокая стабильность'
    if sd < 15:
        return round(sd, 1), 'Средняя стабильность'
    return round(sd, 1), 'Нестабильный результат'


# --- 15.17 Готовность к экзамену ---
def readiness_score(
    predicted_test_score: int | None,
    target_test_score: int,
    syllabus_coverage: float,
    confidence_adjusted_mastery: float,
    adherence: float,
) -> float | None:
    if predicted_test_score is None or target_test_score <= 0:
        return None
    target_attainment = clamp(predicted_test_score / target_test_score * 100)
    return round(
        0.40 * target_attainment
        + 0.25 * syllabus_coverage
        + 0.20 * confidence_adjusted_mastery
        + 0.15 * adherence,
        1,
    )


def readiness_label(score: float | None) -> str:
    if score is None:
        return 'Недостаточно данных'
    if score >= 80:
        return 'Высокая готовность'
    if score >= 65:
        return 'Хорошая готовность'
    if score >= 45:
        return 'Средняя готовность'
    return 'Требуется усилить подготовку'


# --- 16. Классификация тем ---
def classify_topic(
    mastery: float | None,
    confidence: float,
    repeated_errors: int = 0,
    successful_days: int = 0,
) -> str:
    if mastery is None or confidence < 30:
        return 'insufficient_data'
    if mastery < 40:
        return 'critical'
    if mastery < 60:
        return 'weak'
    if mastery >= 80 and confidence >= 60 and repeated_errors == 0 and successful_days >= 2:
        return 'strong'
    return 'normal'
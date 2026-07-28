"""
Учёт активного учебного времени.
Модель хранит агрегат, здесь — правила его обновления (ТЗ 15.11-15.12).
"""
from datetime import date, datetime

from .constants import (
    ACTIVE_DAY_MIN_SECONDS, ACTIVE_DAY_MIN_TASKS, SESSION_IDLE_TIMEOUT_SECONDS,
)


def seconds_to_add(last_activity_at: datetime, now: datetime) -> int:
    """
    Сколько секунд засчитать при heartbeat.
    Простой дольше таймаута не учитывается (ТЗ 15.11).
    """
    delta = (now - last_activity_at).total_seconds()
    if delta <= 0:
        return 0
    if delta > SESSION_IDLE_TIMEOUT_SECONDS:
        return 0
    return int(delta)


def is_active_day(
    active_seconds: int,
    completed_required_items: int = 0,
    solved_tasks: int = 0,
) -> bool:
    """Учебный день активен по любому из трёх критериев (ТЗ 15.12)."""
    return (
        active_seconds >= ACTIVE_DAY_MIN_SECONDS
        or completed_required_items >= 1
        or solved_tasks >= ACTIVE_DAY_MIN_TASKS
    )


def current_streak(active_days: set[date], today: date) -> int:
    """Длина серии подряд идущих активных дней, включая сегодня."""
    if today not in active_days:
        return 0
    streak, day = 0, today
    while day in active_days:
        streak += 1
        day = date.fromordinal(day.toordinal() - 1)
    return streak
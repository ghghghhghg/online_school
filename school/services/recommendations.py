"""
Единый выбор следующего действия ученика (ТЗ 17).

Здесь только ранжирование готовых кандидатов — чистая логика без ORM.
Сбор кандидатов из базы — в analytics_repository.build_recommendation_candidates().
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence


class ActionType:
    """Типы действий. Определяют текст главной кнопки (ТЗ 5)."""
    WATCH_LESSON = 'watch_lesson'
    CONTINUE_LESSON = 'continue_lesson'
    MINI_CHECK = 'mini_check'
    PRACTICE = 'practice'
    REVIEW_ERRORS = 'review_errors'
    SUBMIT_HOMEWORK = 'submit_homework'
    START_MOCK = 'start_mock'
    CONTINUE_MOCK = 'continue_mock'
    REPEAT_TOPIC = 'repeat_topic'


# Приоритеты из ТЗ 17. Меньше — важнее.
# Шаг 10 оставляет место для промежуточных правил без пересборки шкалы.
PRIORITY_OVERDUE_REQUIRED = 10      # просроченное обязательное
PRIORITY_STARTED_REQUIRED = 20      # начатая обязательная работа
PRIORITY_NEAREST_DEADLINE = 30      # задача с ближайшим дедлайном
PRIORITY_PLANNED_TODAY = 40         # запланировано на сегодня
PRIORITY_CRITICAL_ERROR = 50        # критическая ошибка
PRIORITY_REQUIRED_UNDATED = 55      # обязательное, но без срока
PRIORITY_WEAK_TOPIC = 60            # слабая тема
PRIORITY_DUE_REVIEW = 70            # повторение по сроку
PRIORITY_NEXT_TOPIC = 80            # следующая тема программы
PRIORITY_EXTRA_PRACTICE = 90        # дополнительная практика


BUTTON_LABELS = {
    ActionType.WATCH_LESSON: 'Смотреть урок',
    ActionType.CONTINUE_LESSON: 'Продолжить урок',
    ActionType.MINI_CHECK: 'Пройти мини-проверку',
    ActionType.PRACTICE: 'Решить задания',
    ActionType.REVIEW_ERRORS: 'Разобрать ошибки',
    ActionType.SUBMIT_HOMEWORK: 'Сдать домашнюю работу',
    ActionType.START_MOCK: 'Начать пробный экзамен',
    ActionType.CONTINUE_MOCK: 'Продолжить пробный экзамен',
    ActionType.REPEAT_TOPIC: 'Повторить тему',
}


@dataclass(frozen=True)
class Recommendation:
    """Одно рекомендованное действие."""
    action_type: str
    priority: int
    title: str                      # что именно: название урока, темы, работы
    reason: str                     # почему это предложено — показывается ученику
    url: str
    subject_name: str = ''
    course_title: str = ''
    estimated_minutes: int = 15
    due_at: datetime | None = None
    task_count: int = 0             # для «Решить 7 заданий»

    @property
    def button_label(self) -> str:
        """Текст главной кнопки. Никаких универсальных «Продолжить» (ТЗ 5)."""
        if self.action_type == ActionType.PRACTICE and self.task_count:
            return f'Решить {self.task_count} {_task_word(self.task_count)}'
        return BUTTON_LABELS.get(self.action_type, 'Продолжить')


def _task_word(n: int) -> str:
    if 11 <= n % 100 <= 14:
        return 'заданий'
    last = n % 10
    if last == 1:
        return 'задание'
    if last in (2, 3, 4):
        return 'задания'
    return 'заданий'


def _sort_key(rec: Recommendation):
    """
    Приоритет, затем ближайший дедлайн, затем более короткая задача.
    Задачи без срока идут после срочных внутри своего приоритета.
    """
    has_deadline = 0 if rec.due_at else 1
    deadline = rec.due_at.timestamp() if rec.due_at else 0
    return (rec.priority, has_deadline, deadline, rec.estimated_minutes)


def select_next_action(candidates: Sequence[Recommendation]) -> Recommendation | None:
    """Главное действие: одно, самое приоритетное (ТЗ 1)."""
    if not candidates:
        return None
    return min(candidates, key=_sort_key)


def select_secondary_actions(
    candidates: Sequence[Recommendation], limit: int = 3
) -> list[Recommendation]:
    """
    Второстепенные действия: максимум 2-3, не дублируют главное (ТЗ 17).
    Не более одного действия каждого типа, чтобы не заваливать однотипным.
    """
    if not candidates:
        return []

    ordered = sorted(candidates, key=_sort_key)
    main = ordered[0]
    result, seen_types = [], {main.action_type}

    for rec in ordered[1:]:
        if rec.action_type in seen_types:
            continue
        result.append(rec)
        seen_types.add(rec.action_type)
        if len(result) >= limit:
            break
    return result


@dataclass(frozen=True)
class DayPlanState:
    """Состояние дня для Главной."""
    is_completed: bool
    next_action: Recommendation | None
    secondary: list[Recommendation] = field(default_factory=list)
    completed_today: int = 0
    total_today: int = 0

    @property
    def headline(self) -> str:
        if self.is_completed:
            return 'План на сегодня выполнен'
        if self.next_action:
            return self.next_action.title
        return 'Нет активных задач'


def build_day_state(
    candidates: Sequence[Recommendation],
    completed_today: int = 0,
    total_today: int = 0,
) -> DayPlanState:
    """
    Собирает состояние дня. План считается выполненным, когда обязательных
    задач с приоритетом выше «дополнительной практики» не осталось (ТЗ 5).
    """
    required = [c for c in candidates if c.priority <= PRIORITY_NEXT_TOPIC]
    is_completed = not required and total_today > 0 and completed_today >= total_today

    return DayPlanState(
        is_completed=is_completed,
        next_action=select_next_action(candidates),
        secondary=select_secondary_actions(candidates),
        completed_today=completed_today,
        total_today=total_today,
    )
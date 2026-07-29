from datetime import datetime, timedelta, timezone as dt_tz

from django.test import SimpleTestCase

from school.services.recommendations import (
    ActionType, PRIORITY_CRITICAL_ERROR, PRIORITY_EXTRA_PRACTICE,
    PRIORITY_NEXT_TOPIC, PRIORITY_OVERDUE_REQUIRED, PRIORITY_STARTED_REQUIRED,
    Recommendation, build_day_state, select_next_action, select_secondary_actions,
)

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=dt_tz.utc)


def rec(action=ActionType.WATCH_LESSON, priority=PRIORITY_NEXT_TOPIC,
        title='Тема', due=None, minutes=15, tasks=0):
    return Recommendation(
        action_type=action, priority=priority, title=title,
        reason='причина', url='/x/', due_at=due,
        estimated_minutes=minutes, task_count=tasks,
    )


class SelectionTests(SimpleTestCase):
    def test_empty_returns_none(self):
        self.assertIsNone(select_next_action([]))

    def test_lowest_priority_number_wins(self):
        items = [
            rec(priority=PRIORITY_NEXT_TOPIC),
            rec(priority=PRIORITY_OVERDUE_REQUIRED, title='Просрочено'),
            rec(priority=PRIORITY_CRITICAL_ERROR),
        ]
        self.assertEqual(select_next_action(items).title, 'Просрочено')

    def test_started_work_beats_next_topic(self):
        """ТЗ 17: начатая работа важнее новой темы."""
        items = [
            rec(action=ActionType.WATCH_LESSON, priority=PRIORITY_NEXT_TOPIC),
            rec(action=ActionType.CONTINUE_MOCK, priority=PRIORITY_STARTED_REQUIRED,
                title='Пробник'),
        ]
        self.assertEqual(select_next_action(items).title, 'Пробник')

    def test_nearest_deadline_wins_within_same_priority(self):
        items = [
            rec(priority=3, title='Позже', due=NOW + timedelta(days=5)),
            rec(priority=3, title='Скоро', due=NOW + timedelta(days=1)),
        ]
        self.assertEqual(select_next_action(items).title, 'Скоро')

    def test_dated_task_beats_undated_within_priority(self):
        items = [
            rec(priority=3, title='Без срока'),
            rec(priority=3, title='Со сроком', due=NOW + timedelta(days=3)),
        ]
        self.assertEqual(select_next_action(items).title, 'Со сроком')


class SecondaryActionsTests(SimpleTestCase):
    def test_excludes_main_action(self):
        items = [
            rec(action=ActionType.SUBMIT_HOMEWORK, priority=1, title='Главное'),
            rec(action=ActionType.REVIEW_ERRORS, priority=5),
            rec(action=ActionType.WATCH_LESSON, priority=8),
        ]
        secondary = select_secondary_actions(items)
        self.assertNotIn('Главное', [s.title for s in secondary])

    def test_limited_to_three(self):
        items = [rec(action=a, priority=i) for i, a in enumerate([
            ActionType.SUBMIT_HOMEWORK, ActionType.REVIEW_ERRORS,
            ActionType.WATCH_LESSON, ActionType.START_MOCK,
            ActionType.MINI_CHECK, ActionType.PRACTICE,
        ], start=1)]
        self.assertLessEqual(len(select_secondary_actions(items)), 3)

    def test_no_duplicate_action_types(self):
        """Не заваливаем ученика однотипными задачами (ТЗ 17)."""
        items = [
            rec(action=ActionType.SUBMIT_HOMEWORK, priority=1, title='ДЗ1'),
            rec(action=ActionType.SUBMIT_HOMEWORK, priority=2, title='ДЗ2'),
            rec(action=ActionType.SUBMIT_HOMEWORK, priority=3, title='ДЗ3'),
            rec(action=ActionType.WATCH_LESSON, priority=8, title='Урок'),
        ]
        secondary = select_secondary_actions(items)
        self.assertEqual([s.title for s in secondary], ['Урок'])

    def test_empty_input(self):
        self.assertEqual(select_secondary_actions([]), [])


class ButtonLabelTests(SimpleTestCase):
    def test_specific_labels_not_generic(self):
        """ТЗ 5: точное название действия вместо «Продолжить»."""
        self.assertEqual(rec(action=ActionType.WATCH_LESSON).button_label,
                         'Смотреть урок')
        self.assertEqual(rec(action=ActionType.MINI_CHECK).button_label,
                         'Пройти мини-проверку')
        self.assertEqual(rec(action=ActionType.REVIEW_ERRORS).button_label,
                         'Разобрать ошибки')
        self.assertEqual(rec(action=ActionType.CONTINUE_MOCK).button_label,
                         'Продолжить пробный экзамен')

    def test_practice_label_includes_count(self):
        self.assertEqual(
            rec(action=ActionType.PRACTICE, tasks=7).button_label, 'Решить 7 заданий'
        )

    def test_russian_plural_forms(self):
        for n, expected in [(1, 'задание'), (3, 'задания'), (5, 'заданий'),
                            (11, 'заданий'), (21, 'задание'), (22, 'задания')]:
            with self.subTest(n=n):
                label = rec(action=ActionType.PRACTICE, tasks=n).button_label
                self.assertTrue(label.endswith(expected), label)


class DayStateTests(SimpleTestCase):
    def test_completed_when_no_required_left(self):
        items = [rec(priority=PRIORITY_EXTRA_PRACTICE)]
        state = build_day_state(items, completed_today=3, total_today=3)
        self.assertTrue(state.is_completed)
        self.assertEqual(state.headline, 'План на сегодня выполнен')

    def test_not_completed_with_required_task(self):
        items = [rec(priority=PRIORITY_OVERDUE_REQUIRED, title='Домашка')]
        state = build_day_state(items, completed_today=3, total_today=3)
        self.assertFalse(state.is_completed)
        self.assertEqual(state.headline, 'Домашка')

    def test_not_completed_when_nothing_planned(self):
        """Без задач на день план не считается выполненным."""
        state = build_day_state([], completed_today=0, total_today=0)
        self.assertFalse(state.is_completed)

    def test_headline_without_candidates(self):
        state = build_day_state([], completed_today=0, total_today=0)
        self.assertEqual(state.headline, 'Нет активных задач')

    def test_offers_extra_practice_when_plan_done(self):
        items = [rec(action=ActionType.START_MOCK, priority=PRIORITY_EXTRA_PRACTICE,
                     title='Пробник')]
        state = build_day_state(items, completed_today=2, total_today=2)
        self.assertTrue(state.is_completed)
        self.assertEqual(state.next_action.title, 'Пробник')

class UndatedRequiredTests(SimpleTestCase):
    def test_errors_beat_undated_homework(self):
        """Ошибки конкретны и мешают сейчас, домашка без срока подождёт."""
        from school.services.recommendations import PRIORITY_REQUIRED_UNDATED
        items = [
            rec(action=ActionType.SUBMIT_HOMEWORK,
                priority=PRIORITY_REQUIRED_UNDATED, title='Домашка'),
            rec(action=ActionType.REVIEW_ERRORS,
                priority=PRIORITY_CRITICAL_ERROR, title='Ошибки'),
        ]
        self.assertEqual(select_next_action(items).title, 'Ошибки')

    def test_dated_homework_beats_errors(self):
        """С реальным сроком домашка снова важнее."""
        from school.services.recommendations import PRIORITY_NEAREST_DEADLINE
        items = [
            rec(action=ActionType.SUBMIT_HOMEWORK,
                priority=PRIORITY_NEAREST_DEADLINE, title='Домашка',
                due=NOW + timedelta(days=1)),
            rec(action=ActionType.REVIEW_ERRORS,
                priority=PRIORITY_CRITICAL_ERROR, title='Ошибки'),
        ]
        self.assertEqual(select_next_action(items).title, 'Домашка')

    def test_undated_required_beats_next_topic(self):
        """Но выданная домашка всё равно важнее новой темы."""
        from school.services.recommendations import PRIORITY_REQUIRED_UNDATED
        items = [
            rec(action=ActionType.WATCH_LESSON,
                priority=PRIORITY_NEXT_TOPIC, title='Урок'),
            rec(action=ActionType.SUBMIT_HOMEWORK,
                priority=PRIORITY_REQUIRED_UNDATED, title='Домашка'),
        ]
        self.assertEqual(select_next_action(items).title, 'Домашка')
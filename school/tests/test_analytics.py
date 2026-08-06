from datetime import datetime, timedelta, timezone as dt_timezone

from django.test import SimpleTestCase

from school.services.analytics import (
    AttemptData, accuracy, activity_score, classify_topic, confidence_label,
    convert_to_test_score, error_correction_rate, error_rate, expected_primary_score,
    mastery_confidence, mastery_label, plan_adherence, program_progress,
    readiness_score, recency_weight, score_gap, score_trend, stability,
    task_success_probability, topic_mastery, evidence_weight, TaskStats,
)
from school.services.constants import MASTERY_MAX_ATTEMPTS, EVIDENCE_WEIGHT_CAP

NOW = datetime(2026, 7, 23, 12, 0, tzinfo=dt_timezone.utc)


def make_attempt(earned, maximum, days_ago=0, activity='practice'):
    return AttemptData(
        earned_points=earned,
        max_points=maximum,
        activity_type=activity,
        completed_at=NOW - timedelta(days=days_ago),
    )


class ActivityScoreTests(SimpleTestCase):
    def test_full_score(self):
        self.assertEqual(activity_score(5, 5), 100)

    def test_partial_points_counted_as_ratio(self):
        """ТЗ 15.1: частичные баллы — именно отношение."""
        self.assertEqual(activity_score(3, 4), 75)

    def test_zero_max_points_returns_none(self):
        self.assertIsNone(activity_score(0, 0))

    def test_negative_max_points_returns_none(self):
        self.assertIsNone(activity_score(1, -2))


class AccuracyTests(SimpleTestCase):
    def test_aggregates_by_points_not_by_task_count(self):
        attempts = [make_attempt(1, 1), make_attempt(1, 5)]
        self.assertEqual(accuracy(attempts), 2 / 6 * 100)

    def test_skips_broken_attempts(self):
        attempts = [make_attempt(2, 2), make_attempt(0, 0)]
        self.assertEqual(accuracy(attempts), 100)

    def test_empty_returns_none(self):
        self.assertIsNone(accuracy([]))


class ProgressTests(SimpleTestCase):
    def test_normal(self):
        self.assertEqual(program_progress(3, 4), 75)

    def test_zero_total_does_not_crash(self):
        self.assertIsNone(program_progress(0, 0))
        self.assertEqual(program_progress(0, 10), 0.0)

class RecencyTests(SimpleTestCase):
    def test_fresh_attempt_full_weight(self):
        self.assertAlmostEqual(recency_weight(NOW, NOW), 1.0)

    def test_half_life_45_days(self):
        """ТЗ 15.5: вес падает вдвое за 45 дней."""
        old = NOW - timedelta(days=45)
        self.assertAlmostEqual(recency_weight(old, NOW), 0.5, places=4)


class MasteryTests(SimpleTestCase):
    def test_recent_result_outweighs_old(self):
        attempts = [make_attempt(10, 10, days_ago=0), make_attempt(0, 10, days_ago=80)]
        self.assertGreater(topic_mastery(attempts, NOW), 50)

    def test_ignores_attempts_outside_window(self):
        attempts = [make_attempt(0, 10, days_ago=200), make_attempt(10, 10, days_ago=1)]
        self.assertAlmostEqual(topic_mastery(attempts, NOW), 100, places=1)

    def test_no_data_returns_none(self):
        self.assertIsNone(topic_mastery([], NOW))

    def test_mock_exam_weighted_higher_than_mini_check(self):
        mock = [make_attempt(0, 10, activity='mock_exam'), make_attempt(10, 10, activity='mini_check')]
        self.assertLess(topic_mastery(mock, NOW), 50)


class ConfidenceTests(SimpleTestCase):
    def test_single_attempt_is_low_confidence(self):
        conf = mastery_confidence([make_attempt(5, 5)], NOW)
        self.assertLess(conf, 30)
        self.assertEqual(confidence_label(conf), 'Мало данных')

    def test_twenty_fresh_attempts_reach_full_confidence(self):
        attempts = [make_attempt(1, 1) for _ in range(20)]
        self.assertEqual(mastery_confidence(attempts, NOW), 100)


class MasteryLabelTests(SimpleTestCase):
    def test_high_mastery_low_confidence_shows_insufficient_data(self):
        """ТЗ 15.6: нельзя маркировать тему при малых данных."""
        self.assertEqual(mastery_label(95, confidence=10), 'Мало данных')

    def test_high_mastery_high_confidence(self):
        self.assertEqual(mastery_label(90, confidence=70), 'Уверенное освоение')


class ErrorTests(SimpleTestCase):
    def test_error_rate_accounts_partial_points(self):
        self.assertEqual(error_rate([make_attempt(3, 4)]), 25)

    def test_correction_rate_zero_total(self):
        self.assertIsNone(error_correction_rate(0, 0))
        self.assertEqual(error_correction_rate(0, 3), 0.0)

    def test_correction_rate(self):
        self.assertEqual(error_correction_rate(3, 12), 25)


class PlanTests(SimpleTestCase):
    def test_cancelled_tasks_do_not_hurt(self):
        """ТЗ 15.10: отменённые не ухудшают показатель."""
        self.assertEqual(plan_adherence(completed_on_time=5, total_due=10, cancelled=5), 100)

    def test_zero_due(self):
        self.assertIsNone(plan_adherence(0, 0))
        self.assertEqual(plan_adherence(0, 5), 0.0)


class ConversionTableTests(SimpleTestCase):
    TABLE = {0: 0, 10: 30, 20: 55, 30: 78, 40: 95}

    def test_exact_match(self):
        self.assertEqual(convert_to_test_score(20, self.TABLE), 55)

    def test_interpolates_down_to_nearest(self):
        self.assertEqual(convert_to_test_score(25, self.TABLE), 55)

    def test_above_max_clamps(self):
        self.assertEqual(convert_to_test_score(999, self.TABLE), 95)

    def test_empty_table_returns_none(self):
        """ТЗ 24.18: шкала не хардкодится, отсутствие — не падение."""
        self.assertIsNone(convert_to_test_score(20, {}))

    def test_different_exam_year_uses_own_table(self):
        table_2027 = {20: 60}
        self.assertNotEqual(
            convert_to_test_score(20, self.TABLE),
            convert_to_test_score(20, table_2027),
        )


class GapTests(SimpleTestCase):
    def test_goal_reached(self):
        gap, label = score_gap(target=80, predicted=85)
        self.assertEqual(label, 'Цель достигнута по текущему прогнозу')

    def test_no_prediction(self):
        gap, label = score_gap(target=80, predicted=None)
        self.assertIsNone(gap)


class TrendStabilityTests(SimpleTestCase):
    def test_trend_none_without_data(self):
        self.assertIsNone(score_trend([], [70.0]))

    def test_trend_growth(self):
        self.assertEqual(score_trend([75.0, 80.0], [65.0, 70.0]), 10.0)

    def test_stability_needs_three_points(self):
        _, label = stability([80.0, 82.0])
        self.assertEqual(label, 'Мало данных')

    def test_stable_results(self):
        _, label = stability([80.0, 82.0, 79.0, 81.0])
        self.assertEqual(label, 'Высокая стабильность')


class ReadinessTests(SimpleTestCase):
    def test_none_prediction(self):
        self.assertIsNone(readiness_score(None, 80, 50, 50, 50))

    def test_weights_sum_correctly(self):
        score = readiness_score(80, 80, 100, 100, 100)
        self.assertAlmostEqual(score, 100.0, places=1)


class ClassificationTests(SimpleTestCase):
    def test_insufficient_data(self):
        self.assertEqual(classify_topic(mastery=90, confidence=10), 'insufficient_data')

    def test_critical(self):
        self.assertEqual(classify_topic(mastery=35, confidence=60), 'critical')

    def test_strong_requires_multiple_days(self):
        """ТЗ 16: успехи должны быть в разные дни, не в одной сессии."""
        self.assertNotEqual(
            classify_topic(mastery=90, confidence=70, successful_days=1), 'strong'
        )
        self.assertEqual(
            classify_topic(mastery=90, confidence=70, successful_days=3), 'strong'
        )


class AttemptLimitTests(SimpleTestCase):
    def test_only_30_most_recent_attempts_count(self):
        """ТЗ 15.5: сверх лимита 30 старые попытки не влияют."""
        fresh = [make_attempt(10, 10, days_ago=i) for i in range(MASTERY_MAX_ATTEMPTS)]
        old_bad = [make_attempt(0, 10, days_ago=60 + i) for i in range(20)]
        self.assertAlmostEqual(topic_mastery(fresh + old_bad, NOW), 100, places=1)

    def test_limit_keeps_30_newest_attempts(self):
        newest_bad = [
            make_attempt(0, 10, days_ago=i)
            for i in range(MASTERY_MAX_ATTEMPTS)
        ]
        older_good = [
            make_attempt(10, 10, days_ago=40 + i)
            for i in range(20)
        ]

        result = topic_mastery(newest_bad + older_good, NOW)

        self.assertAlmostEqual(result, 0.0, places=1)

    def test_attempts_over_limit_do_not_reduce_mastery(self):
        newest_good = [
            make_attempt(10, 10, days_ago=i)
            for i in range(MASTERY_MAX_ATTEMPTS)
        ]
        older_bad = [
            make_attempt(0, 10, days_ago=40 + i)
            for i in range(20)
        ]

        result = topic_mastery(newest_good + older_bad, NOW)

        self.assertAlmostEqual(result, 100.0, places=1)


class EvidenceWeightTests(SimpleTestCase):
    def test_capped(self):
        self.assertEqual(evidence_weight(10), EVIDENCE_WEIGHT_CAP)

    def test_small_task_not_capped(self):
        self.assertEqual(evidence_weight(2), 2.0)

    def test_zero_max_points_gives_zero(self):
        self.assertEqual(evidence_weight(0), 0.0)

    def test_no_double_counting_of_task_size(self):
        """
        Задание на 1 балл решено верно, на 12 баллов — на 0.
        Крупное задание весомее, но не подавляет полностью (потолок 3).
        """
        attempts = [make_attempt(1, 1, days_ago=0), make_attempt(0, 12, days_ago=0)]
        result = topic_mastery(attempts, NOW)
        self.assertGreater(result, 20)
        self.assertLess(result, 30)


class PredictionTests(SimpleTestCase):
    def test_single_small_task_does_not_give_extreme(self):
        p = task_success_probability(total_earned_points=1, total_max_points=1)
        self.assertLess(p, 0.75)
        self.assertGreater(p, 0.5)

    def test_no_data_returns_neutral(self):
        self.assertEqual(task_success_probability(0, 0), 0.5)

    def test_large_volume_converges_to_observed(self):
        p = task_success_probability(total_earned_points=180, total_max_points=200)
        self.assertAlmostEqual(p, 0.9, places=1)

    def test_partial_points_counted(self):
        p_partial = task_success_probability(5, 10)
        p_full = task_success_probability(10, 10)
        self.assertLess(p_partial, p_full)
        self.assertGreater(p_partial, 0.4)

    def test_expected_primary_score_uses_exam_weight(self):
        stats = [
            TaskStats(max_primary_points=1, total_earned_points=10, total_max_points=10),
            TaskStats(max_primary_points=5, total_earned_points=0, total_max_points=10),
        ]
        score = expected_primary_score(stats)
        self.assertGreater(score, 1.0)
        self.assertLess(score, 4.0)
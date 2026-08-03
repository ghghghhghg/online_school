from school.services.prediction import predict_test_score


TABLE = {0: 0, 10: 30, 20: 55, 30: 78, 40: 95}


class PredictionTests:
    pass


from django.test import SimpleTestCase


class PredictTestScoreTests(SimpleTestCase):
    def test_no_task_numbers_unavailable(self):
        result = predict_test_score({}, {}, TABLE)
        self.assertFalse(result.available)
        self.assertIn('номера ЕГЭ', result.reason)

    def test_no_table_unavailable(self):
        result = predict_test_score({}, {1: 1.0}, None)
        self.assertFalse(result.available)
        self.assertIn('шкала', result.reason)

    def test_no_attempts_unavailable(self):
        result = predict_test_score({}, {1: 1.0, 2: 1.0}, TABLE)
        self.assertFalse(result.available)
        self.assertEqual(result.total_numbers, 2)

    def test_partial_coverage_still_predicts(self):
        attempts = {1: {'earned': 8, 'max': 10}}
        task_max = {1: 1.0, 2: 1.0, 3: 5.0}
        result = predict_test_score(attempts, task_max, TABLE)
        self.assertTrue(result.available)
        self.assertEqual(result.covered_numbers, 1)
        self.assertEqual(result.total_numbers, 3)
        self.assertEqual(result.coverage_percent, 33)

    def test_full_coverage_gives_higher_confidence_prediction(self):
        attempts = {
            1: {'earned': 18, 'max': 20},
            2: {'earned': 16, 'max': 20},
        }
        task_max = {1: 1.0, 2: 1.0}
        result = predict_test_score(attempts, task_max, TABLE)
        self.assertEqual(result.coverage_percent, 100)
        self.assertIsNotNone(result.predicted_test_score)

    def test_out_of_range_primary_score(self):
        attempts = {1: {'earned': 100, 'max': 100}}
        task_max = {1: 999.0}
        result = predict_test_score(attempts, task_max, {0: 0, 5: 50})
        self.assertTrue(result.available)  # clamp к верхней границе таблицы
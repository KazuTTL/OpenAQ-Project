import unittest

import pandas as pd

from src.analysis.anomaly_detection import AnomalyDetector


class TestAnomalyDetector(unittest.TestCase):
    def test_zscore_detects_outlier_within_station_parameter_group(self):
        df = pd.DataFrame({
            "location_key": [1, 1, 1, 1, 1, 2],
            "parameter_name": ["pm25"] * 5 + ["pm25"],
            "datetime_utc": pd.date_range("2026-10-26", periods=6, freq="h"),
            "value": [10.0, 10.0, 10.0, 10.0, 100.0, 100.0],
        })

        result = AnomalyDetector.detect_zscore(df, threshold=1.5, min_samples=5)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["location_key"], 1)
        self.assertEqual(result.iloc[0]["value"], 100.0)
        self.assertEqual(result.iloc[0]["anomaly_method"], "zscore")

    def test_methods_ignore_groups_below_minimum_sample_count(self):
        df = pd.DataFrame({
            "location_key": [1, 1, 1, 1],
            "parameter_name": ["pm25"] * 4,
            "value": [10.0, 10.0, 10.0, 100.0],
        })

        zscore_result = AnomalyDetector.detect_zscore(df, threshold=1.0, min_samples=5)
        iqr_result = AnomalyDetector.detect_iqr(df, min_samples=5)

        self.assertTrue(zscore_result.empty)
        self.assertTrue(iqr_result.empty)

    def test_iqr_detects_outlier_in_constant_series(self):
        df = pd.DataFrame({
            "location_key": [1] * 5,
            "parameter_name": ["pm25"] * 5,
            "value": [10.0, 10.0, 10.0, 10.0, 100.0],
        })

        result = AnomalyDetector.detect_iqr(df, min_samples=5)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["value"], 100.0)
        self.assertEqual(result.iloc[0]["anomaly_method"], "iqr")

    def test_rolling_detection_uses_previous_values_only(self):
        df = pd.DataFrame({
            "location_key": [1] * 6,
            "parameter_name": ["pm25"] * 6,
            "datetime_utc": pd.date_range("2026-10-26", periods=6, freq="h"),
            "value": [1.0, 2.0, 1.0, 2.0, 1.0, 10.0],
        })

        result = AnomalyDetector.detect_rolling(
            df,
            window=3,
            threshold=3.0,
            min_samples=3,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["value"], 10.0)
        self.assertEqual(result.iloc[0]["anomaly_method"], "rolling")

    def test_detect_all_returns_method_for_each_detection(self):
        df = pd.DataFrame({
            "location_key": [1] * 6,
            "parameter_name": ["pm25"] * 6,
            "datetime_utc": pd.date_range("2026-10-26", periods=6, freq="h"),
            "value": [1.0, 2.0, 1.0, 2.0, 1.0, 10.0],
        })

        result = AnomalyDetector.detect_all(df, min_samples=5)

        self.assertFalse(result.empty)
        self.assertTrue(set(result["anomaly_method"]).issubset({"zscore", "iqr", "rolling"}))
        self.assertIn("rolling", set(result["anomaly_method"]))


if __name__ == "__main__":
    unittest.main()

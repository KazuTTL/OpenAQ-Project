import unittest

import pandas as pd

from src.analysis.pattern_mining import PatternMiner


class TestPatternMiner(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({
            "location_key": [1, 1, 1, 1],
            "parameter_name": ["pm25"] * 4,
            "datetime_utc": pd.date_range("2026-10-26", periods=4, freq="h"),
            "hour": [0, 1, 1, 2],
            "day_of_week": [1, 1, 2, 2],
            "aqi": [50.0, 100.0, 150.0, 200.0],
            "value": [10.0, 20.0, 30.0, 40.0],
        })

    def test_hourly_patterns_aggregate_measurements(self):
        result = PatternMiner.hourly_patterns(self.df)

        hour_one = result[result["hour"] == 1].iloc[0]
        self.assertEqual(len(result), 3)
        self.assertEqual(hour_one["measurement_count"], 2)
        self.assertEqual(hour_one["mean_value"], 125.0)

    def test_weekday_patterns_identify_weekends(self):
        result = PatternMiner.weekday_patterns(self.df)

        self.assertEqual(len(result), 2)
        self.assertFalse(result.loc[result["day_of_week"] == 1, "is_weekend"].iloc[0])
        self.assertFalse(result.loc[result["day_of_week"] == 2, "is_weekend"].iloc[0])

    def test_high_aqi_episodes_require_consecutive_measurements(self):
        df = pd.DataFrame({
            "location_key": [1] * 5,
            "parameter_name": ["pm25"] * 5,
            "datetime_utc": pd.to_datetime([
                "2026-10-26T00:00:00Z",
                "2026-10-26T01:00:00Z",
                "2026-10-26T02:00:00Z",
                "2026-10-26T04:00:00Z",
                "2026-10-26T05:00:00Z",
            ]),
            "aqi": [160.0, 170.0, 180.0, 190.0, 200.0],
        })

        result = PatternMiner.high_aqi_episodes(
            df,
            threshold=150.0,
            min_measurements=3,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["measurement_count"], 3)
        self.assertEqual(result.iloc[0]["duration_hours"], 3.0)
        self.assertEqual(result.iloc[0]["max_aqi"], 180.0)

    def test_pollutant_correlation_returns_parameter_matrix(self):
        df = pd.DataFrame({
            "location_key": [1, 1, 1, 1, 1, 1],
            "datetime_utc": list(pd.date_range("2026-10-26", periods=3, freq="h")) * 2,
            "parameter_name": ["pm25"] * 3 + ["pm10"] * 3,
            "value": [1.0, 2.0, 3.0, 2.0, 4.0, 6.0],
        })

        result = PatternMiner.pollutant_correlation(df)

        self.assertEqual(list(result.columns), ["pm10", "pm25"])
        self.assertAlmostEqual(result.loc["pm25", "pm10"], 1.0)
        self.assertAlmostEqual(result.loc["pm10", "pm25"], 1.0)

    def test_high_aqi_episodes_returns_empty_for_no_matches(self):
        result = PatternMiner.high_aqi_episodes(self.df, threshold=300.0)

        self.assertTrue(result.empty)
        self.assertEqual(list(result.columns), [
            "location_key",
            "parameter_name",
            "episode_start",
            "episode_end",
            "duration_hours",
            "measurement_count",
            "mean_aqi",
            "max_aqi",
        ])


if __name__ == "__main__":
    unittest.main()

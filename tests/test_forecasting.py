import unittest
from unittest.mock import patch

import pandas as pd

from src.analysis.forecasting import AirQualityForecaster


class TestAirQualityForecaster(unittest.TestCase):
    def make_time_series(self, rows_per_station=60):
        rows = []
        timestamps = pd.date_range("2026-10-01", periods=rows_per_station, freq="h")
        for location_key, offset in [(1, 0.0), (2, 100.0)]:
            for index, timestamp in enumerate(timestamps):
                rows.append({
                    "datetime_utc": timestamp,
                    "hour": timestamp.hour,
                    "day_of_week": timestamp.day_of_week + 1,
                    "month": timestamp.month,
                    "location_key": location_key,
                    "location_name": f"Station {location_key}",
                    "city": "Test City",
                    "target_value": offset + index,
                })
        return pd.DataFrame(rows)

    def test_create_features_keeps_rolling_windows_inside_station(self):
        result = AirQualityForecaster.create_features(self.make_time_series())

        station_two = result[result["location_key"] == 2]
        self.assertFalse(station_two.empty)
        self.assertTrue((station_two["rolling_mean_6"] >= 100).all())
        self.assertTrue((station_two["rolling_mean_24"] >= 100).all())

    @patch.object(AirQualityForecaster, "load_time_series_data")
    def test_train_and_evaluate_uses_chronological_split(self, load_data):
        load_data.return_value = self.make_time_series()

        result = AirQualityForecaster.train_and_evaluate(test_ratio=0.2)

        self.assertEqual(result["status"], "success")
        self.assertGreater(result["train_samples"], result["test_samples"])
        self.assertIn("random_forest", result)
        self.assertIn("feature_importances", result)

    def test_train_and_evaluate_rejects_invalid_test_ratio(self):
        with self.assertRaises(ValueError):
            AirQualityForecaster.train_and_evaluate(test_ratio=1.0)


if __name__ == "__main__":
    unittest.main()

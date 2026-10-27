import unittest

import pandas as pd

from src.analysis.data_validation import DataQualityValidator


class TestDataQualityValidator(unittest.TestCase):
    def test_duplicate_count_uses_measurement_identity(self):
        df = pd.DataFrame({
            "location_key": [1, 1, 1],
            "parameter_name": ["pm25", "pm25", "pm10"],
            "datetime_utc": [
                "2026-10-26T00:00:00Z",
                "2026-10-26T00:00:00Z",
                "2026-10-26T00:00:00Z",
            ],
            "value": [10.0, 11.0, 20.0],
        })

        self.assertEqual(DataQualityValidator.duplicate_count(df), 2)

    def test_missing_values_reports_only_existing_columns(self):
        df = pd.DataFrame({
            "value": [10.0, None],
            "datetime_utc": [None, "2026-10-26T00:00:00Z"],
        })

        result = DataQualityValidator.missing_values(
            df,
            columns=["value", "datetime_utc", "missing_column"],
        )

        self.assertEqual(result, {"value": 1, "datetime_utc": 1})

    def test_timestamp_summary_handles_invalid_values(self):
        df = pd.DataFrame({
            "datetime_utc": [
                "2026-10-26T00:00:00Z",
                "not-a-timestamp",
                "2026-10-26T01:00:00Z",
            ]
        })

        result = DataQualityValidator.timestamp_summary(df)

        self.assertEqual(result["invalid_timestamp_count"], 1)
        self.assertEqual(result["unique_timestamp_count"], 2)
        self.assertEqual(result["earliest_utc"], "2026-10-26T00:00:00+00:00")
        self.assertEqual(result["latest_utc"], "2026-10-26T01:00:00+00:00")

    def test_invalid_measurements_reports_ranges_and_unknown_parameters(self):
        df = pd.DataFrame({
            "parameter_name": ["pm25", "pm25", "pm10", "unknown"],
            "value": [10.0, -1.0, 2000.0, 5.0],
        })

        result = DataQualityValidator.invalid_measurements(df)

        self.assertEqual(result["negative_value_count"], 1)
        self.assertEqual(result["unknown_parameter_count"], 1)
        self.assertEqual(
            result["out_of_range_by_parameter"],
            {"pm10": 1, "pm25": 1},
        )

    def test_build_report_contains_core_quality_dimensions(self):
        df = pd.DataFrame({
            "location_key": [1, 1],
            "parameter_name": ["pm25", "pm25"],
            "datetime_utc": [
                "2026-10-26T00:00:00Z",
                "2026-10-26T00:00:00Z",
            ],
            "value": [10.0, 10.0],
        })

        report = DataQualityValidator.build_report(df)

        self.assertEqual(report["row_count"], 2)
        self.assertEqual(report["duplicate_count"], 2)
        self.assertEqual(report["invalid_measurements"]["negative_value_count"], 0)
        self.assertEqual(report["timestamp"]["unique_timestamp_count"], 1)


if __name__ == "__main__":
    unittest.main()

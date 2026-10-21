import unittest
import pandas as pd
from src.transform.cleaner import DataCleaner


class TestDataCleaner(unittest.TestCase):
    def test_remove_duplicates(self):
        df = pd.DataFrame({
            "source_location_id": [1, 1, 2],
            "parameter_name": ["pm25", "pm25", "pm25"],
            "datetime_utc": ["2026-10-18 00:00:00", "2026-10-18 00:00:00", "2026-10-18 00:00:00"],
            "value": [15.0, 18.0, 20.0]
        })
        res = DataCleaner.remove_duplicates(df)
        self.assertEqual(len(res), 2)
        self.assertEqual(res.loc[res["source_location_id"] == 1, "value"].iloc[0], 18.0)

    def test_handle_missing_values(self):
        df = pd.DataFrame({
            "datetime_utc": ["2026-10-18 00:00:00", None, "2026-10-18 01:00:00"],
            "value": [10.0, 12.0, None]
        })
        res = DataCleaner.handle_missing_values(df)
        self.assertEqual(len(res), 1)
        self.assertEqual(res.iloc[0]["value"], 10.0)

    def test_validate_measurements(self):
        df = pd.DataFrame({
            "parameter_name": ["pm25", "pm25", "pm25"],
            "value": [-5.0, 50.0, 2000.0]
        })
        res = DataCleaner.validate_measurements(df)
        self.assertEqual(len(res), 1)
        self.assertEqual(res.iloc[0]["value"], 50.0)


if __name__ == "__main__":
    unittest.main()

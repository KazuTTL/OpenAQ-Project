import unittest
import pandas as pd
from src.transform.normalizer import DataNormalizer


class TestDataNormalizer(unittest.TestCase):
    def test_normalize_location(self):
        df = pd.DataFrame({
            "city": ["  ha noi  ", None],
            "country": ["vietnam", None],
            "latitude": [21.0, 150.0],
            "longitude": [105.8, 200.0],
        })
        res = DataNormalizer.normalize_location(df)
        self.assertEqual(res.loc[0, "city"], "Ha Noi")
        self.assertEqual(res.loc[1, "city"], "Unknown")
        self.assertEqual(res.loc[0, "latitude"], 21.0)
        self.assertTrue(pd.isna(res.loc[1, "latitude"]))
        self.assertTrue(pd.isna(res.loc[1, "longitude"]))

    def test_convert_timezone(self):
        df = pd.DataFrame({
            "datetime_utc": ["2026-10-18T00:00:00Z"],
            "timezone": ["Asia/Ho_Chi_Minh"],
        })
        res = DataNormalizer.convert_timezone(df)
        self.assertIn("local_datetime", res.columns)
        self.assertEqual(res.loc[0, "local_datetime"].hour, 7)


if __name__ == "__main__":
    unittest.main()

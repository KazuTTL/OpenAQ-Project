import unittest
import pandas as pd
from src.transform.aqi_calculator import AQICalculator


class TestAQICalculator(unittest.TestCase):
    def test_aqi_category_classification(self):
        self.assertEqual(AQICalculator.get_category(25), "Good")
        self.assertEqual(AQICalculator.get_category(75), "Moderate")
        self.assertEqual(AQICalculator.get_category(125), "Unhealthy for Sensitive Groups")
        self.assertEqual(AQICalculator.get_category(175), "Unhealthy")
        self.assertEqual(AQICalculator.get_category(250), "Very Unhealthy")
        self.assertEqual(AQICalculator.get_category(350), "Hazardous")
        self.assertEqual(AQICalculator.get_category(None), "Unknown")

    def test_calculate_sub_index_pm25(self):
        self.assertEqual(AQICalculator.calculate_sub_index("pm25", 0.0), 0.0)
        self.assertEqual(AQICalculator.calculate_sub_index("pm25", 12.0), 50.0)
        self.assertEqual(AQICalculator.calculate_sub_index("pm25", 35.4), 100.0)
        self.assertIsNone(AQICalculator.calculate_sub_index("pm25", -5.0))

    def test_calculate_sub_index_pm10(self):
        self.assertEqual(AQICalculator.calculate_sub_index("pm10", 0.0), 0.0)
        self.assertEqual(AQICalculator.calculate_sub_index("pm10", 54.0), 50.0)
        self.assertEqual(AQICalculator.calculate_sub_index("pm10", 154.0), 100.0)

    def test_compute_aqi_for_dataframe(self):
        df = pd.DataFrame({
            "parameter_name": ["pm25", "pm10", "unknown_param"],
            "value": [12.0, 54.0, 100.0]
        })
        result = AQICalculator.compute_aqi_for_dataframe(df)
        self.assertIn("aqi", result.columns)
        self.assertIn("pollution_category", result.columns)
        self.assertEqual(result.loc[0, "aqi"], 50.0)
        self.assertEqual(result.loc[0, "pollution_category"], "Good")
        self.assertEqual(result.loc[1, "aqi"], 50.0)
        self.assertEqual(result.loc[1, "pollution_category"], "Good")


if __name__ == "__main__":
    unittest.main()

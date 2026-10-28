import unittest
from src.extract.weather_client import WeatherClient


class TestWeatherClient(unittest.TestCase):
    def setUp(self):
        self.client = WeatherClient()

    def test_get_hourly_weather(self):
        # Hanoi coordinates
        res = self.client.get_hourly_weather(21.03, 105.85, "2026-10-25", "2026-10-25")
        self.assertIsInstance(res, dict)
        if res:
            first_key = list(res.keys())[0]
            self.assertIn("temperature", res[first_key])
            self.assertIn("humidity", res[first_key])
            self.assertIsInstance(res[first_key]["temperature"], float)
            self.assertIsInstance(res[first_key]["humidity"], float)

    def test_get_weather_for_timestamp(self):
        temp, hum = self.client.get_weather_for_timestamp(21.03, 105.85, "2026-10-25T08:00:00Z")
        if temp is not None:
            self.assertIsInstance(temp, float)
            self.assertIsInstance(hum, float)


if __name__ == "__main__":
    unittest.main()

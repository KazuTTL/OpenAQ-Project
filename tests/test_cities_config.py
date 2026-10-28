import unittest
from pathlib import Path
import yaml


class TestCitiesConfig(unittest.TestCase):
    def setUp(self):
        self.base_dir = Path(__file__).resolve().parent.parent
        self.config_path = self.base_dir / "config" / "cities.yaml"

    def test_cities_yaml_exists(self):
        self.assertTrue(self.config_path.exists(), "File config/cities.yaml phai ton tai.")

    def test_cities_yaml_structure(self):
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self.assertIn("cities", data)
        self.assertIn("target_countries", data)
        self.assertGreaterEqual(len(data["cities"]), 20, "Phai co it nhat 20 thanh pho.")

        country_codes = {c["code"] for c in data["target_countries"]}
        self.assertIn("VN", country_codes)
        self.assertIn("TH", country_codes)

        total_stations = 0
        for city in data["cities"]:
            self.assertIn("city_name", city)
            self.assertIn("country_code", city)
            self.assertIn("region", city)
            self.assertIn("stations", city)
            stations = city["stations"]
            self.assertGreaterEqual(len(stations), 2, f"Thanh pho {city['city_name']} phai co it nhat 2 tram do.")

            for stn in stations:
                self.assertIn("station_id", stn)
                self.assertIn("station_name", stn)
                self.assertIn("latitude", stn)
                self.assertIn("longitude", stn)
                self.assertIsInstance(stn["station_id"], int)
                self.assertTrue(-90 <= stn["latitude"] <= 90)
                self.assertTrue(-180 <= stn["longitude"] <= 180)
                total_stations += 1

        self.assertGreaterEqual(total_stations, 40, "Tong so tram phai >= 40 tram.")


if __name__ == "__main__":
    unittest.main()

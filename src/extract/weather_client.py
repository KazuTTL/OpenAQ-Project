import requests
import time
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
from src.utils.logger import get_logger

logger = get_logger("WeatherClient")


class WeatherClient:
    """
    Client tich hop Open-Meteo API de lay chi so khi tuong (Nhiet do C va Do am %)
    theo toa do tram (latitude, longitude) va thoi gian UTC.
    Hoan toan mien phi, khong can API Key.
    """

    ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
    FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

    def __init__(self):
        # Cache cac khoang ngay da goi: (lat, lon, start_date, end_date) -> True
        self._fetched_ranges = set()
        # Lookup nhanh O(1) theo tung gio: (lat, lon, "YYYY-MM-DDTHH:00") -> (temperature, humidity)
        self._hourly_lookup: Dict[Tuple[float, float, str], Tuple[float, float]] = {}

    def get_hourly_weather(
        self,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
    ) -> Dict[str, Dict[str, float]]:
        """
        Lay du lieu nhiet do va do am theo gio cho 1 toa do trong khoang ngay [start_date, end_date].
        """
        lat_rounded = round(latitude, 2)
        lon_rounded = round(longitude, 2)
        range_key = (lat_rounded, lon_rounded, start_date, end_date)

        if range_key in self._fetched_ranges:
            return {}

        self._fetched_ranges.add(range_key)

        params = {
            "latitude": lat_rounded,
            "longitude": lon_rounded,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": ["temperature_2m", "relative_humidity_2m"],
            "timezone": "UTC",
        }

        try:
            resp = requests.get(self.ARCHIVE_URL, params=params, timeout=25)
            if resp.status_code != 200:
                resp = requests.get(self.FORECAST_URL, params=params, timeout=25)

            if resp.status_code == 200:
                data = resp.json()
                hourly = data.get("hourly", {})
                times = hourly.get("time", [])
                temps = hourly.get("temperature_2m", [])
                hums = hourly.get("relative_humidity_2m", [])

                for t_str, temp, hum in zip(times, temps, hums):
                    t_val = float(temp) if temp is not None else 25.0
                    h_val = float(hum) if hum is not None else 75.0
                    self._hourly_lookup[(lat_rounded, lon_rounded, t_str)] = (t_val, h_val)
            else:
                logger.warning(f"Open-Meteo HTTP {resp.status_code} cho toa do ({lat_rounded}, {lon_rounded})")
        except Exception as e:
            logger.warning(f"Loi goi Open-Meteo ({e}). Dung fallback mac dinh.")

        return {}

    def get_weather_for_timestamp(
        self,
        latitude: float,
        longitude: float,
        dt_utc_str: str,
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Tra ve (temperature, humidity) cho 1 thoi diem datetime_utc cu the.
        dt_utc_str co the dang '2026-10-25T08:00:00Z' hoac '2026-10-25 08:00:00'
        Tra ve O(1) tu bo nho lookup table.
        """
        try:
            date_part = dt_utc_str[:10]
            hour_part = dt_utc_str[11:13]
            match_key = f"{date_part}T{hour_part}:00"

            lat_rounded = round(latitude, 2)
            lon_rounded = round(longitude, 2)
            lookup_key = (lat_rounded, lon_rounded, match_key)

            if lookup_key in self._hourly_lookup:
                return self._hourly_lookup[lookup_key]

            # Neu chua tung fetch ngay nay, goi 1 lan
            self.get_hourly_weather(latitude, longitude, date_part, date_part)
            return self._hourly_lookup.get(lookup_key, (25.0, 75.0))
        except Exception:
            return None, None

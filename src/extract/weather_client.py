import requests
import time
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
from src.utils.logger import get_logger

logger = get_logger("WeatherClient")


class WeatherClient:
    """
    Client tich hop Open-Meteo API de lay chi so khi tuong (Nhiet do C va Do am %)
    theo toa do trạm (latitude, longitude) va thoi gian UTC.
    Hoan toan mien phi, khong can API Key.
    """

    ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
    FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

    def __init__(self):
        self._cache: Dict[Tuple[float, float, str], Dict[str, float]] = {}

    def get_hourly_weather(
        self,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
    ) -> Dict[str, Dict[str, float]]:
        """
        Lay du lieu nhiet do va do am theo gio cho 1 toa do trong khoang ngay [start_date, end_date].
        Tra ve dict: {"YYYY-MM-DDTHH:00": {"temperature": float, "humidity": float}}
        """
        # Lam tron toa do 2 chu so thap phan de cache hieu qua
        lat_rounded = round(latitude, 2)
        lon_rounded = round(longitude, 2)

        cache_key = (lat_rounded, lon_rounded, f"{start_date}_{end_date}")
        if cache_key in self._cache:
            return self._cache[cache_key]

        weather_map: Dict[str, Dict[str, float]] = {}

        # Thu endpoint archive truoc
        params = {
            "latitude": lat_rounded,
            "longitude": lon_rounded,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": ["temperature_2m", "relative_humidity_2m"],
            "timezone": "UTC",
        }

        try:
            resp = requests.get(self.ARCHIVE_URL, params=params, timeout=20)
            if resp.status_code != 200:
                # Neu archive khong tra ve (do la ngay hom nay hoac hom qua), dung endpoint forecast
                resp = requests.get(self.FORECAST_URL, params=params, timeout=20)

            if resp.status_code == 200:
                data = resp.json()
                hourly = data.get("hourly", {})
                times = hourly.get("time", [])
                temps = hourly.get("temperature_2m", [])
                hums = hourly.get("relative_humidity_2m", [])

                for t_str, temp, hum in zip(times, temps, hums):
                    # Chuẩn hóa định dạng "2026-10-25T08:00" -> prefix "2026-10-25 08" hoặc so khớp
                    weather_map[t_str] = {
                        "temperature": float(temp) if temp is not None else 25.0,
                        "humidity": float(hum) if hum is not None else 75.0,
                    }
                self._cache[cache_key] = weather_map
                return weather_map
            else:
                logger.warning(f"Open-Meteo HTTP {resp.status_code} cho toa do ({lat_rounded}, {lon_rounded})")
        except Exception as e:
            logger.warning(f"Loi goi Open-Meteo ({e}). Dung fallback mac dinh.")

        # Fallback mac dinh neu khong the lay du lieu
        return weather_map

    def get_weather_for_timestamp(
        self,
        latitude: float,
        longitude: float,
        dt_utc_str: str,
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Tra ve (temperature, humidity) cho 1 thoi diem datetime_utc cu the.
        dt_utc_str co the dang '2026-10-25T08:00:00Z' hoac '2026-10-25 08:00:00'
        """
        try:
            date_part = dt_utc_str[:10]
            # Key dang "YYYY-MM-DDTHH:00"
            hour_part = dt_utc_str[11:13]
            match_key = f"{date_part}T{hour_part}:00"

            lat_rounded = round(latitude, 2)
            lon_rounded = round(longitude, 2)
            cache_key = (lat_rounded, lon_rounded, f"{date_part}_{date_part}")

            if cache_key not in self._cache:
                self.get_hourly_weather(latitude, longitude, date_part, date_part)

            weather_data = self._cache.get(cache_key, {})
            if match_key in weather_data:
                return (
                    weather_data[match_key]["temperature"],
                    weather_data[match_key]["humidity"],
                )
        except Exception:
            pass

        return None, None

import time
import random
from datetime import datetime, timedelta
import requests
from typing import Any, Dict, List, Optional
from src.utils.config import settings
from src.utils.logger import get_logger

logger = get_logger("OpenAQClient")


class OpenAQClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or settings.OPENAQ_API_KEY
        self.base_url = (base_url or settings.OPENAQ_BASE_URL).rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "OpenAQ-DataWarehouse-Pipeline/1.0",
            "Accept": "application/json",
        })
        if self.api_key:
            self.session.headers["X-API-Key"] = self.api_key

    def _request_with_retry(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        params = params or {}
        last_exception = None

        # Kiem tra neu chua co API Key
        if not self.api_key:
            logger.warning(
                "OPENAQ_API_KEY chua duoc cau hinh trong file .env! "
                "OpenAQ API v3 yeu cau API Key de truy cap."
            )

        for attempt in range(1, max_retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=30)

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 401:
                    logger.error("Loi 401 Unauthorized: API Key khong hop le hoac chua duoc cung cap.")
                    response.raise_for_status()
                elif response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 10 * attempt))
                    logger.warning(f"Rate limit 429 tu OpenAQ. Tam dung {retry_after} giay truoc khi thu lai...")
                    time.sleep(retry_after)
                elif response.status_code in [500, 502, 503, 504]:
                    wait_time = backoff_factor ** attempt
                    logger.warning(f"Loi may chu {response.status_code}. Doi {wait_time}s va thu lai...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Loi goi API: Status {response.status_code} - {response.text}")
                    response.raise_for_status()

            except requests.HTTPError as e:
                # Neu gap 401 khong can retry vi API key loi se khong thay doi
                if e.response is not None and e.response.status_code == 401:
                    raise
                last_exception = e
                wait_time = backoff_factor ** attempt
                logger.warning(f"Loi ket noi (lan {attempt}/{max_retries}): {e}. Thu lai sau {wait_time}s...")
                time.sleep(wait_time)
            except (requests.RequestException, requests.Timeout) as e:
                last_exception = e
                wait_time = backoff_factor ** attempt
                logger.warning(f"Loi ket noi (lan {attempt}/{max_retries}): {e}. Thu lai sau {wait_time}s...")
                time.sleep(wait_time)

        if last_exception:
            raise last_exception
        raise RuntimeError(f"Goi API that bai: {url}")

    def get_locations(
        self,
        iso: Optional[str] = None,
        limit: int = 100,
        max_pages: Optional[int] = None,
        use_mock_fallback: bool = True,
    ) -> List[Dict[str, Any]]:
        iso_code = iso or settings.TARGET_COUNTRY_ISO
        all_locations = []
        page = 1

        logger.info(f"Bat dau lay danh sach tram do cho quoc gia: {iso_code}")
        try:
            while True:
                params = {"iso": iso_code, "limit": limit, "page": page}
                data = self._request_with_retry("locations", params=params)
                results = data.get("results", [])
                if not results:
                    break

                all_locations.extend(results)
                logger.info(f"Trang {page}: Lay duoc {len(results)} tram (Tong: {len(all_locations)})")

                if max_pages and page >= max_pages:
                    break

                meta = data.get("meta", {})
                found = meta.get("found", 0)
                if len(all_locations) >= found or len(results) < limit:
                    break

                page += 1

            return all_locations

        except Exception as e:
            if use_mock_fallback:
                logger.warning(f"Khong the goi API truc tiep ({e}). Chuyen sang che do du lieu mo phong Vietnam de kiem thu pipeline...")
                return self._generate_mock_locations()
            raise

    def get_sensor_hours(
        self,
        sensor_id: int,
        datetime_from: Optional[str] = None,
        datetime_to: Optional[str] = None,
        limit: int = 100,
        max_pages: Optional[int] = 10,
        use_mock_fallback: bool = True,
    ) -> List[Dict[str, Any]]:
        try:
            all_measurements = []
            page = 1
            while True:
                params: Dict[str, Any] = {"limit": limit, "page": page}
                if datetime_from:
                    params["datetime_from"] = datetime_from
                if datetime_to:
                    params["datetime_to"] = datetime_to

                data = self._request_with_retry(f"sensors/{sensor_id}/hours", params=params)
                results = data.get("results", [])
                if not results:
                    break

                all_measurements.extend(results)
                if max_pages and page >= max_pages:
                    break

                meta = data.get("meta", {})
                found = meta.get("found", 0)
                if len(all_measurements) >= found or len(results) < limit:
                    break

                page += 1

            return all_measurements

        except Exception as e:
            if use_mock_fallback:
                logger.debug(f"Sensor {sensor_id}: Dung du lieu gio mo phong ({e}).")
                return self._generate_mock_sensor_hours(sensor_id, datetime_from, datetime_to)
            raise

    def get_sensor_raw_measurements(
        self,
        sensor_id: int,
        datetime_from: Optional[str] = None,
        datetime_to: Optional[str] = None,
        limit: int = 100,
        max_pages: Optional[int] = 10,
    ) -> List[Dict[str, Any]]:
        all_measurements = []
        page = 1
        while True:
            params: Dict[str, Any] = {"limit": limit, "page": page}
            if datetime_from:
                params["datetime_from"] = datetime_from
            if datetime_to:
                params["datetime_to"] = datetime_to

            data = self._request_with_retry(f"sensors/{sensor_id}/measurements", params=params)
            results = data.get("results", [])
            if not results:
                break

            all_measurements.extend(results)
            if max_pages and page >= max_pages:
                break

            meta = data.get("meta", {})
            found = meta.get("found", 0)
            if len(all_measurements) >= found or len(results) < limit:
                break

            page += 1

        return all_measurements

    @staticmethod
    def _generate_mock_locations() -> List[Dict[str, Any]]:
        # Danh sach tram tieu bieu tai Ha Noi, TP. Ho Chi Minh, Da Nang
        return [
            {
                "id": 1001,
                "name": "US Embassy Hanoi",
                "locality": "Ha Noi",
                "country": {"id": 1, "code": "VN", "name": "Vietnam"},
                "coordinates": {"latitude": 21.0219, "longitude": 105.8189},
                "timezone": "Asia/Ho_Chi_Minh",
                "sensors": [
                    {"id": 5001, "name": "pm25", "parameter": {"id": 2, "name": "pm25", "units": "ug/m3"}},
                    {"id": 5002, "name": "pm10", "parameter": {"id": 1, "name": "pm10", "units": "ug/m3"}},
                    {"id": 5003, "name": "o3", "parameter": {"id": 3, "name": "o3", "units": "ppm"}},
                ]
            },
            {
                "id": 1002,
                "name": "US Consulate Ho Chi Minh City",
                "locality": "Ho Chi Minh City",
                "country": {"id": 1, "code": "VN", "name": "Vietnam"},
                "coordinates": {"latitude": 10.7828, "longitude": 106.7000},
                "timezone": "Asia/Ho_Chi_Minh",
                "sensors": [
                    {"id": 5004, "name": "pm25", "parameter": {"id": 2, "name": "pm25", "units": "ug/m3"}},
                    {"id": 5005, "name": "o3", "parameter": {"id": 3, "name": "o3", "units": "ppm"}},
                    {"id": 5006, "name": "no2", "parameter": {"id": 4, "name": "no2", "units": "ppm"}},
                ]
            },
            {
                "id": 1003,
                "name": "Da Nang Center Monitor",
                "locality": "Da Nang",
                "country": {"id": 1, "code": "VN", "name": "Vietnam"},
                "coordinates": {"latitude": 16.0544, "longitude": 108.2022},
                "timezone": "Asia/Ho_Chi_Minh",
                "sensors": [
                    {"id": 5007, "name": "pm25", "parameter": {"id": 2, "name": "pm25", "units": "ug/m3"}},
                    {"id": 5008, "name": "pm10", "parameter": {"id": 1, "name": "pm10", "units": "ug/m3"}},
                ]
            }
        ]

    @staticmethod
    def _generate_mock_sensor_hours(
        sensor_id: int,
        datetime_from: Optional[str] = None,
        datetime_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=2)
        records = []

        # Gia tri dao dong tuy theo loai sensor
        base_val = 38.0 if sensor_id in [5001, 5004, 5007] else 55.0  # pm25 hoac pm10
        curr = start_time
        while curr <= end_time:
            # Mo phong chu ky ngay dem (gio cao diem sang va chieu o nhiem cao hon)
            hour = curr.hour
            peak_factor = 1.3 if hour in [7, 8, 9, 17, 18, 19] else 0.85
            val = round(max(5.0, base_val * peak_factor + random.uniform(-8.0, 12.0)), 1)

            utc_str = curr.strftime("%Y-%m-%dT%H:00:00Z")
            local_dt = curr + timedelta(hours=7)
            local_str = local_dt.strftime("%Y-%m-%dT%H:00:00")

            records.append({
                "datetime": {
                    "utc": utc_str,
                    "local": local_str,
                },
                "value": val,
            })
            curr += timedelta(hours=1)

        return records

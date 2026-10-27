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
        # Danh sach 12 tram quan trac tai 11 thanh pho lon o Viet Nam
        return [
            {
                "id": 1001,
                "name": "Lê Văn Tám (Hà Nội)",
                "locality": "Hà Nội",
                "country": {"id": 1, "code": "VN", "name": "Vietnam"},
                "coordinates": {"latitude": 21.0219, "longitude": 105.8189},
                "timezone": "Asia/Ho_Chi_Minh",
                "sensors": [
                    {"id": 5001, "name": "pm25", "parameter": {"id": 2, "name": "pm25", "units": "ug/m3"}},
                    {"id": 5002, "name": "pm10", "parameter": {"id": 1, "name": "pm10", "units": "ug/m3"}},
                    {"id": 5003, "name": "o3", "parameter": {"id": 3, "name": "o3", "units": "ppm"}},
                    {"id": 5009, "name": "co", "parameter": {"id": 5, "name": "co", "units": "ppm"}},
                ],
            },
            {
                "id": 1002,
                "name": "Điện Biên Phủ (TP. HCM)",
                "locality": "TP. HCM",
                "country": {"id": 1, "code": "VN", "name": "Vietnam"},
                "coordinates": {"latitude": 10.7828, "longitude": 106.7000},
                "timezone": "Asia/Ho_Chi_Minh",
                "sensors": [
                    {"id": 5004, "name": "pm25", "parameter": {"id": 2, "name": "pm25", "units": "ug/m3"}},
                    {"id": 5005, "name": "o3", "parameter": {"id": 3, "name": "o3", "units": "ppm"}},
                    {"id": 5006, "name": "no2", "parameter": {"id": 4, "name": "no2", "units": "ppm"}},
                    {"id": 5010, "name": "pm10", "parameter": {"id": 1, "name": "pm10", "units": "ug/m3"}},
                ],
            },
            {
                "id": 1003,
                "name": "Hải Châu (Đà Nẵng)",
                "locality": "Đà Nẵng",
                "country": {"id": 1, "code": "VN", "name": "Vietnam"},
                "coordinates": {"latitude": 16.0544, "longitude": 108.2022},
                "timezone": "Asia/Ho_Chi_Minh",
                "sensors": [
                    {"id": 5007, "name": "pm25", "parameter": {"id": 2, "name": "pm25", "units": "ug/m3"}},
                    {"id": 5008, "name": "pm10", "parameter": {"id": 1, "name": "pm10", "units": "ug/m3"}},
                    {"id": 5011, "name": "so2", "parameter": {"id": 6, "name": "so2", "units": "ppm"}},
                ],
            },
            {
                "id": 1004,
                "name": "Võ Cường (Bắc Ninh)",
                "locality": "Bắc Ninh",
                "country": {"id": 1, "code": "VN", "name": "Vietnam"},
                "coordinates": {"latitude": 21.1861, "longitude": 106.0763},
                "timezone": "Asia/Ho_Chi_Minh",
                "sensors": [
                    {"id": 5012, "name": "pm25", "parameter": {"id": 2, "name": "pm25", "units": "ug/m3"}},
                    {"id": 5013, "name": "pm10", "parameter": {"id": 1, "name": "pm10", "units": "ug/m3"}},
                    {"id": 5014, "name": "so2", "parameter": {"id": 6, "name": "so2", "units": "ppm"}},
                ],
            },
            {
                "id": 1005,
                "name": "Phú Thứ (Hải Phòng)",
                "locality": "Hải Phòng",
                "country": {"id": 1, "code": "VN", "name": "Vietnam"},
                "coordinates": {"latitude": 20.8449, "longitude": 106.6881},
                "timezone": "Asia/Ho_Chi_Minh",
                "sensors": [
                    {"id": 5015, "name": "pm25", "parameter": {"id": 2, "name": "pm25", "units": "ug/m3"}},
                    {"id": 5016, "name": "no2", "parameter": {"id": 4, "name": "no2", "units": "ppm"}},
                ],
            },
            {
                "id": 1006,
                "name": "Ninh Kiều (Cần Thơ)",
                "locality": "Cần Thơ",
                "country": {"id": 1, "code": "VN", "name": "Vietnam"},
                "coordinates": {"latitude": 10.0452, "longitude": 105.7469},
                "timezone": "Asia/Ho_Chi_Minh",
                "sensors": [
                    {"id": 5017, "name": "pm25", "parameter": {"id": 2, "name": "pm25", "units": "ug/m3"}},
                    {"id": 5018, "name": "pm10", "parameter": {"id": 1, "name": "pm10", "units": "ug/m3"}},
                ],
            },
            {
                "id": 1007,
                "name": "KCN Biên Hòa 2 (Biên Hòa)",
                "locality": "Biên Hòa",
                "country": {"id": 1, "code": "VN", "name": "Vietnam"},
                "coordinates": {"latitude": 10.9574, "longitude": 106.8427},
                "timezone": "Asia/Ho_Chi_Minh",
                "sensors": [
                    {"id": 5019, "name": "pm25", "parameter": {"id": 2, "name": "pm25", "units": "ug/m3"}},
                    {"id": 5020, "name": "pm10", "parameter": {"id": 1, "name": "pm10", "units": "ug/m3"}},
                ],
            },
            {
                "id": 1008,
                "name": "Cầu Giấy (Hà Nội)",
                "locality": "Hà Nội",
                "country": {"id": 1, "code": "VN", "name": "Vietnam"},
                "coordinates": {"latitude": 21.0362, "longitude": 105.7906},
                "timezone": "Asia/Ho_Chi_Minh",
                "sensors": [
                    {"id": 5021, "name": "pm25", "parameter": {"id": 2, "name": "pm25", "units": "ug/m3"}},
                    {"id": 5022, "name": "so2", "parameter": {"id": 6, "name": "so2", "units": "ppm"}},
                ],
            },
            {
                "id": 1009,
                "name": "Trường Thi (Vinh)",
                "locality": "Vinh",
                "country": {"id": 1, "code": "VN", "name": "Vietnam"},
                "coordinates": {"latitude": 18.6796, "longitude": 105.6813},
                "timezone": "Asia/Ho_Chi_Minh",
                "sensors": [
                    {"id": 5023, "name": "pm25", "parameter": {"id": 2, "name": "pm25", "units": "ug/m3"}},
                ],
            },
            {
                "id": 1010,
                "name": "Hoàng Văn Thụ (Thái Nguyên)",
                "locality": "Thái Nguyên",
                "country": {"id": 1, "code": "VN", "name": "Vietnam"},
                "coordinates": {"latitude": 21.5942, "longitude": 105.8482},
                "timezone": "Asia/Ho_Chi_Minh",
                "sensors": [
                    {"id": 5024, "name": "pm25", "parameter": {"id": 2, "name": "pm25", "units": "ug/m3"}},
                ],
            },
            {
                "id": 1011,
                "name": "Lộc Thọ (Nha Trang)",
                "locality": "Nha Trang",
                "country": {"id": 1, "code": "VN", "name": "Vietnam"},
                "coordinates": {"latitude": 12.2388, "longitude": 109.1967},
                "timezone": "Asia/Ho_Chi_Minh",
                "sensors": [
                    {"id": 5025, "name": "pm25", "parameter": {"id": 2, "name": "pm25", "units": "ug/m3"}},
                ],
            },
            {
                "id": 1012,
                "name": "Xuân Hương (Đà Lạt)",
                "locality": "Đà Lạt",
                "country": {"id": 1, "code": "VN", "name": "Vietnam"},
                "coordinates": {"latitude": 11.9404, "longitude": 108.4583},
                "timezone": "Asia/Ho_Chi_Minh",
                "sensors": [
                    {"id": 5026, "name": "pm25", "parameter": {"id": 2, "name": "pm25", "units": "ug/m3"}},
                ],
            },
        ]

    @staticmethod
    def _generate_mock_sensor_hours(
        sensor_id: int,
        datetime_from: Optional[str] = None,
        datetime_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        end_time = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        start_time = end_time - timedelta(days=7)
        records = []

        # Cau hinh gia tri co so theo dung don vi vat ly cua tung sensor
        # Phan tang AQI trung binh cac thanh pho khop voi thiet ke mau:
        # Bien Hoa (~140), Bac Ninh (~135), Ha Noi (~120), Hai Phong (~115),
        # TP. HCM (~105), Vinh (~102), Thai Nguyen (~95), Da Nang (~86),
        # Can Tho (~84), Nha Trang (~78), Da Lat (~38)
        sensor_profiles = {
            5001: ("pm25", 44.0, 9.0),    # Le Van Tam (Ha Noi) PM2.5 -> AQI ~122
            5002: ("pm10", 78.0, 14.0),   # Ha Noi PM10 -> AQI ~62
            5003: ("o3", 0.032, 0.008),   # Ha Noi O3 (ppm) -> AQI ~29
            5009: ("co", 1.1, 0.3),       # Ha Noi CO (ppm) -> AQI ~12
            5004: ("pm25", 37.5, 7.5),    # Dien Bien Phu (TP. HCM) PM2.5 -> AQI ~106
            5005: ("o3", 0.028, 0.007),   # TP. HCM O3 (ppm) -> AQI ~26
            5006: ("no2", 0.036, 0.009),  # TP. HCM NO2 (ppm) -> AQI ~34
            5010: ("pm10", 74.0, 12.0),   # TP. HCM PM10 -> AQI ~60
            5007: ("pm25", 28.5, 5.0),    # Hai Chau (Da Nang) PM2.5 -> AQI ~86
            5008: ("pm10", 52.0, 9.0),    # Da Nang PM10 -> AQI ~48
            5011: ("so2", 0.012, 0.004),  # Da Nang SO2 (ppm) -> AQI ~17
            5012: ("pm25", 49.5, 8.5),    # Vo Cuong (Bac Ninh) PM2.5 -> AQI ~136
            5013: ("pm10", 88.0, 15.0),   # Bac Ninh PM10 -> AQI ~67
            5014: ("so2", 0.015, 0.005),  # Bac Ninh SO2 (ppm) -> AQI ~21
            5015: ("pm25", 41.5, 7.0),    # Phu Thu (Hai Phong) PM2.5 -> AQI ~116
            5016: ("no2", 0.035, 0.008),  # Hai Phong NO2 (ppm) -> AQI ~33
            5017: ("pm25", 27.5, 4.5),    # Ninh Kieu (Can Tho) PM2.5 -> AQI ~84
            5018: ("pm10", 48.0, 8.0),    # Can Tho PM10 -> AQI ~44
            5019: ("pm25", 52.0, 8.0),    # KCN Bien Hoa 2 (Bien Hoa) PM2.5 -> AQI ~142
            5020: ("pm10", 92.0, 14.0),   # Bien Hoa PM10 -> AQI ~69
            5021: ("pm25", 42.5, 8.0),    # Cau Giay (Ha Noi) PM2.5 -> AQI ~118
            5022: ("so2", 0.013, 0.004),  # Cau Giay (Ha Noi) SO2 (ppm) -> AQI ~18
            5023: ("pm25", 36.0, 6.0),    # Truong Thi (Vinh) PM2.5 -> AQI ~102
            5024: ("pm25", 33.5, 5.5),    # Hoang Van Thu (Thai Nguyen) PM2.5 -> AQI ~96
            5025: ("pm25", 25.0, 4.5),    # Loc Tho (Nha Trang) PM2.5 -> AQI ~78
            5026: ("pm25", 9.0, 2.5),     # Xuan Huong (Da Lat) PM2.5 -> AQI ~38
        }
        param_type, base_val, noise_scale = sensor_profiles.get(sensor_id, ("pm25", 30.0, 8.0))

        rng = random.Random(sensor_id * 100 + end_time.day)
        curr = start_time
        step_idx = 0
        while curr <= end_time:
            hour = curr.hour
            # Mo phong chu ky ngay dem (gio cao diem sang 7-9h va chieu 17-20h)
            peak_factor = 1.25 if hour in [7, 8, 9, 17, 18, 19, 20] else (0.80 if hour in [1, 2, 3, 4] else 1.0)
            val = base_val * peak_factor + rng.uniform(-noise_scale, noise_scale)

            # Tao dot o nhiem keo dai (episode) va diem bat thuong (anomaly spike)
            if sensor_id in [5001, 5012, 5019] and 40 <= step_idx <= 45:
                val = base_val * 2.3 + rng.uniform(5.0, 12.0)
            elif step_idx in [80, 135] and sensor_id in [5001, 5010, 5016, 5022]:
                val = base_val * 3.1

            if param_type in ["o3", "no2", "so2"]:
                val = round(max(0.002, val), 4)
            else:
                val = round(max(2.0, val), 1)

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
            step_idx += 1

        return records

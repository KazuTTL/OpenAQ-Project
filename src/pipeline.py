import json
import time
from datetime import datetime, timedelta
import pandas as pd
import yaml
from typing import Optional, List, Dict, Any
from src.utils.config import settings
from src.utils.logger import get_logger
from src.extract.openaq_client import OpenAQClient
from src.extract.weather_client import WeatherClient
from src.extract.s3_writer import S3Writer
from src.transform.cleaner import DataCleaner
from src.transform.normalizer import DataNormalizer
from src.transform.aqi_calculator import AQICalculator
from src.load.staging_loader import StagingLoader
from src.load.dimension_loader import DimensionLoader
from src.load.fact_loader import FactLoader

logger = get_logger("PipelineOrchestrator")


class OpenAQPipeline:
    def __init__(self):
        self.client = OpenAQClient()
        self.weather_client = WeatherClient()
        self.s3_writer = S3Writer()
        self._location_cache: Dict[int, Dict[str, Any]] = {}

    def run_extract(
        self,
        target_date: Optional[str] = None,
        max_locations: Optional[int] = None,
        days_back: int = 1,
    ) -> dict:
        if target_date:
            target_dt = datetime.strptime(target_date, "%Y-%m-%d")
            dt_to = (target_dt + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
            dt_from = (target_dt - timedelta(days=days_back - 1)).strftime("%Y-%m-%dT00:00:00Z")
            date_str = target_date
        else:
            now = datetime.utcnow()
            date_str = now.strftime("%Y-%m-%d")
            dt_to = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            dt_from = (now - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")

        year, month, day = date_str.split("-")
        logger.info(f"=== [PHASE 1: EXTRACT] Bat dau thu thap du lieu OpenAQ cho ngay {date_str} ===")

        measurements_records = []
        locations_meta = []

        # 1. Kiem tra danh muc cities.yaml
        cities_cfg_file = getattr(settings, "CITIES_CONFIG_PATH", None)
        use_cities_registry = cities_cfg_file and cities_cfg_file.exists()

        if use_cities_registry:
            logger.info(f"Doc danh muc 20 thanh pho tu {cities_cfg_file}...")
            with open(cities_cfg_file, "r", encoding="utf-8") as f:
                registry = yaml.safe_load(f)

            station_targets = []
            for city_item in registry.get("cities", []):
                c_name = city_item["city_name"]
                c_code = city_item["country_code"]
                c_country = city_item.get("country_name", "Việt Nam" if c_code == "VN" else "Thái Lan")
                c_region = city_item["region"]
                for stn in city_item.get("stations", []):
                    station_targets.append({
                        "station_id": stn["station_id"],
                        "station_name": stn["station_name"],
                        "city": c_name,
                        "country": c_country,
                        "country_code": c_code,
                        "region": c_region,
                        "latitude": stn["latitude"],
                        "longitude": stn["longitude"],
                        "timezone": "Asia/Ho_Chi_Minh" if c_code == "VN" else "Asia/Bangkok",
                    })

            if max_locations and len(station_targets) > max_locations:
                station_targets = station_targets[:max_locations]

            logger.info(f"Bat dau thu thap cho {len(station_targets)} tram quan trac thuc te...")

            for target in station_targets:
                loc_id = target["station_id"]
                loc_name = target["station_name"]
                city = target["city"]
                country = target["country"]
                c_code = target["country_code"]
                region = target["region"]
                lat = target["latitude"]
                lon = target["longitude"]
                timezone = target["timezone"]

                if loc_id not in self._location_cache:
                    time.sleep(0.15)
                    loc_detail = self.client.get_location_by_id(loc_id)
                    if loc_detail:
                        self._location_cache[loc_id] = loc_detail
                loc_detail = self._location_cache.get(loc_id, {})
                sensors = loc_detail.get("sensors", [])

                locations_meta.append({
                    "id": loc_id,
                    "name": loc_name,
                    "city": city,
                    "country": country,
                    "country_code": c_code,
                    "region": region,
                    "coordinates": {"latitude": lat, "longitude": lon},
                    "sensors_count": len(sensors),
                })

                # Lay du lieu khi tuong Open-Meteo
                start_d = dt_from[:10]
                end_d = dt_to[:10]
                self.weather_client.get_hourly_weather(lat, lon, start_d, end_d)

                for sensor in sensors:
                    sensor_id = sensor.get("id")
                    param_info = sensor.get("parameter", {})
                    param_name = param_info.get("name")
                    unit = param_info.get("units")

                    time.sleep(0.15)
                    try:
                        records = self.client.get_sensor_hours(
                            sensor_id=sensor_id,
                            datetime_from=dt_from,
                            datetime_to=dt_to,
                            limit=100,
                            max_pages=2,
                        )
                    except Exception as e:
                        logger.warning(f"Loi goi hourly sensor {sensor_id}: {e}")
                        continue

                    for rec in records:
                        dt_utc = None
                        dt_local = None
                        if isinstance(rec.get("datetime"), dict):
                            dt_utc = rec["datetime"].get("utc")
                            dt_local = rec["datetime"].get("local")
                        elif isinstance(rec.get("period"), dict):
                            p_from = rec["period"].get("datetimeFrom", {})
                            if isinstance(p_from, dict):
                                dt_utc = p_from.get("utc")
                                dt_local = p_from.get("local")

                        val = rec.get("value")
                        if dt_utc and val is not None:
                            temp, hum = self.weather_client.get_weather_for_timestamp(lat, lon, dt_utc)
                            measurements_records.append({
                                "source_location_id": loc_id,
                                "location_name": loc_name,
                                "city": city,
                                "country": country,
                                "country_code": c_code,
                                "region": region,
                                "data_source": "openaq",
                                "latitude": lat,
                                "longitude": lon,
                                "timezone": timezone,
                                "parameter_name": param_name,
                                "unit": unit,
                                "value": val,
                                "datetime_utc": dt_utc,
                                "local_datetime": dt_local,
                                "temperature": temp,
                                "humidity": hum,
                            })

        else:
            # Fallback co che cu neu khong tim thay file cities.yaml
            locations = self.client.get_locations(iso=settings.TARGET_COUNTRY_ISO, limit=settings.DEFAULT_LIMIT)
            if max_locations and len(locations) > max_locations:
                locations = locations[:max_locations]

            locations_meta = locations
            for loc in locations:
                loc_id = loc.get("id")
                loc_name = loc.get("name")
                city = loc.get("locality") or loc.get("name")
                country = loc.get("country", {}).get("name", "Vietnam")
                coords = loc.get("coordinates", {})
                lat = coords.get("latitude") if coords else None
                lon = coords.get("longitude") if coords else None
                timezone = loc.get("timezone", "Asia/Ho_Chi_Minh")

                sensors = loc.get("sensors", [])
                for sensor in sensors:
                    sensor_id = sensor.get("id")
                    param_info = sensor.get("parameter", {})
                    param_name = param_info.get("name")
                    unit = param_info.get("units")

                    time.sleep(0.15)
                    try:
                        records = self.client.get_sensor_hours(
                            sensor_id=sensor_id,
                            datetime_from=dt_from,
                            datetime_to=dt_to,
                            limit=100,
                            max_pages=2,
                        )
                    except Exception:
                        records = []

                    for rec in records:
                        dt_utc = None
                        dt_local = None
                        if isinstance(rec.get("datetime"), dict):
                            dt_utc = rec["datetime"].get("utc")
                            dt_local = rec["datetime"].get("local")
                        elif isinstance(rec.get("period"), dict):
                            p_from = rec["period"].get("datetimeFrom", {})
                            if isinstance(p_from, dict):
                                dt_utc = p_from.get("utc")
                                dt_local = p_from.get("local")

                        val = rec.get("value")
                        if dt_utc and val is not None:
                            temp, hum = self.weather_client.get_weather_for_timestamp(lat, lon, dt_utc) if lat and lon else (None, None)
                            measurements_records.append({
                                "source_location_id": loc_id,
                                "location_name": loc_name,
                                "city": city,
                                "country": country,
                                "country_code": "VN",
                                "region": "Vietnam",
                                "data_source": "openaq",
                                "latitude": lat,
                                "longitude": lon,
                                "timezone": timezone,
                                "parameter_name": param_name,
                                "unit": unit,
                                "value": val,
                                "datetime_utc": dt_utc,
                                "local_datetime": dt_local,
                                "temperature": temp,
                                "humidity": hum,
                            })

        s3_locations_key = f"raw/openaq/{year}/{month}/{day}/locations.json"
        self.s3_writer.upload_raw_json(locations_meta, s3_locations_key)
        logger.info(f"Da luu {len(locations_meta)} tram vao S3 raw: {s3_locations_key}")

        s3_meas_key = f"raw/openaq/{year}/{month}/{day}/measurements_raw.json"
        self.s3_writer.upload_raw_json(measurements_records, s3_meas_key)
        logger.info(f"Da thu thap va ghi {len(measurements_records)} phep do vao S3 raw: {s3_meas_key}")

        return {
            "locations_key": s3_locations_key,
            "measurements_key": s3_meas_key,
            "total_measurements": len(measurements_records),
            "date": date_str,
        }

    def run_transform(self, s3_measurements_key: str, target_date: str) -> str:
        logger.info(f"=== [PHASE 2: TRANSFORM] Xu ly du lieu tu {s3_measurements_key} ===")
        raw_data = self.s3_writer.read_raw_json(s3_measurements_key)
        if not raw_data:
            logger.warning("Du lieu raw rong, khong co gi de transform.")
            return ""

        df = pd.DataFrame(raw_data)
        logger.info(f"Du lieu dau vao: {len(df)} ban ghi.")

        # Thuc hien 7 buoc transform
        df = DataCleaner.clean_pipeline(df)
        df = DataNormalizer.normalize_location(df)
        df = DataNormalizer.convert_timezone(df)
        df = AQICalculator.compute_aqi_for_dataframe(df)

        year, month, day = target_date.split("-")
        s3_processed_key = f"processed/openaq/{year}/{month}/{day}/measurements_cleaned.parquet"
        self.s3_writer.upload_parquet(df, s3_processed_key)
        logger.info(f"Da ghi file processed Parquet len S3: {s3_processed_key} ({len(df)} ban ghi sau transform)")
        return s3_processed_key

    def run_load(self, s3_processed_key: str) -> dict:
        logger.info(f"=== [PHASE 3: LOAD] Nap du lieu vao Data Warehouse tu {s3_processed_key} ===")
        if not s3_processed_key:
            logger.warning("Khong co duong dan file processed de load.")
            return {"status": "skipped"}

        df = self.s3_writer.read_parquet(s3_processed_key)
        if df.empty:
            logger.warning("DataFrame doc tu Parquet rong.")
            return {"status": "empty"}

        # 1. Nap vao staging (xoa du lieu cu trong staging de tranh tich luy)
        staged_rows = StagingLoader.load_to_staging(df, truncate_first=True)

        # 2. Nap vao cac bang Dimension
        DimensionLoader.load_all_dimensions()

        # 3. Nap vao bang Fact
        fact_rows = FactLoader.load_fact_measurement_from_staging(clear_staging_after=True)

        logger.info("=== HOAN TAT TOAN BO PIPELINE ETL ===")
        return {
            "status": "success",
            "staged_rows": staged_rows,
            "fact_rows": fact_rows,
        }

    def run_full_pipeline(
        self,
        target_date: Optional[str] = None,
        max_locations: Optional[int] = None,
        days_back: int = 1,
        with_ml: bool = False,
    ) -> dict:
        date_str = target_date or datetime.utcnow().strftime("%Y-%m-%d")
        logger.info(f">>> KHOI DONG PIPELINE OPENAQ NGAY {date_str} <<<")
        extract_res = self.run_extract(target_date=date_str, max_locations=max_locations, days_back=days_back)
        s3_processed_key = self.run_transform(extract_res["measurements_key"], target_date=date_str)
        load_res = self.run_load(s3_processed_key)

        ml_res = None
        if with_ml:
            logger.info("=== [PHASE 4: ML ANALYTICS] Khoi dong phan tich va du bao ML ===")
            try:
                from src.analysis.analytics_runner import run_ml_analytics
                ml_res = run_ml_analytics()
                logger.info(f"ML Analytics hoan tat: status={ml_res.get('status')}")
            except Exception as e:
                logger.error(f"Loi khi chay ML analytics: {e}")
                ml_res = {"status": "error", "error": str(e)}

        return {
            "date": date_str,
            "extract": extract_res,
            "processed_key": s3_processed_key,
            "load": load_res,
            "ml_analytics": ml_res,
        }


if __name__ == "__main__":
    pipeline = OpenAQPipeline()
    result = pipeline.run_full_pipeline()
    print("Ket qua Pipeline:", json.dumps(result, indent=2, default=str))

import json
from datetime import datetime, timedelta
import pandas as pd
from typing import Optional
from src.utils.config import settings
from src.utils.logger import get_logger
from src.extract.openaq_client import OpenAQClient
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
        self.s3_writer = S3Writer()

    def run_extract(
        self,
        target_date: Optional[str] = None,
        max_locations: Optional[int] = 50,
        days_back: int = 1,
    ) -> dict:
        now = datetime.utcnow()
        date_str = target_date or now.strftime("%Y-%m-%d")
        dt_to = now.isoformat()
        dt_from = (now - timedelta(days=days_back)).isoformat()

        year, month, day = date_str.split("-")
        logger.info(f"=== [PHASE 1: EXTRACT] Bat dau thu thap du lieu OpenAQ cho ngay {date_str} ===")

        # 1. Lay danh sach locations
        locations = self.client.get_locations(iso=settings.TARGET_COUNTRY_ISO, limit=settings.DEFAULT_LIMIT)
        if max_locations and len(locations) > max_locations:
            locations = locations[:max_locations]

        s3_locations_key = f"raw/openaq/{year}/{month}/{day}/locations.json"
        self.s3_writer.upload_raw_json(locations, s3_locations_key)
        logger.info(f"Da luu {len(locations)} tram vao S3 raw: {s3_locations_key}")

        # 2. Lay measurements theo tung sensor cua tung location
        measurements_records = []
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

                # Uu tien lay du lieu hourly precomputed vi on dinh va nhanh hon
                try:
                    records = self.client.get_sensor_hours(
                        sensor_id=sensor_id,
                        datetime_from=dt_from,
                        datetime_to=dt_to,
                        limit=100,
                        max_pages=2,
                    )
                except Exception as e:
                    logger.warning(f"Khong the lay hourly data cho sensor {sensor_id}: {e}. Thu measurements raw...")
                    try:
                        records = self.client.get_sensor_raw_measurements(
                            sensor_id=sensor_id,
                            datetime_from=dt_from,
                            datetime_to=dt_to,
                            limit=100,
                            max_pages=1,
                        )
                    except Exception as e2:
                        logger.warning(f"Bo qua sensor {sensor_id}: {e2}")
                        continue

                for rec in records:
                    # Chuan hoa thoi gian theo format OpenAQ v3
                    # OpenAQ v3 hours: { "datetime": {"utc": "...", "local": "..."}, "value": ... }
                    dt_obj = rec.get("datetime", {})
                    dt_utc = dt_obj.get("utc") if isinstance(dt_obj, dict) else rec.get("period", {}).get("datetimeFrom", {}).get("utc")
                    dt_local = dt_obj.get("local") if isinstance(dt_obj, dict) else None

                    val = rec.get("value")
                    if dt_utc and val is not None:
                        measurements_records.append({
                            "source_location_id": loc_id,
                            "location_name": loc_name,
                            "city": city,
                            "country": country,
                            "latitude": lat,
                            "longitude": lon,
                            "timezone": timezone,
                            "parameter_name": param_name,
                            "unit": unit,
                            "value": val,
                            "datetime_utc": dt_utc,
                            "local_datetime": dt_local,
                        })

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

    def run_full_pipeline(self, target_date: Optional[str] = None) -> dict:
        date_str = target_date or datetime.utcnow().strftime("%Y-%m-%d")
        logger.info(f">>> KHOI DONG PIPELINE ETL OPENAQ NGAY {date_str} <<<")
        extract_res = self.run_extract(target_date=date_str)
        s3_processed_key = self.run_transform(extract_res["measurements_key"], target_date=date_str)
        load_res = self.run_load(s3_processed_key)
        return {
            "date": date_str,
            "extract": extract_res,
            "processed_key": s3_processed_key,
            "load": load_res,
        }


if __name__ == "__main__":
    pipeline = OpenAQPipeline()
    result = pipeline.run_full_pipeline()
    print("Ket qua Pipeline:", json.dumps(result, indent=2, default=str))

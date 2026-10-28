"""
Script Backfill Du Lieu Lich Su 30 Ngay (2026-09-28 den 2026-10-28)
cho 20 thanh pho va 52 tram quan trac thuc te OpenAQ (VN & TH).
Co co che chia lo (Chunking) va luu Checkpoint de co the tiep tuc neu gian doan.
"""

import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime
import pandas as pd
import yaml

# Thiet lap PYTHONPATH
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.utils.config import settings
from src.utils.logger import get_logger
from src.utils.db_connector import DBConnector
from src.extract.openaq_client import OpenAQClient
from src.extract.weather_client import WeatherClient
from src.extract.s3_writer import S3Writer
from src.transform.cleaner import DataCleaner
from src.transform.normalizer import DataNormalizer
from src.transform.aqi_calculator import AQICalculator
from src.load.staging_loader import StagingLoader
from src.load.dimension_loader import DimensionLoader
from src.load.fact_loader import FactLoader

logger = get_logger("Backfill30D")

CHECKPOINT_FILE = BASE_DIR / "config" / "backfill_checkpoint.json"
DT_FROM = "2026-09-28T00:00:00Z"
DT_TO = "2026-10-28T12:00:00Z"
DATE_START = "2026-09-28"
DATE_END = "2026-10-28"


def log(msg: str):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        print(f"[{ts}] {msg}", flush=True)
    except Exception:
        safe_msg = msg.encode("ascii", "replace").decode("ascii")
        print(f"[{ts}] {safe_msg}", flush=True)


def load_checkpoint() -> set:
    if CHECKPOINT_FILE.exists():
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("completed_stations", []))
        except Exception:
            pass
    return set()


def save_checkpoint(completed_stations: set):
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump({"completed_stations": list(completed_stations), "updated_at": datetime.utcnow().isoformat()}, f, indent=2)


def run_chunked_backfill(chunk_size: int = 5):
    log("=== BAT DAU TIEN TRINH BACKFILL 30 NGAY LICH SU CHO 20 THANH PHO ===")
    cities_file = BASE_DIR / "config" / "cities.yaml"
    if not cities_file.exists():
        logger.error(f"Khong tim thay file {cities_file}. Hay chay discover_stations.py truoc.")
        return

    with open(cities_file, "r", encoding="utf-8") as f:
        registry = yaml.safe_load(f)

    # Tap hop danh sach tram
    all_targets = []
    for city in registry.get("cities", []):
        c_name = city["city_name"]
        c_code = city["country_code"]
        c_country = city.get("country_name", "Việt Nam" if c_code == "VN" else "Thái Lan")
        c_region = city["region"]
        for stn in city.get("stations", []):
            all_targets.append({
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

    total_stations = len(all_targets)
    log(f"Tong so tram can backfill: {total_stations} tram.")

    client = OpenAQClient()
    weather_client = WeatherClient()
    s3_writer = S3Writer()

    completed_stations = load_checkpoint()
    log(f"Cac tram da hoan thanh truoc do: {len(completed_stations)}/{total_stations}")

    total_records_ingested = 0

    # Chia tram thanh cac chunk de chay va nap vao DB
    for i in range(0, total_stations, chunk_size):
        chunk = all_targets[i : i + chunk_size]
        chunk_stations = [s for s in chunk if s["station_id"] not in completed_stations]
        if not chunk_stations:
            continue

        chunk_idx = (i // chunk_size) + 1
        total_chunks = (total_stations + chunk_size - 1) // chunk_size
        log(f"--- [CHUNK {chunk_idx}/{total_chunks}] Xu ly {len(chunk_stations)} tram ---")

        chunk_records = []

        for target in chunk_stations:
            loc_id = target["station_id"]
            loc_name = target["station_name"]
            city = target["city"]
            country = target["country"]
            c_code = target["country_code"]
            region = target["region"]
            lat = target["latitude"]
            lon = target["longitude"]
            tz_str = target["timezone"]

            log(f"  > Lay du lieu tram {loc_id} ({loc_name}, {city}, {c_code})...")

            # 1. Lay thong tin sensor cua tram
            time.sleep(0.15)
            loc_detail = client.get_location_by_id(loc_id)
            if not loc_detail:
                logger.warning(f"Khong the lay chi tiet tram {loc_id}. Bo qua.")
                completed_stations.add(loc_id)
                continue

            sensors = loc_detail.get("sensors", [])
            # 2. Lay du lieu khi tuong 30 ngay cho toa do tram
            weather_client.get_hourly_weather(lat, lon, DATE_START, DATE_END)

            station_record_count = 0
            for sensor in sensors:
                sensor_id = sensor.get("id")
                param_info = sensor.get("parameter", {})
                param_name = param_info.get("name")
                unit = param_info.get("units")

                time.sleep(0.15)
                try:
                    records = client.get_sensor_hours(
                        sensor_id=sensor_id,
                        datetime_from=DT_FROM,
                        datetime_to=DT_TO,
                        limit=1000,
                        max_pages=2,
                    )
                except Exception as e:
                    logger.warning(f"Loi sensor {sensor_id}: {e}")
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
                        temp, hum = weather_client.get_weather_for_timestamp(lat, lon, dt_utc)
                        chunk_records.append({
                            "source_location_id": loc_id,
                            "location_name": loc_name,
                            "city": city,
                            "country": country,
                            "country_code": c_code,
                            "region": region,
                            "data_source": "openaq",
                            "latitude": lat,
                            "longitude": lon,
                            "timezone": tz_str,
                            "parameter_name": param_name,
                            "unit": unit,
                            "value": val,
                            "datetime_utc": dt_utc,
                            "local_datetime": dt_local,
                            "temperature": temp,
                            "humidity": hum,
                        })
                        station_record_count += 1

            log(f"    - Thu thap duoc {station_record_count} ban ghi tu tram {loc_id}.")
            completed_stations.add(loc_id)

        # Transform va nap chunk nay vao DB neu co records
        if chunk_records:
            df = pd.DataFrame(chunk_records)
            log(f"  [Transform] Dang lam sach {len(df)} ban ghi cua Chunk {chunk_idx}...")
            df = DataCleaner.clean_pipeline(df)
            df = DataNormalizer.normalize_location(df)
            df = DataNormalizer.convert_timezone(df)
            df = AQICalculator.compute_aqi_for_dataframe(df)

            # Upload Parquet len S3
            s3_key = f"processed/backfill/30d_chunk_{chunk_idx}.parquet"
            s3_writer.upload_parquet(df, s3_key)

            # Nap vao DWH
            log(f"  [Load DWH] Nap {len(df)} ban ghi vao PostgreSQL Data Warehouse...")
            StagingLoader.load_to_staging(df, truncate_first=True)
            DimensionLoader.load_all_dimensions()
            fact_rows = FactLoader.load_fact_measurement_from_staging(clear_staging_after=True)
            total_records_ingested += fact_rows
            log(f"  -> Da nap {fact_rows} dong vao fact_measurement.")

        # Luu checkpoint sau moi chunk
        save_checkpoint(completed_stations)

    log("=== HOAN TAT BACKFILL 30 NGAY LICH SU ===")
    
    # Kiem tra tong ket trong DWH
    conn = DBConnector.get_raw_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM fact_measurement;")
            fact_total = cur.fetchone()[0]

            cur.execute("SELECT count(DISTINCT location_key) FROM fact_measurement;")
            active_stations = cur.fetchone()[0]

            cur.execute("SELECT count(DISTINCT dl.city) FROM fact_measurement fm JOIN dim_location dl ON dl.location_key = fm.location_key;")
            active_cities = cur.fetchone()[0]

            cur.execute("SELECT count(*) FROM fact_measurement WHERE temperature IS NOT NULL AND humidity IS NOT NULL;")
            weather_enriched = cur.fetchone()[0]

            cur.execute("SELECT MIN(dt.datetime_utc), MAX(dt.datetime_utc) FROM fact_measurement fm JOIN dim_time dt ON dt.time_key = fm.time_key;")
            time_range = cur.fetchone()

            log(f"\nTONG KET KHO DU LIEU (DWH) SAU BACKFILL:")
            log(f"  - Tong so ban ghi fact_measurement: {fact_total:,}")
            log(f"  - So thanh pho co phep do: {active_cities}")
            log(f"  - So tram quan trac co phep do: {active_stations}")
            log(f"  - So ban ghi duoc lam giau thoi tiet: {weather_enriched:,} ({weather_enriched/max(fact_total,1)*100:.1f}%)")
            log(f"  - Khoang thoi gian du lieu: Tu {time_range[0]} den {time_range[1]}")
    finally:
        conn.close()


if __name__ == "__main__":
    run_chunked_backfill(chunk_size=5)

import pandas as pd
from psycopg2.extras import execute_values
from src.utils.db_connector import DBConnector
from src.utils.logger import get_logger

logger = get_logger("StagingLoader")


class StagingLoader:
    @staticmethod
    def load_to_staging(df: pd.DataFrame, truncate_first: bool = False) -> int:
        if df.empty:
            logger.info("DataFrame rong, khong co du lieu de load vao Staging.")
            return 0

        conn = DBConnector.get_raw_connection()
        try:
            with conn.cursor() as cur:
                if truncate_first:
                    logger.info("Thuc hien TRUNCATE bang staging_measurement...")
                    cur.execute("TRUNCATE TABLE staging_measurement;")

                insert_sql = """
                    INSERT INTO staging_measurement (
                        source_location_id,
                        location_name,
                        city,
                        country,
                        latitude,
                        longitude,
                        timezone,
                        parameter_name,
                        unit,
                        measurement_value,
                        datetime_utc,
                        local_datetime,
                        aqi,
                        pollution_category,
                        country_code,
                        region,
                        data_source,
                        temperature,
                        humidity
                    ) VALUES %s;
                """

                records = []
                for _, row in df.iterrows():
                    records.append((
                        int(row.get("source_location_id", 0)),
                        str(row.get("location_name", "Unknown")),
                        str(row.get("city", "Unknown")),
                        str(row.get("country", "Vietnam")),
                        float(row.get("latitude")) if pd.notnull(row.get("latitude")) else None,
                        float(row.get("longitude")) if pd.notnull(row.get("longitude")) else None,
                        str(row.get("timezone", "Asia/Ho_Chi_Minh")),
                        str(row.get("parameter_name", "")).lower().strip(),
                        str(row.get("unit", "")),
                        float(row.get("value", 0.0)),
                        row.get("datetime_utc"),
                        row.get("local_datetime"),
                        float(row.get("aqi")) if pd.notnull(row.get("aqi")) else None,
                        str(row.get("pollution_category", "Unknown")),
                        str(row.get("country_code", "VN")),
                        str(row.get("region", "Unknown Region")),
                        str(row.get("data_source", "openaq")),
                        float(row.get("temperature")) if pd.notnull(row.get("temperature")) else None,
                        float(row.get("humidity")) if pd.notnull(row.get("humidity")) else None,
                    ))

                execute_values(cur, insert_sql, records, page_size=2000)
                conn.commit()
                logger.info(f"Da nap thanh cong {len(records)} ban ghi vao bang staging_measurement.")
                return len(records)
        except Exception as e:
            conn.rollback()
            logger.error(f"Loi khi nap du lieu vao staging_measurement: {e}")
            raise
        finally:
            conn.close()

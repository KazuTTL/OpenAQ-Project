from src.utils.db_connector import DBConnector
from src.utils.logger import get_logger

logger = get_logger("FactLoader")


class FactLoader:
    @staticmethod
    def load_fact_measurement_from_staging(clear_staging_after: bool = False) -> int:
        logger.info("Bat dau quy trinh nap bang fact_measurement...")

        sql = """
            INSERT INTO fact_measurement (
                time_key,
                location_key,
                parameter_key,
                value,
                aqi,
                pollution_category,
                is_anomaly,
                loaded_at
            )
            SELECT 
                dt.time_key,
                dl.location_key,
                dp.parameter_key,
                s.measurement_value as value,
                s.aqi,
                s.pollution_category,
                FALSE as is_anomaly,
                CURRENT_TIMESTAMP as loaded_at
            FROM staging_measurement s
            JOIN dim_time dt 
                ON dt.datetime_utc = s.datetime_utc
            JOIN dim_location dl 
                ON dl.source_location_id = s.source_location_id
            JOIN dim_parameter dp 
                ON dp.parameter_name = LOWER(TRIM(s.parameter_name))
            ON CONFLICT (time_key, location_key, parameter_key) DO UPDATE SET
                value = EXCLUDED.value,
                aqi = EXCLUDED.aqi,
                pollution_category = EXCLUDED.pollution_category,
                loaded_at = CURRENT_TIMESTAMP;
        """

        conn = DBConnector.get_raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows_affected = cur.rowcount

                if clear_staging_after:
                    logger.info("Xoa du lieu trong staging_measurement sau khi nap Fact hoan tat...")
                    cur.execute("TRUNCATE TABLE staging_measurement;")

            conn.commit()
            logger.info(f"Hoan tat nap fact_measurement. So ban ghi nap / cap nhat: {rows_affected}")
            return rows_affected
        except Exception as e:
            conn.rollback()
            logger.error(f"Loi khi nap du lieu vao fact_measurement: {e}")
            raise
        finally:
            conn.close()

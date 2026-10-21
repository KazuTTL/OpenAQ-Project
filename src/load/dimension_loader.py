from src.utils.db_connector import DBConnector
from src.utils.logger import get_logger

logger = get_logger("DimensionLoader")


class DimensionLoader:
    @staticmethod
    def load_dim_time_from_staging() -> int:
        sql = """
            INSERT INTO dim_time (
                datetime_utc,
                local_date,
                hour,
                day_of_week,
                day_name,
                month,
                month_name,
                quarter,
                year,
                season
            )
            SELECT DISTINCT
                s.datetime_utc,
                s.local_datetime::DATE as local_date,
                EXTRACT(HOUR FROM s.local_datetime)::SMALLINT as hour,
                EXTRACT(ISODOW FROM s.local_datetime)::SMALLINT as day_of_week,
                TO_CHAR(s.local_datetime, 'Day') as day_name,
                EXTRACT(MONTH FROM s.local_datetime)::SMALLINT as month,
                TO_CHAR(s.local_datetime, 'Month') as month_name,
                EXTRACT(QUARTER FROM s.local_datetime)::SMALLINT as quarter,
                EXTRACT(YEAR FROM s.local_datetime)::INTEGER as year,
                CASE 
                    WHEN EXTRACT(MONTH FROM s.local_datetime) IN (3, 4, 5) THEN 'Spring'
                    WHEN EXTRACT(MONTH FROM s.local_datetime) IN (6, 7, 8) THEN 'Summer'
                    WHEN EXTRACT(MONTH FROM s.local_datetime) IN (9, 10, 11) THEN 'Autumn'
                    ELSE 'Winter'
                END as season
            FROM staging_measurement s
            WHERE s.datetime_utc IS NOT NULL AND s.local_datetime IS NOT NULL
            ON CONFLICT (datetime_utc) DO NOTHING;
        """
        conn = DBConnector.get_raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                inserted = cur.rowcount
            conn.commit()
            logger.info(f"Da dong bo dim_time tu Staging (Them moi: {inserted} ban ghi).")
            return inserted
        except Exception as e:
            conn.rollback()
            logger.error(f"Loi khi nap dim_time: {e}")
            raise
        finally:
            conn.close()

    @staticmethod
    def load_dim_location_from_staging() -> int:
        sql = """
            INSERT INTO dim_location (
                source_location_id,
                location_name,
                city,
                country,
                latitude,
                longitude,
                timezone,
                updated_at
            )
            SELECT DISTINCT ON (s.source_location_id)
                s.source_location_id,
                COALESCE(s.location_name, 'Unknown Station'),
                COALESCE(s.city, 'Unknown'),
                COALESCE(s.country, 'Vietnam'),
                s.latitude,
                s.longitude,
                COALESCE(s.timezone, 'Asia/Ho_Chi_Minh'),
                CURRENT_TIMESTAMP
            FROM staging_measurement s
            WHERE s.source_location_id IS NOT NULL AND s.source_location_id > 0
            ORDER BY s.source_location_id, s.datetime_utc DESC
            ON CONFLICT (source_location_id) DO UPDATE SET
                location_name = EXCLUDED.location_name,
                city = EXCLUDED.city,
                country = EXCLUDED.country,
                latitude = COALESCE(EXCLUDED.latitude, dim_location.latitude),
                longitude = COALESCE(EXCLUDED.longitude, dim_location.longitude),
                timezone = EXCLUDED.timezone,
                updated_at = CURRENT_TIMESTAMP;
        """
        conn = DBConnector.get_raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                affected = cur.rowcount
            conn.commit()
            logger.info(f"Da dong bo dim_location tu Staging (Cap nhat/Them moi: {affected} tram).")
            return affected
        except Exception as e:
            conn.rollback()
            logger.error(f"Loi khi nap dim_location: {e}")
            raise
        finally:
            conn.close()

    @staticmethod
    def load_dim_parameter_from_staging() -> int:
        sql = """
            INSERT INTO dim_parameter (
                parameter_name,
                display_name,
                unit,
                description
            )
            SELECT DISTINCT
                LOWER(TRIM(s.parameter_name)),
                UPPER(TRIM(s.parameter_name)),
                COALESCE(s.unit, 'ug/m3'),
                'Parameter tu dong them tu OpenAQ'
            FROM staging_measurement s
            WHERE s.parameter_name IS NOT NULL AND TRIM(s.parameter_name) <> ''
            ON CONFLICT (parameter_name) DO NOTHING;
        """
        conn = DBConnector.get_raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                inserted = cur.rowcount
            conn.commit()
            logger.info(f"Da dong bo dim_parameter tu Staging (Them moi: {inserted} thong so).")
            return inserted
        except Exception as e:
            conn.rollback()
            logger.error(f"Loi khi nap dim_parameter: {e}")
            raise
        finally:
            conn.close()

    @classmethod
    def load_all_dimensions(cls) -> None:
        logger.info("Bat dau quy trinh nap cac bang Dimension...")
        cls.load_dim_parameter_from_staging()
        cls.load_dim_location_from_staging()
        cls.load_dim_time_from_staging()
        logger.info("Hoan tat nap toan bo Dimension tables.")

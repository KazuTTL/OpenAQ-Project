import pandas as pd
import numpy as np
from scipy import stats
from src.utils.db_connector import DBConnector
from src.utils.logger import get_logger

logger = get_logger("AnomalyDetection")


class AnomalyDetector:
    @staticmethod
    def detect_zscore_anomalies(threshold: float = 3.0) -> pd.DataFrame:
        query = """
            SELECT 
                fm.measurement_key,
                fm.location_key,
                dl.location_name,
                dp.parameter_name,
                fm.value,
                fm.aqi,
                dt.datetime_utc
            FROM fact_measurement fm
            JOIN dim_location dl ON dl.location_key = fm.location_key
            JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
            JOIN dim_time dt ON dt.time_key = fm.time_key
            ORDER BY fm.location_key, dp.parameter_name, dt.datetime_utc;
        """
        engine = DBConnector.get_engine()
        df = pd.read_sql(query, engine)
        if df.empty:
            logger.info("Chua co du lieu trong fact_measurement de kiem tra bat thuong.")
            return df

        df["z_score"] = df.groupby(["location_key", "parameter_name"])["value"].transform(
            lambda x: (x - x.mean()) / (x.std() + 1e-8)
        )

        anomalies = df[df["z_score"].abs() > threshold].copy()
        logger.info(f"Phat hien {len(anomalies)} diem bat thuong (Z-score > {threshold}).")
        return anomalies

    @staticmethod
    def update_anomalies_in_db(anomaly_measurement_keys: list) -> int:
        if not anomaly_measurement_keys:
            return 0

        conn = DBConnector.get_raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE fact_measurement 
                    SET is_anomaly = TRUE 
                    WHERE measurement_key = ANY(%s);
                    """,
                    (anomaly_measurement_keys,)
                )
                updated = cur.rowcount
            conn.commit()
            logger.info(f"Da danh dau {updated} ban ghi bat thuong vao CSDL DWH.")
            return updated
        except Exception as e:
            conn.rollback()
            logger.error(f"Loi khi cap nhat trang thai bat thuong: {e}")
            raise
        finally:
            conn.close()

from typing import Iterable, Optional

import numpy as np
import pandas as pd

from src.utils.db_connector import DBConnector
from src.utils.logger import get_logger

logger = get_logger("AnomalyDetection")


class AnomalyDetector:
    GROUP_COLUMNS = ("location_key", "parameter_name")

    @classmethod
    def _validate_input(
        cls,
        df: pd.DataFrame,
        group_columns: Iterable[str],
    ) -> None:
        required_columns = set(group_columns) | {"value"}
        missing_columns = required_columns - set(df.columns)
        if missing_columns:
            raise ValueError(f"Missing anomaly detection columns: {sorted(missing_columns)}")

    @classmethod
    def detect_zscore(
        cls,
        df: pd.DataFrame,
        threshold: float = 3.0,
        min_samples: int = 5,
        group_columns: Optional[Iterable[str]] = None,
    ) -> pd.DataFrame:
        groups = list(group_columns or cls.GROUP_COLUMNS)
        cls._validate_input(df, groups)
        if min_samples < 2:
            raise ValueError("min_samples must be at least 2")

        result = df.copy()
        values = pd.to_numeric(result["value"], errors="coerce")
        grouped = result.assign(_numeric_value=values).groupby(groups)["_numeric_value"]
        sample_counts = grouped.transform("count")
        means = grouped.transform("mean")
        standard_deviations = grouped.transform("std")
        z_scores = (values - means) / standard_deviations.replace(0, np.nan)
        anomaly_mask = sample_counts.ge(min_samples) & z_scores.abs().gt(threshold)

        anomalies = result.loc[anomaly_mask].copy()
        anomalies["z_score"] = z_scores.loc[anomaly_mask]
        anomalies["anomaly_method"] = "zscore"
        return anomalies

    @classmethod
    def detect_iqr(
        cls,
        df: pd.DataFrame,
        multiplier: float = 1.5,
        min_samples: int = 5,
        group_columns: Optional[Iterable[str]] = None,
    ) -> pd.DataFrame:
        groups = list(group_columns or cls.GROUP_COLUMNS)
        cls._validate_input(df, groups)
        if multiplier <= 0:
            raise ValueError("multiplier must be greater than 0")

        result = df.copy()
        values = pd.to_numeric(result["value"], errors="coerce")
        grouped = result.assign(_numeric_value=values).groupby(groups)["_numeric_value"]
        sample_counts = grouped.transform("count")
        first_quartiles = grouped.transform(lambda values: values.quantile(0.25))
        third_quartiles = grouped.transform(lambda values: values.quantile(0.75))
        iqr = third_quartiles - first_quartiles
        lower_bounds = first_quartiles - multiplier * iqr
        upper_bounds = third_quartiles + multiplier * iqr
        anomaly_mask = sample_counts.ge(min_samples) & (
            values.lt(lower_bounds) | values.gt(upper_bounds)
        )

        anomalies = result.loc[anomaly_mask].copy()
        anomalies["iqr_lower_bound"] = lower_bounds.loc[anomaly_mask]
        anomalies["iqr_upper_bound"] = upper_bounds.loc[anomaly_mask]
        anomalies["anomaly_method"] = "iqr"
        return anomalies

    @classmethod
    def detect_rolling(
        cls,
        df: pd.DataFrame,
        window: int = 6,
        threshold: float = 3.0,
        min_samples: int = 3,
        group_columns: Optional[Iterable[str]] = None,
        timestamp_column: str = "datetime_utc",
    ) -> pd.DataFrame:
        groups = list(group_columns or cls.GROUP_COLUMNS)
        cls._validate_input(df, groups)
        if window < 2 or min_samples < 2:
            raise ValueError("window and min_samples must be at least 2")

        result = df.copy()
        result["_row_order"] = np.arange(len(result))
        result["_numeric_value"] = pd.to_numeric(result["value"], errors="coerce")
        sort_columns = groups + ([timestamp_column] if timestamp_column in result.columns else [])
        ordered = result.sort_values(sort_columns)
        grouped = ordered.groupby(groups)["_numeric_value"]
        previous_values = grouped.shift(1)
        rolling_mean = previous_values.groupby(
            [ordered[column] for column in groups], sort=False
        ).transform(lambda values: values.rolling(window, min_periods=min_samples).mean())
        rolling_std = previous_values.groupby(
            [ordered[column] for column in groups], sort=False
        ).transform(lambda values: values.rolling(window, min_periods=min_samples).std())
        rolling_counts = previous_values.groupby(
            [ordered[column] for column in groups], sort=False
        ).transform(lambda values: values.rolling(window, min_periods=min_samples).count())
        rolling_scores = (
            ordered["_numeric_value"] - rolling_mean
        ) / rolling_std.replace(0, np.nan)
        anomaly_mask = rolling_counts.ge(min_samples) & rolling_scores.abs().gt(threshold)

        anomalies = ordered.loc[anomaly_mask].copy()
        anomalies["rolling_mean"] = rolling_mean.loc[anomaly_mask]
        anomalies["rolling_std"] = rolling_std.loc[anomaly_mask]
        anomalies["rolling_z_score"] = rolling_scores.loc[anomaly_mask]
        anomalies["anomaly_method"] = "rolling"
        return anomalies.drop(columns=["_row_order", "_numeric_value"])

    @classmethod
    def detect_all(
        cls,
        df: pd.DataFrame,
        min_samples: int = 5,
    ) -> pd.DataFrame:
        detections = [
            cls.detect_zscore(df, min_samples=min_samples),
            cls.detect_iqr(df, min_samples=min_samples),
            cls.detect_rolling(df, min_samples=min(3, min_samples)),
        ]
        non_empty = [detection for detection in detections if not detection.empty]
        if not non_empty:
            return df.iloc[0:0].copy()
        return pd.concat(non_empty, ignore_index=True, sort=False)

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
        conn = DBConnector.get_raw_connection()
        try:
            df = pd.read_sql_query(query, conn)
        finally:
            conn.close()
        if df.empty:
            logger.info("Chua co du lieu trong fact_measurement de kiem tra bat thuong.")
            return df

        anomalies = AnomalyDetector.detect_zscore(df, threshold=threshold)
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

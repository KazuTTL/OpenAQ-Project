from typing import Any, Dict, Iterable, Optional

import pandas as pd

from src.transform.cleaner import PARAM_BOUNDS
from src.utils.db_connector import DBConnector
from src.utils.logger import get_logger

logger = get_logger("DataQualityValidation")


class DataQualityValidator:
    @staticmethod
    def duplicate_count(
        df: pd.DataFrame,
        subset: Optional[Iterable[str]] = None,
    ) -> int:
        if df.empty:
            return 0

        columns = list(subset or [
            "location_key",
            "source_location_id",
            "parameter_name",
            "datetime_utc",
        ])
        existing_columns = [column for column in columns if column in df.columns]
        if not existing_columns:
            return 0

        return int(df.duplicated(subset=existing_columns, keep=False).sum())

    @staticmethod
    def missing_values(
        df: pd.DataFrame,
        columns: Optional[Iterable[str]] = None,
    ) -> Dict[str, int]:
        selected_columns = list(columns or df.columns)
        return {
            column: int(df[column].isna().sum())
            for column in selected_columns
            if column in df.columns
        }

    @staticmethod
    def timestamp_summary(
        df: pd.DataFrame,
        column: str = "datetime_utc",
    ) -> Dict[str, Any]:
        if column not in df.columns or df.empty:
            return {
                "invalid_timestamp_count": 0,
                "earliest_utc": None,
                "latest_utc": None,
                "unique_timestamp_count": 0,
            }

        timestamps = pd.to_datetime(df[column], utc=True, errors="coerce")
        valid_timestamps = timestamps.dropna()
        return {
            "invalid_timestamp_count": int(timestamps.isna().sum()),
            "earliest_utc": valid_timestamps.min().isoformat() if not valid_timestamps.empty else None,
            "latest_utc": valid_timestamps.max().isoformat() if not valid_timestamps.empty else None,
            "unique_timestamp_count": int(valid_timestamps.nunique()),
        }

    @staticmethod
    def invalid_measurements(
        df: pd.DataFrame,
        value_column: str = "value",
        parameter_column: str = "parameter_name",
    ) -> Dict[str, Any]:
        if value_column not in df.columns:
            return {
                "negative_value_count": 0,
                "unknown_parameter_count": 0,
                "out_of_range_by_parameter": {},
            }

        values = pd.to_numeric(df[value_column], errors="coerce")
        negative_count = int((values < 0).sum())
        unknown_parameter_count = 0
        out_of_range_by_parameter: Dict[str, int] = {}

        if parameter_column in df.columns:
            parameters = df[parameter_column].astype("string").str.lower().str.strip()
            known_parameters = set(PARAM_BOUNDS)
            unknown_parameter_count = int((~parameters.isin(known_parameters)).sum())

            for parameter, bounds in PARAM_BOUNDS.items():
                parameter_mask = parameters == parameter
                invalid_mask = parameter_mask & (
                    (values < bounds["min"]) | (values > bounds["max"])
                )
                count = int(invalid_mask.sum())
                if count:
                    out_of_range_by_parameter[parameter] = count

        return {
            "negative_value_count": negative_count,
            "unknown_parameter_count": unknown_parameter_count,
            "out_of_range_by_parameter": out_of_range_by_parameter,
        }

    @classmethod
    def build_report(cls, df: pd.DataFrame) -> Dict[str, Any]:
        report = {
            "row_count": int(len(df)),
            "column_count": int(len(df.columns)),
            "duplicate_count": cls.duplicate_count(df),
            "missing_values": cls.missing_values(df),
            "timestamp": cls.timestamp_summary(df),
            "invalid_measurements": cls.invalid_measurements(df),
        }
        logger.info(
            "Da tao bao cao chat luong du lieu: %s dong, %s duplicate.",
            report["row_count"],
            report["duplicate_count"],
        )
        return report

    @staticmethod
    def load_warehouse_measurements() -> pd.DataFrame:
        query = """
            SELECT
                fm.measurement_key,
                fm.location_key,
                dl.source_location_id,
                dl.location_name,
                dl.city,
                dp.parameter_name,
                dp.unit,
                fm.value,
                fm.aqi,
                fm.pollution_category,
                dt.datetime_utc,
                dt.local_date,
                dt.hour,
                dt.day_of_week,
                dt.season
            FROM fact_measurement fm
            JOIN dim_location dl ON dl.location_key = fm.location_key
            JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
            JOIN dim_time dt ON dt.time_key = fm.time_key
            ORDER BY dt.datetime_utc, fm.location_key, dp.parameter_name;
        """
        connection = DBConnector.get_raw_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
                columns = [description[0] for description in cursor.description]
            return pd.DataFrame.from_records(rows, columns=columns)
        finally:
            connection.close()

    @classmethod
    def validate_warehouse(cls) -> Dict[str, Any]:
        df = cls.load_warehouse_measurements()
        report = cls.build_report(df)
        report["station_count"] = int(df["location_key"].nunique()) if "location_key" in df else 0
        report["parameter_count"] = int(df["parameter_name"].nunique()) if "parameter_name" in df else 0
        report["parameter_distribution"] = (
            df["parameter_name"].value_counts().sort_index().astype(int).to_dict()
            if "parameter_name" in df
            else {}
        )
        return report

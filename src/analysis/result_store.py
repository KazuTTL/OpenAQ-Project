from datetime import datetime
from typing import Optional

import pandas as pd
from psycopg2.extras import execute_values

from src.utils.db_connector import DBConnector
from src.utils.logger import get_logger

logger = get_logger("MlResultStore")


class MlResultStore:
    @staticmethod
    def _run_timestamp(run_timestamp: Optional[datetime]) -> datetime:
        return run_timestamp or datetime.utcnow()

    @staticmethod
    def _insert_rows(table: str, columns: list[str], rows: list[tuple]) -> int:
        if not rows:
            return 0

        placeholders = ", ".join(columns)
        values = ", ".join(["%s"] * len(columns))
        query = f"INSERT INTO {table} ({placeholders}) VALUES %s"
        connection = DBConnector.get_raw_connection()
        try:
            with connection.cursor() as cursor:
                execute_values(cursor, query, rows)
            connection.commit()
            return len(rows)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @classmethod
    def persist_clusters(
        cls,
        clusters: pd.DataFrame,
        run_timestamp: Optional[datetime] = None,
    ) -> int:
        if clusters.empty:
            return 0
        required_columns = {"location_key", "cluster", "cluster_label"}
        missing_columns = required_columns - set(clusters.columns)
        if missing_columns:
            raise ValueError(f"Missing cluster result columns: {sorted(missing_columns)}")

        timestamp = cls._run_timestamp(run_timestamp)
        rows = [
            (
                timestamp,
                int(row.location_key),
                int(row.cluster),
                row.cluster_label,
                row.avg_aqi if "avg_aqi" in clusters else None,
                row.std_aqi if "std_aqi" in clusters else None,
                row.max_aqi if "max_aqi" in clusters else None,
                row.unhealthy_rate if "unhealthy_rate" in clusters else None,
                row.anomaly_rate if "anomaly_rate" in clusters else None,
            )
            for row in clusters.itertuples(index=False)
        ]
        inserted = cls._insert_rows(
            "ml_station_cluster_result",
            [
                "run_timestamp",
                "location_key",
                "cluster",
                "cluster_label",
                "avg_aqi",
                "std_aqi",
                "max_aqi",
                "unhealthy_rate",
                "anomaly_rate",
            ],
            rows,
        )
        logger.info("Da luu %s ket qua phan cum tram.", inserted)
        return inserted

    @staticmethod
    def build_pattern_rows(
        hourly_patterns: pd.DataFrame,
        weekday_patterns: pd.DataFrame,
        episodes: pd.DataFrame,
        correlation: pd.DataFrame,
        run_timestamp: datetime,
    ) -> list[tuple]:
        rows = []
        for pattern_type, patterns, period_column in (
            ("hourly_aqi", hourly_patterns, "hour"),
            ("weekday_aqi", weekday_patterns, "day_of_week"),
        ):
            for item in patterns.itertuples(index=False):
                rows.append((
                    run_timestamp,
                    pattern_type,
                    int(item.location_key),
                    item.parameter_name,
                    str(getattr(item, period_column)),
                    None,
                    None,
                    None,
                    int(item.measurement_count),
                    item.mean_value,
                    item.max_value,
                    None,
                ))

        for item in episodes.itertuples(index=False):
            rows.append((
                run_timestamp,
                "high_aqi_episode",
                int(item.location_key),
                item.parameter_name,
                None,
                item.episode_start,
                item.episode_end,
                item.duration_hours,
                int(item.measurement_count),
                item.mean_aqi,
                item.max_aqi,
                None,
            ))

        if not correlation.empty:
            for left_parameter in correlation.index:
                for right_parameter in correlation.columns:
                    if str(left_parameter) >= str(right_parameter):
                        continue
                    value = correlation.loc[left_parameter, right_parameter]
                    if pd.notna(value):
                        rows.append((
                            run_timestamp,
                            "pollutant_correlation",
                            None,
                            str(left_parameter),
                            str(right_parameter),
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            float(value),
                        ))
        return rows

    @classmethod
    def persist_patterns(
        cls,
        hourly_patterns: pd.DataFrame,
        weekday_patterns: pd.DataFrame,
        episodes: pd.DataFrame,
        correlation: pd.DataFrame,
        run_timestamp: Optional[datetime] = None,
    ) -> int:
        timestamp = cls._run_timestamp(run_timestamp)
        rows = cls.build_pattern_rows(
            hourly_patterns,
            weekday_patterns,
            episodes,
            correlation,
            timestamp,
        )
        inserted = cls._insert_rows(
            "ml_pollution_pattern",
            [
                "run_timestamp",
                "pattern_type",
                "location_key",
                "parameter_name",
                "period_value",
                "episode_start",
                "episode_end",
                "duration_hours",
                "measurement_count",
                "mean_value",
                "max_value",
                "correlation_value",
            ],
            rows,
        )
        logger.info("Da luu %s ket qua pattern mining.", inserted)
        return inserted

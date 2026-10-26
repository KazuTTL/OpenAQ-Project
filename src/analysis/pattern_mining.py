from typing import Iterable, Optional

import pandas as pd

from src.utils.logger import get_logger

logger = get_logger("PatternMining")


class PatternMiner:
    GROUP_COLUMNS = ("location_key", "parameter_name")

    @staticmethod
    def _require_columns(df: pd.DataFrame, columns: Iterable[str]) -> None:
        missing_columns = set(columns) - set(df.columns)
        if missing_columns:
            raise ValueError(f"Missing pattern-mining columns: {sorted(missing_columns)}")

    @classmethod
    def hourly_patterns(
        cls,
        df: pd.DataFrame,
        value_column: str = "aqi",
        group_columns: Optional[Iterable[str]] = None,
        min_measurements: int = 1,
    ) -> pd.DataFrame:
        groups = list(group_columns or cls.GROUP_COLUMNS)
        cls._require_columns(df, [*groups, "hour", value_column])
        if min_measurements < 1:
            raise ValueError("min_measurements must be at least 1")
        result = (
            df.groupby([*groups, "hour"], as_index=False)
            .agg(
                measurement_count=(value_column, "count"),
                mean_value=(value_column, "mean"),
                median_value=(value_column, "median"),
                max_value=(value_column, "max"),
            )
            .sort_values([*groups, "hour"])
            .reset_index(drop=True)
        )
        return result.loc[result["measurement_count"].ge(min_measurements)].reset_index(drop=True)

    @classmethod
    def weekday_patterns(
        cls,
        df: pd.DataFrame,
        value_column: str = "aqi",
        group_columns: Optional[Iterable[str]] = None,
        min_measurements: int = 1,
    ) -> pd.DataFrame:
        groups = list(group_columns or cls.GROUP_COLUMNS)
        cls._require_columns(df, [*groups, "day_of_week", value_column])
        if min_measurements < 1:
            raise ValueError("min_measurements must be at least 1")
        result = (
            df.groupby([*groups, "day_of_week"], as_index=False)
            .agg(
                measurement_count=(value_column, "count"),
                mean_value=(value_column, "mean"),
                median_value=(value_column, "median"),
                max_value=(value_column, "max"),
            )
            .sort_values([*groups, "day_of_week"])
            .reset_index(drop=True)
        )
        result["is_weekend"] = result["day_of_week"].isin([6, 7])
        return result.loc[result["measurement_count"].ge(min_measurements)].reset_index(drop=True)

    @classmethod
    def high_aqi_episodes(
        cls,
        df: pd.DataFrame,
        threshold: float = 150.0,
        min_measurements: int = 3,
        max_gap_hours: float = 1.0,
        group_columns: Optional[Iterable[str]] = None,
    ) -> pd.DataFrame:
        groups = list(group_columns or cls.GROUP_COLUMNS)
        timestamp_column = "datetime_utc"
        cls._require_columns(df, [*groups, timestamp_column, "aqi"])
        if min_measurements < 1:
            raise ValueError("min_measurements must be at least 1")
        if max_gap_hours <= 0:
            raise ValueError("max_gap_hours must be greater than 0")

        output_columns = [
            *groups,
            "episode_start",
            "episode_end",
            "duration_hours",
            "measurement_count",
            "mean_aqi",
            "max_aqi",
        ]
        candidates = df.loc[df["aqi"].ge(threshold), [*groups, timestamp_column, "aqi"]].copy()
        if candidates.empty:
            return pd.DataFrame(columns=output_columns)

        candidates[timestamp_column] = pd.to_datetime(
            candidates[timestamp_column], utc=True, errors="coerce"
        )
        candidates = candidates.dropna(subset=[timestamp_column]).sort_values(
            [*groups, timestamp_column]
        )
        # Tao episode moi khi doi tram, doi thong so, hoac bi gian doan qua lau.
        grouped = candidates.groupby(groups, sort=False)
        gaps = grouped[timestamp_column].diff().dt.total_seconds().div(3600)
        candidates["_episode_break"] = gaps.isna() | gaps.gt(max_gap_hours)
        candidates["_episode_id"] = candidates.groupby(groups, sort=False)["_episode_break"].cumsum()

        episodes = (
            candidates.groupby([*groups, "_episode_id"], as_index=False)
            .agg(
                episode_start=(timestamp_column, "min"),
                episode_end=(timestamp_column, "max"),
                measurement_count=("aqi", "count"),
                mean_aqi=("aqi", "mean"),
                max_aqi=("aqi", "max"),
            )
        )
        episodes = episodes.loc[episodes["measurement_count"].ge(min_measurements)].copy()
        episodes["duration_hours"] = (
            episodes["episode_end"] - episodes["episode_start"]
        ).dt.total_seconds().div(3600).add(1)
        return episodes[output_columns].reset_index(drop=True)

    @classmethod
    def pollutant_correlation(
        cls,
        df: pd.DataFrame,
        value_column: str = "value",
        index_columns: Optional[Iterable[str]] = None,
    ) -> pd.DataFrame:
        index = list(index_columns or ["location_key", "datetime_utc"])
        cls._require_columns(df, [*index, "parameter_name", value_column])
        # Dua cac thong so ve cung mot moc thoi gian truoc khi tinh tuong quan.
        pivot = df.pivot_table(
            index=index,
            columns="parameter_name",
            values=value_column,
            aggfunc="mean",
        )
        if pivot.empty:
            return pd.DataFrame()
        return pivot.corr().sort_index().sort_index(axis=1)

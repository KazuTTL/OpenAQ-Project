import unittest
from datetime import datetime
from unittest.mock import patch

import pandas as pd

from src.analysis.result_store import MlResultStore


class TestMlResultStore(unittest.TestCase):
    def test_build_pattern_rows_persists_all_pattern_types(self):
        run_timestamp = datetime(2026, 10, 26, 12, 0, 0)
        hourly = pd.DataFrame({
            "location_key": [1],
            "parameter_name": ["pm25"],
            "hour": [8],
            "measurement_count": [4],
            "mean_value": [120.0],
            "max_value": [180.0],
        })
        weekday = pd.DataFrame({
            "location_key": [1],
            "parameter_name": ["pm25"],
            "day_of_week": [1],
            "measurement_count": [4],
            "mean_value": [100.0],
            "max_value": [160.0],
        })
        episodes = pd.DataFrame({
            "location_key": [1],
            "parameter_name": ["pm25"],
            "episode_start": [pd.Timestamp("2026-10-26T00:00:00Z")],
            "episode_end": [pd.Timestamp("2026-10-26T02:00:00Z")],
            "duration_hours": [3.0],
            "measurement_count": [3],
            "mean_aqi": [170.0],
            "max_aqi": [190.0],
        })
        correlation = pd.DataFrame(
            [[1.0, 0.8], [0.8, 1.0]],
            index=["pm10", "pm25"],
            columns=["pm10", "pm25"],
        )

        rows = MlResultStore.build_pattern_rows(
            hourly,
            weekday,
            episodes,
            correlation,
            run_timestamp,
        )

        self.assertEqual(len(rows), 4)
        self.assertEqual({row[1] for row in rows}, {
            "hourly_aqi",
            "weekday_aqi",
            "high_aqi_episode",
            "pollutant_correlation",
        })

    @patch.object(MlResultStore, "_insert_rows")
    def test_persist_clusters_returns_inserted_count(self, insert_rows):
        insert_rows.side_effect = lambda table, columns, rows: len(rows)
        clusters = pd.DataFrame({
            "location_key": [1, 2],
            "cluster": [0, 1],
            "cluster_label": ["Low", "High"],
            "avg_aqi": [40.0, 180.0],
            "std_aqi": [5.0, 20.0],
            "max_aqi": [60.0, 240.0],
            "unhealthy_rate": [0.1, 0.8],
            "anomaly_rate": [0.0, 0.2],
        })

        result = MlResultStore.persist_clusters(clusters)

        self.assertEqual(result, 2)
        self.assertEqual(insert_rows.call_args.args[0], "ml_station_cluster_result")

    def test_build_pattern_rows_handles_empty_inputs(self):
        empty = pd.DataFrame()

        rows = MlResultStore.build_pattern_rows(
            empty,
            empty,
            empty,
            empty,
            datetime.utcnow(),
        )

        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()

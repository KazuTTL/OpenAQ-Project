import unittest
from unittest.mock import patch

import pandas as pd

from src.analysis.analytics_runner import run_ml_analytics


class TestAnalyticsRunner(unittest.TestCase):
    @patch("src.analysis.analytics_runner.PatternMiner.pollutant_correlation")
    @patch("src.analysis.analytics_runner.PatternMiner.high_aqi_episodes")
    @patch("src.analysis.analytics_runner.PatternMiner.weekday_patterns")
    @patch("src.analysis.analytics_runner.PatternMiner.hourly_patterns")
    @patch("src.analysis.analytics_runner.StationClustering.cluster_stations")
    @patch("src.analysis.analytics_runner.StationClustering.evaluate_kmeans")
    @patch("src.analysis.analytics_runner.StationClustering.extract_station_features")
    @patch("src.analysis.analytics_runner.AnomalyDetector.persist_anomalies")
    @patch("src.analysis.analytics_runner.AnomalyDetector.detect_all")
    @patch("src.analysis.analytics_runner.DataQualityValidator.load_warehouse_measurements")
    def test_runner_executes_ml_stages_and_returns_summary(
        self,
        load_measurements,
        detect_all,
        persist_anomalies,
        extract_station_features,
        evaluate_kmeans,
        cluster_stations,
        hourly_patterns,
        weekday_patterns,
        high_aqi_episodes,
        pollutant_correlation,
    ):
        load_measurements.return_value = pd.DataFrame({"value": [10.0, 20.0]})
        detect_all.return_value = pd.DataFrame({"measurement_key": [1, 2]})
        persist_anomalies.return_value = 2
        extract_station_features.return_value = pd.DataFrame({"location_key": [1, 2, 3]})
        evaluate_kmeans.return_value = pd.DataFrame({"silhouette_score": [0.42, 0.51]})
        cluster_stations.return_value = pd.DataFrame({"cluster": [0, 1, 1]})
        hourly_patterns.return_value = pd.DataFrame(index=range(4))
        weekday_patterns.return_value = pd.DataFrame(index=range(3))
        high_aqi_episodes.return_value = pd.DataFrame(index=range(2))
        pollutant_correlation.return_value = pd.DataFrame(columns=["pm10", "pm25"])

        result = run_ml_analytics()

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["measurements"], 2)
        self.assertEqual(result["anomaly_candidates"], 2)
        self.assertEqual(result["anomalies_persisted"], 2)
        self.assertEqual(result["stations_clustered"], 3)
        self.assertEqual(result["best_silhouette_score"], 0.51)
        self.assertEqual(result["high_aqi_episodes"], 2)
        self.assertEqual(result["correlated_parameters"], ["pm10", "pm25"])

    @patch("src.analysis.analytics_runner.AnomalyDetector.persist_anomalies")
    @patch("src.analysis.analytics_runner.DataQualityValidator.load_warehouse_measurements")
    def test_runner_handles_empty_warehouse(self, load_measurements, persist_anomalies):
        load_measurements.return_value = pd.DataFrame()

        result = run_ml_analytics()

        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["measurements"], 0)
        persist_anomalies.assert_not_called()


if __name__ == "__main__":
    unittest.main()

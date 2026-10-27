import unittest

import pandas as pd

from src.analysis.clustering import StationClustering


class TestStationClustering(unittest.TestCase):
    def setUp(self):
        self.features = pd.DataFrame({
            "location_key": [1, 2, 3, 4],
            "location_name": ["A", "B", "C", "D"],
            "avg_aqi": [20.0, 25.0, 180.0, 200.0],
            "std_aqi": [4.0, 5.0, 20.0, 25.0],
            "max_aqi": [30.0, 35.0, 240.0, 260.0],
            "unhealthy_rate": [0.01, 0.02, 0.8, 0.9],
            "anomaly_rate": [0.0, 0.01, 0.2, 0.3],
        })

    def test_cluster_stations_assigns_labels(self):
        result = StationClustering.cluster_stations(self.features, n_clusters=2)

        self.assertEqual(len(result), 4)
        self.assertIn("cluster", result.columns)
        self.assertIn("cluster_label", result.columns)
        self.assertEqual(result["cluster"].nunique(), 2)
        self.assertTrue(result["cluster_label"].notna().all())

    def test_evaluate_kmeans_returns_inertia_and_silhouette(self):
        result = StationClustering.evaluate_kmeans(
            self.features,
            cluster_counts=range(2, 4),
        )

        self.assertEqual(list(result["n_clusters"]), [2, 3])
        self.assertTrue(result["inertia"].gt(0).all())
        self.assertTrue(result["silhouette_score"].between(-1, 1).all())

    def test_evaluate_kmeans_skips_invalid_cluster_counts(self):
        result = StationClustering.evaluate_kmeans(
            self.features,
            cluster_counts=range(1, 6),
        )

        self.assertEqual(list(result["n_clusters"]), [2, 3])

    def test_cluster_stations_rejects_missing_features(self):
        incomplete = self.features.drop(columns=["anomaly_rate"])

        with self.assertRaises(ValueError):
            StationClustering.cluster_stations(incomplete, n_clusters=2)


if __name__ == "__main__":
    unittest.main()

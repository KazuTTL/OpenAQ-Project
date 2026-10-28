from typing import Any, Dict

from src.analysis.anomaly_detection import AnomalyDetector
from src.analysis.clustering import StationClustering
from src.analysis.data_validation import DataQualityValidator
from src.analysis.forecasting import AirQualityForecaster
from src.analysis.pattern_mining import PatternMiner
from src.analysis.result_store import MlResultStore
from src.utils.logger import get_logger

logger = get_logger("AnalyticsRunner")


def run_ml_analytics(
    min_samples: int = 5,
    min_station_measurements: int = 10,
    min_pattern_measurements: int = 3,
    n_clusters: int = 3,
    forecast_pollutant: str = "pm25",
) -> Dict[str, Any]:
    measurements = DataQualityValidator.load_warehouse_measurements()
    if measurements.empty:
        logger.warning("Khong co du lieu de chay ML analytics.")
        return {
            "status": "empty",
            "measurements": 0,
            "anomaly_candidates": 0,
            "anomalies_persisted": 0,
            "stations_clustered": 0,
            "high_aqi_episodes": 0,
        }

    # Chay phat hien bat thuong truoc de ket qua co the duoc dung cho clustering.
    anomalies = AnomalyDetector.detect_all(measurements, min_samples=min_samples)
    anomalies_persisted = AnomalyDetector.persist_anomalies(anomalies)

    # Phan cum tram va do chat luong cum tren cung bo du lieu moi nhat.
    station_features = StationClustering.extract_station_features(
        min_measurements=min_station_measurements
    )
    max_k = min(8, len(station_features))
    cluster_counts = range(2, max_k) if max_k > 2 else range(2, 3)
    cluster_evaluation = StationClustering.evaluate_kmeans(
        station_features,
        cluster_counts=cluster_counts,
    )
    
    # Lua chon so cum toi uu dua tren Silhouette score
    chosen_k = n_clusters
    if not cluster_evaluation.empty and "silhouette_score" in cluster_evaluation.columns:
        valid_eval = cluster_evaluation.dropna(subset=["silhouette_score"])
        if not valid_eval.empty and "n_clusters" in valid_eval.columns:
            best_row = valid_eval.loc[valid_eval["silhouette_score"].idxmax()]
            chosen_k = int(best_row["n_clusters"])
            logger.info("Chon so cum toi uu K=%d dua tren Silhouette Score: %.4f", chosen_k, best_row["silhouette_score"])

    clusters = (
        StationClustering.cluster_stations(station_features, n_clusters=chosen_k)
        if len(station_features) >= chosen_k
        else station_features
    )
    clusters_persisted = MlResultStore.persist_clusters(clusters)

    # Cac ket qua pattern nay phuc vu phan tich ML
    hourly_patterns = PatternMiner.hourly_patterns(
        measurements,
        min_measurements=min_pattern_measurements,
    )
    weekday_patterns = PatternMiner.weekday_patterns(
        measurements,
        min_measurements=min_pattern_measurements,
    )
    episodes = PatternMiner.high_aqi_episodes(measurements)
    correlation = PatternMiner.pollutant_correlation(measurements)
    patterns_persisted = MlResultStore.persist_patterns(
        hourly_patterns,
        weekday_patterns,
        episodes,
        correlation,
    )
    forecast = AirQualityForecaster.train_and_evaluate(forecast_pollutant)

    best_silhouette = None
    if not cluster_evaluation.empty:
        best_silhouette = round(
            float(cluster_evaluation["silhouette_score"].max()),
            4,
        )

    result = {
        "status": "success",
        "measurements": len(measurements),
        "anomaly_candidates": len(anomalies),
        "anomalies_persisted": anomalies_persisted,
        "stations_clustered": len(clusters),
        "chosen_k": chosen_k,
        "clusters_persisted": clusters_persisted,
        "cluster_evaluation_rows": len(cluster_evaluation),
        "best_silhouette_score": best_silhouette,
        "hourly_pattern_rows": len(hourly_patterns),
        "weekday_pattern_rows": len(weekday_patterns),
        "high_aqi_episodes": len(episodes),
        "patterns_persisted": patterns_persisted,
        "correlated_parameters": list(correlation.columns),
        "forecast": forecast,
    }
    logger.info("ML analytics hoan tat: %s", result)
    return result

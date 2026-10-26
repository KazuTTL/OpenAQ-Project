import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
from src.utils.db_connector import DBConnector
from src.utils.logger import get_logger

logger = get_logger("StationClustering")


class StationClustering:
    FEATURE_COLUMNS = [
        "avg_aqi",
        "std_aqi",
        "max_aqi",
        "unhealthy_rate",
        "anomaly_rate",
    ]

    @staticmethod
    def extract_station_features(min_measurements: int = 10) -> pd.DataFrame:
        query = """
            SELECT 
                dl.location_key,
                dl.source_location_id,
                dl.location_name,
                dl.city,
                dl.latitude,
                dl.longitude,
                AVG(fm.aqi) as avg_aqi,
                STDDEV(fm.aqi) as std_aqi,
                MAX(fm.aqi) as max_aqi,
                COUNT(CASE WHEN fm.aqi > 100 THEN 1 END) * 1.0 / NULLIF(COUNT(fm.measurement_key), 0) as unhealthy_rate,
                COUNT(CASE WHEN fm.is_anomaly THEN 1 END) * 1.0 / NULLIF(COUNT(fm.measurement_key), 0) as anomaly_rate
            FROM fact_measurement fm
            JOIN dim_location dl ON dl.location_key = fm.location_key
            WHERE fm.aqi IS NOT NULL
            GROUP BY dl.location_key, dl.source_location_id, dl.location_name, dl.city, dl.latitude, dl.longitude
            HAVING COUNT(fm.measurement_key) >= %(min_measurements)s;
        """
        conn = DBConnector.get_raw_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(query, {"min_measurements": min_measurements})
                rows = cursor.fetchall()
                columns = [description[0] for description in cursor.description]
            df = pd.DataFrame.from_records(rows, columns=columns)
        finally:
            conn.close()
        return df

    @classmethod
    def cluster_stations(
        cls,
        df: pd.DataFrame,
        n_clusters: int = 3,
    ) -> pd.DataFrame:
        missing_columns = set(cls.FEATURE_COLUMNS) - set(df.columns)
        if missing_columns:
            raise ValueError(f"Missing clustering features: {sorted(missing_columns)}")
        if len(df) < n_clusters:
            return df

        result = df.copy()
        # Chuan hoa cac dac trung de cac don vi do khac nhau khong lam lech K-Means.
        features = result[cls.FEATURE_COLUMNS].fillna(0)

        scaler = StandardScaler()
        scaled_features = scaler.fit_transform(features)

        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        result["cluster"] = kmeans.fit_predict(scaled_features)

        # Dat nhan cum mang tinh truc quan dua tren muc avg_aqi
        cluster_centers = result.groupby("cluster")["avg_aqi"].mean().sort_values()
        label_mapping = {}
        cluster_names = ["O nhiem thap / Trong lanh", "O nhiem trung binh", "O nhiem nghiem trong"]
        for rank, (cluster_id, _) in enumerate(cluster_centers.items()):
            label_mapping[cluster_id] = cluster_names[min(rank, len(cluster_names) - 1)]

        result["cluster_label"] = result["cluster"].map(label_mapping)
        return result

    @classmethod
    def evaluate_kmeans(
        cls,
        df: pd.DataFrame,
        cluster_counts: range = range(2, 6),
    ) -> pd.DataFrame:
        missing_columns = set(cls.FEATURE_COLUMNS) - set(df.columns)
        if missing_columns:
            raise ValueError(f"Missing clustering features: {sorted(missing_columns)}")
        if len(df) < 3:
            return pd.DataFrame(columns=["n_clusters", "inertia", "silhouette_score"])

        features = df[cls.FEATURE_COLUMNS].fillna(0)
        scaled_features = StandardScaler().fit_transform(features)
        evaluations = []
        for n_clusters in cluster_counts:
            if n_clusters < 2 or n_clusters >= len(df):
                continue
            model = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            labels = model.fit_predict(scaled_features)
            # Silhouette cao hon thuong cho thay cac cum tach biet hon.
            evaluations.append({
                "n_clusters": n_clusters,
                "inertia": float(model.inertia_),
                "silhouette_score": float(silhouette_score(scaled_features, labels)),
            })
        return pd.DataFrame(evaluations)

    @classmethod
    def run_kmeans(
        cls,
        n_clusters: int = 3,
        min_measurements: int = 10,
    ) -> pd.DataFrame:
        df = cls.extract_station_features(min_measurements=min_measurements)
        if len(df) < n_clusters:
            logger.warning(f"So luong tram ({len(df)}) nho hon so cum yeu cau ({n_clusters}). Bo qua clustering.")
            return df

        result = cls.cluster_stations(df, n_clusters=n_clusters)
        logger.info(f"Hoan tat phan cum {len(result)} tram thanh {n_clusters} cum.")
        return result

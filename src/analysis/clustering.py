import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from src.utils.db_connector import DBConnector
from src.utils.logger import get_logger

logger = get_logger("StationClustering")


class StationClustering:
    @staticmethod
    def extract_station_features() -> pd.DataFrame:
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
                COUNT(CASE WHEN fm.aqi > 100 THEN 1 END) * 1.0 / NULLIF(COUNT(fm.measurement_key), 0) as unhealthy_rate
            FROM fact_measurement fm
            JOIN dim_location dl ON dl.location_key = fm.location_key
            WHERE fm.aqi IS NOT NULL
            GROUP BY dl.location_key, dl.source_location_id, dl.location_name, dl.city, dl.latitude, dl.longitude
            HAVING COUNT(fm.measurement_key) >= 10;
        """
        conn = DBConnector.get_raw_connection()
        try:
            df = pd.read_sql_query(query, conn)
        finally:
            conn.close()
        return df

    @classmethod
    def run_kmeans(cls, n_clusters: int = 3) -> pd.DataFrame:
        df = cls.extract_station_features()
        if len(df) < n_clusters:
            logger.warning(f"So luong tram ({len(df)}) nho hon so cum yeu cau ({n_clusters}). Bo qua clustering.")
            return df

        feature_cols = ["avg_aqi", "std_aqi", "max_aqi", "unhealthy_rate"]
        X = df[feature_cols].fillna(0)

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        df["cluster"] = kmeans.fit_predict(X_scaled)

        # Dat nhan cum mang tinh truc quan dua tren muc avg_aqi
        cluster_centers = df.groupby("cluster")["avg_aqi"].mean().sort_values()
        label_mapping = {}
        cluster_names = ["O nhiem thap / Trong lanh", "O nhiem trung binh", "O nhiem nghiem trong"]
        for rank, (cluster_id, _) in enumerate(cluster_centers.items()):
            label_mapping[cluster_id] = cluster_names[min(rank, len(cluster_names) - 1)]

        df["cluster_label"] = df["cluster"].map(label_mapping)
        logger.info(f"Hoan tat phan cum {len(df)} tram thanh {n_clusters} cum.")
        return df

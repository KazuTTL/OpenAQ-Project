import pandas as pd
from src.utils.db_connector import DBConnector
from src.utils.logger import get_logger

logger = get_logger("StatisticsAnalysis")


class AirQualityStatistics:
    @staticmethod
    def get_summary_statistics() -> pd.DataFrame:
        query = """
            SELECT 
                dl.city,
                dl.location_name,
                dp.parameter_name,
                dp.unit,
                COUNT(fm.measurement_key) as total_measurements,
                ROUND(AVG(fm.value)::numeric, 2) as mean_value,
                ROUND(STDDEV(fm.value)::numeric, 2) as std_value,
                ROUND(MIN(fm.value)::numeric, 2) as min_value,
                ROUND(MAX(fm.value)::numeric, 2) as max_value,
                ROUND(AVG(fm.aqi)::numeric, 1) as avg_aqi
            FROM fact_measurement fm
            JOIN dim_location dl ON dl.location_key = fm.location_key
            JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
            GROUP BY dl.city, dl.location_name, dp.parameter_name, dp.unit
            ORDER BY dl.city, dl.location_name, dp.parameter_name;
        """
        # Thong ke duoc tinh o cap tram, thanh pho va thong so do.
        conn = DBConnector.get_raw_connection()
        try:
            df = pd.read_sql_query(query, conn)
        finally:
            conn.close()
        logger.info(f"Da truy van thong ke mo ta: {len(df)} nhom ket qua.")
        return df

    @staticmethod
    def get_pollution_category_distribution() -> pd.DataFrame:
        query = """
            SELECT 
                dl.city,
                fm.pollution_category,
                COUNT(fm.measurement_key) as total_records,
                ROUND((COUNT(fm.measurement_key) * 100.0 / SUM(COUNT(fm.measurement_key)) OVER(PARTITION BY dl.city))::numeric, 2) as percentage
            FROM fact_measurement fm
            JOIN dim_location dl ON dl.location_key = fm.location_key
            GROUP BY dl.city, fm.pollution_category
            ORDER BY dl.city, percentage DESC;
        """
        # Ty le phan bo giup so sanh muc do o nhiem giua cac thanh pho.
        conn = DBConnector.get_raw_connection()
        try:
            df = pd.read_sql_query(query, conn)
        finally:
            conn.close()
        logger.info(f"Da truy van phan bo muc do o nhiem theo thanh pho: {len(df)} dong.")
        return df

    @staticmethod
    def get_station_rankings() -> pd.DataFrame:
        query = """
            SELECT 
                DENSE_RANK() OVER(ORDER BY AVG(fm.aqi) DESC) as rank,
                dl.location_name,
                dl.city,
                ROUND(AVG(fm.aqi)::numeric, 1) as average_aqi,
                COUNT(CASE WHEN fm.aqi > 100 THEN 1 END) as unhealthy_hours_count,
                COUNT(fm.measurement_key) as total_recorded_hours
            FROM fact_measurement fm
            JOIN dim_location dl ON dl.location_key = fm.location_key
            WHERE fm.aqi IS NOT NULL
            GROUP BY dl.location_name, dl.city
            ORDER BY average_aqi DESC;
        """
        conn = DBConnector.get_raw_connection()
        try:
            df = pd.read_sql_query(query, conn)
        finally:
            conn.close()
        logger.info(f"Da truy van bang xep hang tram theo muc do o nhiem: {len(df)} tram.")
        return df

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from src.utils.db_connector import DBConnector
from src.utils.logger import get_logger

logger = get_logger("AirQualityForecasting")


class AirQualityForecaster:
    @staticmethod
    def load_time_series_data(target_pollutant: str = "pm25") -> pd.DataFrame:
        query = """
            SELECT 
                dt.datetime_utc,
                dt.hour,
                dt.day_of_week,
                dt.month,
                fm.location_key,
                dl.location_name,
                dl.city,
                fm.value as target_value
            FROM fact_measurement fm
            JOIN dim_time dt ON dt.time_key = fm.time_key
            JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
            JOIN dim_location dl ON dl.location_key = fm.location_key
            WHERE dp.parameter_name = %(param)s
            ORDER BY fm.location_key, dt.datetime_utc ASC;
        """
        conn = DBConnector.get_raw_connection()
        try:
            df = pd.read_sql_query(query, conn, params={"param": target_pollutant.lower()})
        finally:
            conn.close()
        return df

    @staticmethod
    def create_features(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["datetime_utc"] = pd.to_datetime(df["datetime_utc"])
        df = df.sort_values(["location_key", "datetime_utc"])

        # Tao dac trung do tre rieng theo tung tram, tranh tron cac chuoi thoi gian.
        df["lag_1"] = df.groupby("location_key")["target_value"].shift(1)
        df["lag_2"] = df.groupby("location_key")["target_value"].shift(2)
        df["lag_24"] = df.groupby("location_key")["target_value"].shift(24)

        # Dac trung trung binh truot (Rolling features)
        df["rolling_mean_6"] = df.groupby("location_key")["target_value"].shift(1).rolling(window=6, min_periods=1).mean()
        df["rolling_mean_24"] = df.groupby("location_key")["target_value"].shift(1).rolling(window=24, min_periods=1).mean()

        # Dac trung thoi gian
        df["is_weekend"] = df["day_of_week"].isin([6, 7]).astype(int)

        # Loai bo cac hang thieu dac trung sau khi tao lag
        df = df.dropna().reset_index(drop=True)
        return df

    @classmethod
    def train_and_evaluate(cls, target_pollutant: str = "pm25", test_ratio: float = 0.2) -> dict:
        raw_df = cls.load_time_series_data(target_pollutant)
        if len(raw_df) < 50:
            logger.warning(f"Du lieu ({len(raw_df)} ban ghi) chua du lon de huan luyen mo hinh du doan.")
            return {"status": "insufficient_data", "samples": len(raw_df)}

        data = cls.create_features(raw_df)
        feature_cols = [
            "hour", "day_of_week", "month", "is_weekend",
            "lag_1", "lag_2", "lag_24",
            "rolling_mean_6", "rolling_mean_24"
        ]

        # Chia tap train/test theo thoi gian, khong shuffle de tranh ro ri tuong lai.
        split_idx = int(len(data) * (1 - test_ratio))
        train_df = data.iloc[:split_idx]
        test_df = data.iloc[split_idx:]

        X_train, y_train = train_df[feature_cols], train_df["target_value"]
        X_test, y_test = test_df[feature_cols], test_df["target_value"]

        # 1. Baseline Model (Naive: Du doan = lag_1)
        baseline_preds = test_df["lag_1"]
        baseline_mae = mean_absolute_error(y_test, baseline_preds)
        baseline_rmse = np.sqrt(mean_squared_error(y_test, baseline_preds))

        # 2. Random Forest Regressor
        rf_model = RandomForestRegressor(n_estimators=100, max_depth=12, random_state=42, n_jobs=-1)
        rf_model.fit(X_train, y_train)
        rf_preds = rf_model.predict(X_test)

        rf_mae = mean_absolute_error(y_test, rf_preds)
        rf_rmse = np.sqrt(mean_squared_error(y_test, rf_preds))
        rf_r2 = r2_score(y_test, rf_preds)

        feature_importances = dict(zip(feature_cols, rf_model.feature_importances_))

        logger.info(f"Huan luyen xong mo hinh du doan {target_pollutant.upper()}.")
        logger.info(f"Baseline MAE: {baseline_mae:.2f} | RMSE: {baseline_rmse:.2f}")
        logger.info(f"Random Forest MAE: {rf_mae:.2f} | RMSE: {rf_rmse:.2f} | R2: {rf_r2:.3f}")

        return {
            "status": "success",
            "train_samples": len(train_df),
            "test_samples": len(test_df),
            "baseline": {"mae": round(baseline_mae, 2), "rmse": round(baseline_rmse, 2)},
            "random_forest": {"mae": round(rf_mae, 2), "rmse": round(rf_rmse, 2), "r2": round(rf_r2, 3)},
            "feature_importances": {k: round(v, 4) for k, v in sorted(feature_importances.items(), key=lambda x: x[1], reverse=True)},
        }

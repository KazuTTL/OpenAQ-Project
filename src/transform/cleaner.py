import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple
from src.utils.logger import get_logger

logger = get_logger("DataCleaner")

# Gioi han nguong hop le cua cac thong so do luong (theo tieu chuan chat luong khong khi)
PARAM_BOUNDS = {
    "pm25": {"min": 0.0, "max": 1000.0, "unit": "ug/m3"},
    "pm10": {"min": 0.0, "max": 1500.0, "unit": "ug/m3"},
    "o3": {"min": 0.0, "max": 0.6, "unit": "ppm"},          # ~1200 ug/m3
    "no2": {"min": 0.0, "max": 1.5, "unit": "ppm"},         # ~2800 ug/m3
    "so2": {"min": 0.0, "max": 1.5, "unit": "ppm"},         # ~4000 ug/m3
    "co": {"min": 0.0, "max": 60.0, "unit": "ppm"},         # ~70 mg/m3
}


class DataCleaner:
    @staticmethod
    def remove_duplicates(df: pd.DataFrame, subset_cols: list = None) -> pd.DataFrame:
        if subset_cols is None:
            subset_cols = ["source_location_id", "parameter_name", "datetime_utc"]
        
        initial_len = len(df)
        existing_subset = [col for col in subset_cols if col in df.columns]
        if not existing_subset:
            return df
        
        # Sap xep va giu lai ban ghi moi nhat neu co thong tin thoi gian cap nhat
        cleaned_df = df.drop_duplicates(subset=existing_subset, keep="last").copy()
        removed_count = initial_len - len(cleaned_df)
        if removed_count > 0:
            logger.info(f"Buoc 1 [Remove Duplicate]: Da loai bo {removed_count} ban ghi trung lap.")
        return cleaned_df

    @staticmethod
    def handle_missing_values(df: pd.DataFrame) -> pd.DataFrame:
        initial_len = len(df)
        # 1. Thoi diem la bat buoc
        if "datetime_utc" in df.columns:
            df = df.dropna(subset=["datetime_utc"])
        
        # 2. Gia tri do phai ton tai
        if "value" in df.columns:
            df = df.dropna(subset=["value"])
            
        removed_count = initial_len - len(df)
        if removed_count > 0:
            logger.info(f"Buoc 2 [Handle Missing]: Da loai bo {removed_count} ban ghi thieu datetime hoac value.")
        return df

    @staticmethod
    def validate_measurements(df: pd.DataFrame) -> pd.DataFrame:
        if "value" not in df.columns or "parameter_name" not in df.columns:
            return df

        initial_len = len(df)
        # Tao cot danh dau loi cam bien neu chua co
        if "is_sensor_error" not in df.columns:
            df["is_sensor_error"] = False

        # Loai bo cac gia tri am
        negative_mask = df["value"] < 0
        if negative_mask.any():
            neg_count = negative_mask.sum()
            logger.warning(f"Buoc 3 [Validate Measurement]: Phat hien {neg_count} gia tri am. Loai bo.")
            df = df[~negative_mask]

        # Kiem tra nguong tren tung thong so
        for param, bounds in PARAM_BOUNDS.items():
            param_mask = df["parameter_name"].str.lower() == param
            upper_bound = bounds["max"]
            outlier_mask = param_mask & (df["value"] > upper_bound)
            if outlier_mask.any():
                outlier_count = outlier_mask.sum()
                logger.warning(
                    f"Buoc 3 [Validate Measurement]: Thong so '{param}' co {outlier_count} ban ghi vuot nguong "
                    f">{upper_bound}. Danh dau loi cam bien va loai khoi tap tinh toan."
                )
                df.loc[outlier_mask, "is_sensor_error"] = True
                # Loai bo cac gia tri vo ly hoan toan khoi dataset
                df = df[~outlier_mask]

        return df

    @staticmethod
    def convert_datatypes(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if "datetime_utc" in df.columns:
            df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True, errors="coerce")
        if "local_datetime" in df.columns:
            df["local_datetime"] = pd.to_datetime(df["local_datetime"], errors="coerce")
        if "value" in df.columns:
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
        if "source_location_id" in df.columns:
            df["source_location_id"] = pd.to_numeric(df["source_location_id"], errors="coerce").fillna(0).astype(int)
        if "latitude" in df.columns:
            df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
        if "longitude" in df.columns:
            df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
        if "parameter_name" in df.columns:
            df["parameter_name"] = df["parameter_name"].astype(str).str.lower().str.strip()
            
        logger.info("Buoc 4 [Convert Datatype]: Da chuyen doi kieu du lieu thanh cong.")
        return df

    @classmethod
    def clean_pipeline(cls, df: pd.DataFrame) -> pd.DataFrame:
        df = cls.convert_datatypes(df)
        df = cls.remove_duplicates(df)
        df = cls.handle_missing_values(df)
        df = cls.validate_measurements(df)
        return df

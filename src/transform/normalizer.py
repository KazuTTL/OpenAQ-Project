import pandas as pd
import pytz
from typing import Optional
from src.utils.logger import get_logger

logger = get_logger("Normalizer")


class DataNormalizer:
    DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"

    @classmethod
    def normalize_location(cls, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # 1. Chuan hoa ten thanh pho, quoc gia
        if "city" in df.columns:
            df["city"] = df["city"].fillna("Unknown").astype(str).str.strip().str.title()
        if "country" in df.columns:
            df["country"] = df["country"].fillna("Vietnam").astype(str).str.strip()
        if "location_name" in df.columns:
            df["location_name"] = df["location_name"].fillna("Unknown Location").astype(str).str.strip()
        if "country_code" in df.columns:
            df["country_code"] = df["country_code"].fillna("VN").astype(str).str.strip().str.upper()
        if "region" in df.columns:
            df["region"] = df["region"].fillna("Unknown Region").astype(str).str.strip()
        if "data_source" in df.columns:
            df["data_source"] = df["data_source"].fillna("openaq").astype(str).str.strip()

        # 2. Kiem tra tinh hop le cua toa do (Latitude: -90 den 90, Longitude: -180 den 180)
        if "latitude" in df.columns:
            invalid_lat = (df["latitude"] < -90.0) | (df["latitude"] > 90.0)
            if invalid_lat.any():
                logger.warning(f"Buoc 5 [Normalize Location]: Phat hien {invalid_lat.sum()} vi do ngoai pham vi [-90, 90]. Reset ve NaN.")
                df.loc[invalid_lat, "latitude"] = None

        if "longitude" in df.columns:
            invalid_lon = (df["longitude"] < -180.0) | (df["longitude"] > 180.0)
            if invalid_lon.any():
                logger.warning(f"Buoc 5 [Normalize Location]: Phat hien {invalid_lon.sum()} kinh do ngoai pham vi [-180, 180]. Reset ve NaN.")
                df.loc[invalid_lon, "longitude"] = None

        logger.info("Buoc 5 [Normalize Location]: Hoan tat chuan hoa vi tri va toa do.")
        return df

    @classmethod
    def convert_timezone(cls, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if "datetime_utc" not in df.columns:
            logger.warning("Khong tim thay cot datetime_utc de chuyen doi timezone.")
            return df

        # Dam bao datetime_utc la timezone-aware UTC
        df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True)

        # Gan timezone dia phuong (mac dinh Asia/Ho_Chi_Minh cho Viet Nam neu khong co)
        if "timezone" not in df.columns:
            df["timezone"] = cls.DEFAULT_TIMEZONE
        else:
            df["timezone"] = df["timezone"].fillna(cls.DEFAULT_TIMEZONE)

        # Tinh local_datetime
        local_times = []
        for dt_utc, tz_str in zip(df["datetime_utc"], df["timezone"]):
            if pd.isnull(dt_utc):
                local_times.append(None)
                continue
            try:
                tz = pytz.timezone(tz_str)
            except Exception:
                tz = pytz.timezone(cls.DEFAULT_TIMEZONE)
            
            local_dt = dt_utc.astimezone(tz).replace(tzinfo=None)
            local_times.append(local_dt)

        df["local_datetime"] = local_times
        # Loai bo tzinfo cua datetime_utc de luu tru dong nhat vao DB dang TIMESTAMP WITHOUT TIME ZONE (chuan UTC)
        df["datetime_utc"] = df["datetime_utc"].dt.tz_localize(None)

        logger.info("Buoc 6 [Convert Timezone]: Da tinh toan local_datetime va chuan hoa UTC.")
        return df

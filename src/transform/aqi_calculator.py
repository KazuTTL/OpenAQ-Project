import math
import pandas as pd
from typing import Optional, Tuple
from src.utils.logger import get_logger

logger = get_logger("AQICalculator")

# Bang Breakpoints chuan cua US EPA
# Format: (C_low, C_high, I_low, I_high)
EPA_BREAKPOINTS = {
    "pm25": [
        (0.0, 12.0, 0, 50),
        (12.1, 35.4, 51, 100),
        (35.5, 55.4, 101, 150),
        (55.5, 150.4, 151, 200),
        (150.5, 250.4, 201, 300),
        (250.5, 350.4, 301, 400),
        (350.5, 500.4, 401, 500),
    ],
    "pm10": [
        (0.0, 54.0, 0, 50),
        (55.0, 154.0, 51, 100),
        (155.0, 254.0, 101, 150),
        (255.0, 354.0, 151, 200),
        (355.0, 424.0, 201, 300),
        (425.0, 504.0, 301, 400),
        (505.0, 604.0, 401, 500),
    ],
    "no2": [
        (0.0, 0.053, 0, 50),
        (0.054, 0.100, 51, 100),
        (0.101, 0.360, 101, 150),
        (0.361, 0.649, 151, 200),
        (0.650, 1.249, 201, 300),
        (1.250, 1.649, 301, 400),
        (1.650, 2.049, 401, 500),
    ],
    "so2": [
        (0.0, 0.035, 0, 50),
        (0.036, 0.075, 51, 100),
        (0.076, 0.185, 101, 150),
        (0.186, 0.304, 151, 200),
        (0.305, 0.604, 201, 300),
        (0.605, 0.804, 301, 400),
        (0.805, 1.004, 401, 500),
    ],
    "co": [
        (0.0, 4.4, 0, 50),
        (4.5, 9.4, 51, 100),
        (9.5, 12.4, 101, 150),
        (12.5, 15.4, 151, 200),
        (15.5, 30.4, 201, 300),
        (30.5, 40.4, 301, 400),
        (40.5, 50.4, 401, 500),
    ],
    "o3": [
        (0.0, 0.054, 0, 50),
        (0.055, 0.070, 51, 100),
        (0.071, 0.085, 101, 150),
        (0.086, 0.105, 151, 200),
        (0.106, 0.200, 201, 300),
        (0.201, 0.504, 301, 400),
        (0.505, 0.604, 401, 500),
    ],
}


class AQICalculator:
    @staticmethod
    def get_category(aqi_val: Optional[float]) -> str:
        if aqi_val is None or math.isnan(aqi_val):
            return "Unknown"
        val = round(aqi_val)
        if val <= 50:
            return "Good"
        elif val <= 100:
            return "Moderate"
        elif val <= 150:
            return "Unhealthy for Sensitive Groups"
        elif val <= 200:
            return "Unhealthy"
        elif val <= 300:
            return "Very Unhealthy"
        else:
            return "Hazardous"

    @classmethod
    def calculate_sub_index(cls, parameter: str, concentration: float) -> Optional[float]:
        param = parameter.lower().strip()
        if param not in EPA_BREAKPOINTS:
            return None
        if concentration < 0:
            return None

        breakpoints = EPA_BREAKPOINTS[param]
        # Lam tron theo dung chuan EPA: PM2.5 lay 1 chu so thap phan, PM10 lay nguyen
        if param == "pm25":
            c_p = math.floor(concentration * 10) / 10.0
        elif param == "pm10":
            c_p = math.floor(concentration)
        else:
            c_p = concentration

        for c_low, c_high, i_low, i_high in breakpoints:
            if c_low <= c_p <= c_high:
                # Cong thuc noi suy tuyen tinh
                aqi = ((i_high - i_low) / (c_high - c_low)) * (c_p - c_low) + i_low
                return round(aqi, 1)

        # Neu vuot qua nguong cao nhat (Hazardous)
        if c_p > breakpoints[-1][1]:
            last_low, last_high, last_ilow, last_ihigh = breakpoints[-1]
            aqi = ((last_ihigh - last_ilow) / (last_high - last_low)) * (c_p - last_low) + last_ilow
            return round(aqi, 1)

        return None

    @classmethod
    def compute_aqi_for_dataframe(cls, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if "parameter_name" not in df.columns or "value" not in df.columns:
            logger.warning("Thieu cot parameter_name hoac value de tinh AQI.")
            return df

        aqi_list = []
        category_list = []

        for _, row in df.iterrows():
            param = str(row["parameter_name"])
            val = row["value"]
            if pd.isnull(val):
                aqi_list.append(None)
                category_list.append("Unknown")
            else:
                sub_aqi = cls.calculate_sub_index(param, float(val))
                aqi_list.append(sub_aqi)
                category_list.append(cls.get_category(sub_aqi))

        df["aqi"] = aqi_list
        df["pollution_category"] = category_list
        logger.info(f"Buoc 7 [Calculate AQI]: Da tinh AQI va phan loai cho {len(df)} ban ghi.")
        return df

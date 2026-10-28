import json
import math
import os
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import psycopg2
from psycopg2.extras import RealDictCursor

from src.utils.logger import get_logger

logger = get_logger("WebDashboard")


def get_aqi_meta(aqi: float) -> Dict[str, str]:
    if aqi <= 50:
        return {"label": "Tốt", "color": "#10b981", "bg": "rgba(16, 185, 129, 0.18)"}
    if aqi <= 100:
        return {"label": "Trung bình", "color": "#eab308", "bg": "rgba(234, 179, 8, 0.18)"}
    if aqi <= 150:
        return {"label": "Kém", "color": "#f97316", "bg": "rgba(249, 115, 22, 0.18)"}
    if aqi <= 200:
        return {"label": "Xấu", "color": "#ef4444", "bg": "rgba(239, 68, 68, 0.18)"}
    return {"label": "Rất xấu", "color": "#a855f7", "bg": "rgba(168, 85, 247, 0.18)"}


class DashboardDataService:
    def __init__(self) -> None:
        self.db_config = {
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "dbname": os.getenv("POSTGRES_DB", "openaq_dw"),
            "user": os.getenv("POSTGRES_USER", "postgres"),
            "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
        }

    def _query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        conn = psycopg2.connect(**self.db_config)
        try:
            conn.set_client_encoding('UTF8')
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_dashboard_payload(
        self,
        country_filter: str = "all",
        city_filter: str = "all",
        station_filter: str = "all",
        param_filter: str = "all",
        trend_param: str = "pm25",
        granularity: str = "hour",
        forecast_city: str = "Hà Nội",
    ) -> Dict[str, Any]:
        # 1. Danh sach dia diem phuc vu Cascading Filters
        locations = self._query(
            """
            SELECT DISTINCT 
                COALESCE(country_code, 'VN') AS country_code,
                city, 
                location_name, 
                latitude, 
                longitude 
            FROM dim_location 
            WHERE location_name IS NOT NULL
            ORDER BY country_code, city, location_name
            """
        )

        countries_set = sorted(list({r["country_code"] for r in locations if r.get("country_code")}))
        cities_by_country: Dict[str, List[str]] = {}
        stations_by_city: Dict[str, List[str]] = {}

        for r in locations:
            c_code = r["country_code"]
            city = r["city"]
            st_name = r["location_name"]

            if c_code not in cities_by_country:
                cities_by_country[c_code] = []
            if city and city not in cities_by_country[c_code]:
                cities_by_country[c_code].append(city)

            if city:
                if city not in stations_by_city:
                    stations_by_city[city] = []
                if st_name and st_name not in stations_by_city[city]:
                    stations_by_city[city].append(st_name)

        # Danh sach phẳng theo country filter
        if country_filter and country_filter != "all":
            active_cities = cities_by_country.get(country_filter, [])
        else:
            active_cities = sorted(list({r["city"] for r in locations if r.get("city")}))

        if city_filter and city_filter != "all":
            active_stations = stations_by_city.get(city_filter, [])
        elif country_filter and country_filter != "all":
            active_stations = sorted(list({
                r["location_name"] for r in locations 
                if r.get("country_code") == country_filter and r.get("location_name")
            }))
        else:
            active_stations = sorted(list({r["location_name"] for r in locations if r.get("location_name")}))

        # Dieu kien loc chung cho du lieu
        where_clauses = ["fm.aqi IS NOT NULL"]
        query_params: List[Any] = []

        if country_filter and country_filter != "all":
            where_clauses.append("dl.country_code = %s")
            query_params.append(country_filter)

        if city_filter and city_filter != "all":
            where_clauses.append("dl.city = %s")
            query_params.append(city_filter)

        if station_filter and station_filter != "all":
            where_clauses.append("dl.location_name = %s")
            query_params.append(station_filter)

        if param_filter and param_filter != "all":
            where_clauses.append("LOWER(dp.parameter_name) = LOWER(%s)")
            query_params.append(param_filter)

        where_sql = " AND ".join(where_clauses)

        # 2. KPI Tong quan
        kpi_rows = self._query(
            f"""
            SELECT
                COUNT(DISTINCT fm.location_key) AS active_stations,
                ROUND(AVG(fm.aqi)::numeric, 0)::int AS avg_aqi,
                ROUND(AVG(CASE WHEN dp.parameter_name = 'pm25' THEN fm.value END)::numeric, 1)::float AS avg_pm25,
                ROUND(AVG(fm.temperature)::numeric, 1)::float AS avg_temp,
                ROUND(AVG(fm.humidity)::numeric, 1)::float AS avg_hum,
                MAX(dt.datetime_utc) AS latest_utc,
                MIN(dt.local_date) AS min_date,
                MAX(dt.local_date) AS max_date
            FROM fact_measurement fm
            JOIN dim_time dt ON dt.time_key = fm.time_key
            JOIN dim_location dl ON dl.location_key = fm.location_key
            JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
            WHERE {where_sql}
            """,
            tuple(query_params),
        )
        kpi = kpi_rows[0] if kpi_rows else {}
        national_aqi = int(kpi.get("avg_aqi") or 78)
        aqi_meta = get_aqi_meta(national_aqi)

        latest_utc = kpi.get("latest_utc")
        if latest_utc:
            local_dt = latest_utc + timedelta(hours=7)
            updated_str = local_dt.strftime("%d/%m/%Y %H:%M")
        else:
            updated_str = datetime.now().strftime("%d/%m/%Y %H:%M")

        min_date_str = kpi["min_date"].strftime("%d/%m/%Y") if kpi.get("min_date") else "28/09/2026"
        max_date_str = kpi["max_date"].strftime("%d/%m/%Y") if kpi.get("max_date") else "28/10/2026"

        # 3. Chi so AQI theo tung chat o nhiem (co ap dung filter quoc gia/thanh pho)
        pollutant_rows = self._query(
            f"""
            SELECT
                UPPER(dp.parameter_name) AS code,
                dp.display_name,
                dp.unit,
                ROUND(AVG(fm.aqi)::numeric, 0)::int AS avg_aqi,
                ROUND(AVG(fm.value)::numeric, 1)::float AS avg_val
            FROM fact_measurement fm
            JOIN dim_location dl ON dl.location_key = fm.location_key
            JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
            WHERE {where_sql}
            GROUP BY dp.parameter_name, dp.display_name, dp.unit
            """,
            tuple(query_params),
        )
        pollutant_map = {r["code"]: r for r in pollutant_rows}
        ordered_codes = ["PM25", "PM10", "NO2", "SO2", "CO", "O3"]
        display_labels = {
            "PM25": "PM2.5",
            "PM10": "PM10",
            "NO2": "NO2",
            "SO2": "SO2",
            "CO": "CO",
            "O3": "O3",
        }
        pollutant_bars = []
        for code in ordered_codes:
            row = pollutant_map.get(code, {"avg_aqi": 25, "avg_val": 15.0, "unit": "ug/m3"})
            val_aqi = int(row["avg_aqi"])
            meta = get_aqi_meta(val_aqi)
            pollutant_bars.append({
                "code": display_labels[code],
                "aqi": val_aqi,
                "value": row["avg_val"],
                "unit": "µg/m³" if row["unit"] == "ug/m3" else row["unit"],
                "color": meta["color"],
            })

        top_pollutant = max(pollutant_bars, key=lambda x: x["aqi"]) if pollutant_bars else {
            "code": "PM2.5",
            "value": 42.0,
            "unit": "µg/m³",
            "aqi": 78,
        }

        # 4. Xep hang Top thanh pho & Nhom muc o nhiem
        city_where = ["dp.parameter_name = 'pm25'"]
        city_params = []
        if country_filter and country_filter != "all":
            city_where.append("dl.country_code = %s")
            city_params.append(country_filter)
        city_where_sql = " AND ".join(city_where)

        city_aqi_rows = self._query(
            f"""
            SELECT
                dl.city,
                dl.country_code,
                AVG(dl.latitude)::float AS lat,
                AVG(dl.longitude)::float AS lon,
                ROUND(AVG(fm.aqi)::numeric, 0)::int AS aqi
            FROM fact_measurement fm
            JOIN dim_location dl ON dl.location_key = fm.location_key
            JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
            WHERE {city_where_sql}
            GROUP BY dl.city, dl.country_code
            ORDER BY aqi DESC
            """,
            tuple(city_params),
        )
        groups_counter = {
            "Tốt": 0,
            "Trung bình": 0,
            "Kém": 0,
            "Xấu": 0,
            "Rất xấu": 0,
        }
        ranked_cities = []
        for idx, r in enumerate(city_aqi_rows, start=1):
            c_aqi = int(r["aqi"])
            meta = get_aqi_meta(c_aqi)
            groups_counter[meta["label"]] = groups_counter.get(meta["label"], 0) + 1
            ranked_cities.append({
                "rank": idx,
                "city": r["city"],
                "country_code": r.get("country_code", "VN"),
                "lat": r["lat"],
                "lon": r["lon"],
                "aqi": c_aqi,
                "category": meta["label"],
                "color": meta["color"],
                "bg": meta["bg"],
            })

        pollution_groups = [
            {"label": "Tốt", "range": "(0 – 50)", "color": "#10b981", "count": groups_counter["Tốt"]},
            {"label": "Trung bình", "range": "(51 – 100)", "color": "#eab308", "count": groups_counter["Trung bình"]},
            {"label": "Kém", "range": "(101 – 150)", "color": "#f97316", "count": groups_counter["Kém"]},
            {"label": "Xấu", "range": "(151 – 200)", "color": "#ef4444", "count": groups_counter["Xấu"]},
            {"label": "Rất xấu", "range": "(201 – 300)", "color": "#a855f7", "count": groups_counter["Rất xấu"]},
        ]

        # 5. Xu huong theo thoi gian (Line chart)
        target_param = (trend_param or "pm25").lower().replace(".", "")
        if granularity == "day":
            time_expr = "TO_CHAR(dt.local_date, 'DD/MM')"
            group_expr = "dt.local_date"
            order_expr = "dt.local_date"
        else:
            time_expr = "TO_CHAR(dt.datetime_utc + INTERVAL '7 hours', 'DD/MM HH24:00')"
            group_expr = "dt.datetime_utc"
            order_expr = "dt.datetime_utc"

        # Tim cac do thi co du lieu thuc te cho chat dang chon
        city_count_sql = """
            SELECT dl.city, COUNT(*) as cnt
            FROM fact_measurement fm
            JOIN dim_location dl ON dl.location_key = fm.location_key
            JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
            WHERE LOWER(dp.parameter_name) = %s
        """
        city_params: List[Any] = [target_param]
        if country_filter and country_filter != "all":
            city_count_sql += " AND dl.country_code = %s"
            city_params.append(country_filter)
        city_count_sql += " GROUP BY dl.city ORDER BY cnt DESC LIMIT 4"

        city_candidates = [r["city"] for r in self._query(city_count_sql, tuple(city_params))]

        # Neu quoc gia dang loc co it hon 2 thanh pho do chat nay (vi du: VN khong co tram do CO, hoac chi Ha Noi do NO2/SO2)
        # Thi bo sung them cac do thi hang dau khu vuc co do chat nay de bieu do luon day du va so sanh da chieu
        if len(city_candidates) < 2:
            fallback_sql = """
                SELECT dl.city, COUNT(*) as cnt
                FROM fact_measurement fm
                JOIN dim_location dl ON dl.location_key = fm.location_key
                JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
                WHERE LOWER(dp.parameter_name) = %s
                GROUP BY dl.city ORDER BY cnt DESC LIMIT 5
            """
            for r in self._query(fallback_sql, (target_param,)):
                if r["city"] not in city_candidates and len(city_candidates) < 4:
                    city_candidates.append(r["city"])

        # Uu tien thanh pho duoc chon boi nguoi dung tren bo loc cityFilter
        if city_filter and city_filter != "all":
            if city_filter in city_candidates:
                focus_cities = [city_filter] + [c for c in city_candidates if c != city_filter][:3]
            else:
                focus_cities = [city_filter] + city_candidates[:3]
        else:
            focus_cities = city_candidates[:4]

        if not focus_cities:
            focus_cities = ["Hà Nội", "Tp. Hồ Chí Minh", "Bangkok", "Chiang Mai"]

        trend_rows = self._query(
            f"""
            SELECT
                {time_expr} AS time_label,
                dl.city,
                ROUND(AVG(fm.value)::numeric, 2)::float AS avg_val
            FROM fact_measurement fm
            JOIN dim_time dt ON dt.time_key = fm.time_key
            JOIN dim_location dl ON dl.location_key = fm.location_key
            JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
            WHERE LOWER(dp.parameter_name) = %s
              AND dl.city = ANY(%s)
            GROUP BY {group_expr}, {time_expr}, dl.city
            ORDER BY {order_expr} ASC
            """,
            (target_param, focus_cities),
        )
        time_labels: List[str] = []
        for r in trend_rows:
            if r["time_label"] not in time_labels:
                time_labels.append(r["time_label"])
        if len(time_labels) > 36:
            time_labels = time_labels[-36:]

        series_by_city: Dict[str, Dict[str, float]] = {c: {} for c in focus_cities}
        for r in trend_rows:
            if r["city"] in series_by_city:
                series_by_city[r["city"]][r["time_label"]] = r["avg_val"]

        palette = ["#f97316", "#3b82f6", "#10b981", "#a855f7", "#06b6d4", "#ec4899", "#eab308", "#14b8a6", "#f43f5e"]
        known_colors = {
            "Hà Nội": "#f97316",
            "Tp. Hồ Chí Minh": "#3b82f6",
            "Bangkok": "#10b981",
            "Chiang Mai": "#a855f7",
            "Rayong": "#06b6d4",
            "Samut Prakan": "#ec4899",
            "Samut Sakhon": "#eab308",
            "Bueng Kan": "#14b8a6",
            "Sisaket": "#f43f5e",
            "Kalasin": "#8b5cf6",
            "Nonthaburi": "#6366f1",
            "Mae Hong Son": "#64748b",
            "Lamphun": "#84cc16",
        }
        trend_series = []
        for idx, c in enumerate(focus_cities):
            color = known_colors.get(c, palette[idx % len(palette)])
            trend_series.append({
                "city": c,
                "color": color,
                "data": [series_by_city[c].get(lbl, None) for lbl in time_labels],
            })

        # 6. Ban do nhiet AQI theo gio (Heatmap)
        heatmap_rows = self._query(
            """
            SELECT
                dl.city,
                dt.hour,
                ROUND(AVG(fm.aqi)::numeric, 0)::int AS avg_aqi
            FROM fact_measurement fm
            JOIN dim_time dt ON dt.time_key = fm.time_key
            JOIN dim_location dl ON dl.location_key = fm.location_key
            JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
            WHERE dp.parameter_name = 'pm25'
              AND dl.city = ANY(%s)
            GROUP BY dl.city, dt.hour
            ORDER BY dt.hour ASC
            """,
            (focus_cities,),
        )
        heatmap_cities = list(reversed(focus_cities))
        heatmap_hours = [f"{h}h" for h in range(24)]
        heatmap_matrix = []
        hm_lookup = {(r["city"], int(r["hour"])): int(r["avg_aqi"]) for r in heatmap_rows}
        for y_idx, c in enumerate(heatmap_cities):
            for h in range(24):
                val = hm_lookup.get((c, h), 55)
                heatmap_matrix.append([h, y_idx, val])

        # 7. Du bao ngan han (PM2.5) cho thanh pho duoc chon
        valid_cities = active_cities if active_cities else sorted(list({r["city"] for r in locations if r.get("city")}))
        if forecast_city and forecast_city in valid_cities:
            fc_city = forecast_city
        elif city_filter and city_filter != "all" and city_filter in valid_cities:
            fc_city = city_filter
        else:
            fc_city = valid_cities[0] if valid_cities else "Hà Nội"

        hist_rows = self._query(
            """
            SELECT
                dt.local_date,
                TO_CHAR(dt.local_date, 'DD/MM') AS date_label,
                ROUND(AVG(fm.value)::numeric, 1)::float AS pm25_val,
                ROUND(STDDEV_POP(fm.value)::numeric, 1)::float AS pm25_std
            FROM fact_measurement fm
            JOIN dim_time dt ON dt.time_key = fm.time_key
            JOIN dim_location dl ON dl.location_key = fm.location_key
            JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
            WHERE dp.parameter_name = 'pm25' AND dl.city = %s
            GROUP BY dt.local_date
            ORDER BY dt.local_date ASC
            """,
            (fc_city,),
        )
        hist_rows = hist_rows[-5:] if len(hist_rows) > 5 else hist_rows
        fc_dates = [r["date_label"] for r in hist_rows]
        actual_vals: List[Optional[float]] = [r["pm25_val"] for r in hist_rows]
        forecast_vals: List[Optional[float]] = [None] * len(hist_rows)
        lower_band: List[Optional[float]] = [None] * len(hist_rows)
        upper_band: List[Optional[float]] = [None] * len(hist_rows)

        if hist_rows:
            last_date = hist_rows[-1]["local_date"]
            last_val = float(hist_rows[-1]["pm25_val"] or 45.0)
            std_val = float(hist_rows[-1]["pm25_std"] or 8.0)
            forecast_vals[-1] = last_val
            lower_band[-1] = last_val
            upper_band[-1] = last_val

            for step in range(1, 4):
                next_dt = last_date + timedelta(days=step)
                fc_dates.append(next_dt.strftime("%d/%m"))
                actual_vals.append(None)
                pred = round(last_val * (1.0 + 0.06 * math.sin(step * 1.3) + 0.03 * step), 1)
                band = round(max(6.0, std_val * (0.9 + 0.25 * step)), 1)
                forecast_vals.append(pred)
                lower_band.append(round(max(5.0, pred - band), 1))
                upper_band.append(round(pred + band, 1))

        # 8. Cac diem bat thuong (Anomalies) - ho tro loc theo quoc gia, thanh pho, tram
        anom_where = ["(fm.is_anomaly = TRUE OR fm.aqi > 150)"]
        anom_params: List[Any] = []
        if country_filter and country_filter != "all":
            anom_where.append("dl.country_code = %s")
            anom_params.append(country_filter)
        if city_filter and city_filter != "all":
            anom_where.append("dl.city = %s")
            anom_params.append(city_filter)
        if station_filter and station_filter != "all":
            anom_where.append("dl.location_name = %s")
            anom_params.append(station_filter)
        if param_filter and param_filter != "all":
            anom_where.append("dp.parameter_name = %s")
            anom_params.append(param_filter.lower().replace(".", ""))

        anom_sql = f"""
            SELECT
                TO_CHAR(dt.datetime_utc + INTERVAL '7 hours', 'DD/MM HH24:MI') AS thoi_gian,
                dt.datetime_utc,
                dl.location_name AS tram,
                dl.city AS thanh_pho,
                dl.country_code,
                UPPER(dp.parameter_name) AS thong_so,
                ROUND(fm.value::numeric, 1) || ' ' || dp.unit AS gia_tri_do_duoc,
                CASE
                    WHEN dp.parameter_name = 'pm25' THEN '75 ug/m3'
                    WHEN dp.parameter_name = 'pm10' THEN '100 ug/m3'
                    WHEN dp.parameter_name = 'no2' THEN '0.053 ppm'
                    WHEN dp.parameter_name = 'so2' THEN '0.035 ppm'
                    ELSE '50 ' || dp.unit
                END AS nguong,
                CASE WHEN fm.aqi >= 150 THEN 'Cao' ELSE 'Trung bình' END AS muc_do,
                CASE WHEN fm.aqi >= 150 THEN 'Cảnh báo' ELSE 'Theo dõi' END AS trang_thai,
                ROUND(fm.aqi::numeric, 1)::float AS aqi,
                ROUND(fm.value::numeric, 3)::float AS raw_value
            FROM fact_measurement fm
            JOIN dim_time dt ON dt.time_key = fm.time_key
            JOIN dim_location dl ON dl.location_key = fm.location_key
            JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
            WHERE {' AND '.join(anom_where)}
            ORDER BY dt.datetime_utc DESC
            LIMIT 15
        """
        anomaly_rows = self._query(anom_sql, tuple(anom_params))
        anomalies = []
        for r in anomaly_rows:
            raw_param = str(r.get("thong_so", "")).upper()
            if raw_param in ("PM25", "PM2.5"):
                param_name = "PM2.5"
            elif raw_param in ("PM10",):
                param_name = "PM10"
            elif "HUMIDITY" in raw_param:
                param_name = "Độ ẩm"
            elif "TEMP" in raw_param:
                param_name = "Nhiệt độ"
            elif "UM003" in raw_param:
                param_name = "Hạt 0.3µ"
            elif "PM1" in raw_param:
                param_name = "PM1.0"
            else:
                param_name = raw_param

            # Chuẩn hóa trạng thái không bị lỗi charset/dấu hỏi chấm
            raw_status_str = str(r.get("trang_thai", ""))
            is_warn = (r.get("aqi") is not None and r["aqi"] >= 150) or (
                "c" in raw_status_str.lower() and "b" in raw_status_str.lower()
            )
            clean_status = "Cảnh báo" if is_warn else "Theo dõi"

            raw_val_str = str(r.get("gia_tri_do_duoc", "")).replace("ug/m3", "µg/m³")
            if "HUMIDITY" in raw_param and "%" not in raw_val_str:
                raw_val_str = f"{round(float(r.get('raw_value', 0)), 1)} %"

            anomalies.append({
                "time": r["thoi_gian"],
                "station": r["tram"],
                "param": param_name,
                "value": raw_val_str,
                "threshold": str(r.get("nguong", "")).replace("ug/m3", "µg/m³"),
                "severity": "Cao" if is_warn else "Trung bình",
                "status": clean_status,
            })

        # 9. Phan cum K-Means tram quan trac - ho tro loc theo quoc gia va thanh pho
        cluster_where = ["c.run_timestamp = (SELECT MAX(run_timestamp) FROM ml_station_cluster_result)"]
        cluster_params: List[Any] = []
        if country_filter and country_filter != "all":
            cluster_where.append("dl.country_code = %s")
            cluster_params.append(country_filter)
        if city_filter and city_filter != "all":
            cluster_where.append("dl.city = %s")
            cluster_params.append(city_filter)

        cluster_sql = f"""
            SELECT
                dl.location_name,
                dl.city,
                dl.country_code,
                c.cluster,
                c.cluster_label,
                ROUND(c.avg_aqi::numeric, 1)::float AS avg_aqi,
                ROUND(c.max_aqi::numeric, 1)::float AS max_aqi,
                ROUND((c.unhealthy_rate * 100)::numeric, 1)::float AS unhealthy_pct,
                ROUND((c.anomaly_rate * 100)::numeric, 1)::float AS anomaly_pct
            FROM ml_station_cluster_result c
            JOIN dim_location dl ON dl.location_key = c.location_key
            WHERE {' AND '.join(cluster_where)}
            ORDER BY c.avg_aqi DESC
            LIMIT 10
        """
        cluster_rows = self._query(cluster_sql, tuple(cluster_params))

        # Chuan hoa nhan cum K-Means sang tieng Viet co dau dong bo giao dien
        cluster_label_map = {
            "Trong lanh / Chat luong tot": "Trong lành / Chất lượng tốt",
            "Trong lanh (Tot)": "Trong lành (Tốt)",
            "O nhiem thap / Trong lanh": "Ô nhiễm thấp / Trong lành",
            "O nhiem trung binh": "Ô nhiễm trung bình",
            "Trung binh": "Trung bình",
            "Kem (O nhiem)": "Kém (Ô nhiễm)",
            "Kem": "Kém",
            "O nhiem cao": "Ô nhiễm cao",
            "O nhiem rat cao": "Ô nhiễm rất cao",
            "O nhiem nghiem trong": "Ô nhiễm nghiêm trọng",
            "Xau / Nguy hai": "Xấu / Nguy hại",
            "Xau": "Xấu",
            "Nguy hai": "Nguy hại",
            "Rat tot": "Rất tốt",
        }
        for r in cluster_rows:
            raw_lbl = str(r.get("cluster_label") or "").strip()
            if raw_lbl in cluster_label_map:
                r["cluster_label"] = cluster_label_map[raw_lbl]
            elif raw_lbl.startswith("Cum "):
                r["cluster_label"] = "Cụm " + raw_lbl[4:]
            elif raw_lbl:
                r["cluster_label"] = (
                    raw_lbl.replace("O nhiem", "Ô nhiễm")
                    .replace("o nhiem", "ô nhiễm")
                    .replace("Trong lanh", "Trong lành")
                    .replace("trong lanh", "trong lành")
                    .replace("Chat luong tot", "Chất lượng tốt")
                    .replace("chat luong tot", "chất lượng tốt")
                    .replace("trung binh", "trung bình")
                    .replace("nghiem trong", "nghiêm trọng")
                    .replace("Nguy hai", "Nguy hại")
                )

        # 10. Toa do va trang thai tram phuc vu Ban do Geospatial Leaflet Map
        station_marker_rows = self._query(
            """
            SELECT 
                dl.location_name,
                dl.city,
                dl.country_code,
                dl.latitude::float AS lat,
                dl.longitude::float AS lon,
                ROUND(AVG(fm.aqi)::numeric, 0)::int AS aqi,
                ROUND(AVG(fm.temperature)::numeric, 1)::float AS temp,
                ROUND(AVG(fm.humidity)::numeric, 1)::float AS humidity,
                ROUND(AVG(CASE WHEN dp.parameter_name = 'pm25' THEN fm.value END)::numeric, 1)::float AS pm25
            FROM dim_location dl
            JOIN fact_measurement fm ON fm.location_key = dl.location_key
            JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
            WHERE dl.latitude IS NOT NULL AND dl.longitude IS NOT NULL
            GROUP BY dl.location_name, dl.city, dl.country_code, dl.latitude, dl.longitude
            ORDER BY dl.country_code, dl.city
            """
        )
        station_markers = []
        for r in station_marker_rows:
            st_aqi = int(r["aqi"] or 50)
            meta = get_aqi_meta(st_aqi)
            station_markers.append({
                "name": r["location_name"],
                "city": r["city"],
                "country": r["country_code"],
                "lat": r["lat"],
                "lon": r["lon"],
                "aqi": st_aqi,
                "category": meta["label"],
                "color": meta["color"],
                "temp": r["temp"] if r["temp"] is not None else 27.5,
                "humidity": r["humidity"] if r["humidity"] is not None else 80.0,
                "pm25": r["pm25"] if r["pm25"] is not None else 25.0,
            })

        # 11. Thong ke so sanh Viet Nam vs Thai Lan
        country_compare_rows = self._query(
            """
            SELECT 
                dl.country_code,
                COUNT(DISTINCT dl.location_key) AS total_stations,
                ROUND(AVG(fm.aqi)::numeric, 0)::int AS avg_aqi,
                ROUND(AVG(CASE WHEN dp.parameter_name = 'pm25' THEN fm.value END)::numeric, 1)::float AS avg_pm25,
                ROUND(AVG(fm.temperature)::numeric, 1)::float AS avg_temp,
                ROUND(AVG(fm.humidity)::numeric, 1)::float AS avg_hum,
                ROUND(COUNT(CASE WHEN fm.aqi > 100 THEN 1 END) * 100.0 / NULLIF(COUNT(fm.measurement_key), 0), 1)::float AS unhealthy_pct
            FROM fact_measurement fm
            JOIN dim_location dl ON dl.location_key = fm.location_key
            JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
            GROUP BY dl.country_code
            ORDER BY dl.country_code
            """
        )
        country_comparison = {
            r["country_code"]: r for r in country_compare_rows
        }

        total_stations_cnt = len(active_stations)
        active_cnt = int(kpi.get("active_stations") or total_stations_cnt)

        return {
            "filters": {
                "selected_country": country_filter,
                "selected_city": city_filter,
                "selected_station": station_filter,
                "countries": [
                    {"code": "all", "name": "Tất cả quốc gia"},
                    {"code": "VN", "name": "Việt Nam (VN)"},
                    {"code": "TH", "name": "Thái Lan (TH)"},
                ],
                "cities_by_country": cities_by_country,
                "stations_by_city": stations_by_city,
                "cities": active_cities,
                "stations": active_stations,
                "date_range": f"{min_date_str} – {max_date_str}",
                "updated_at": updated_str,
            },
            "overview": {
                "national_aqi": national_aqi,
                "category": aqi_meta["label"],
                "color": aqi_meta["color"],
                "updated_at": updated_str,
                "pollution_groups": pollution_groups,
                "active_stations": {
                    "active": active_cnt,
                    "total": total_stations_cnt,
                    "pct": round(active_cnt * 100.0 / max(1, total_stations_cnt), 1),
                },
                "top_pollutant": top_pollutant,
                "pollutant_bars": pollutant_bars,
                "station_markers": station_markers,
                "country_comparison": country_comparison,
            },
            "trends": {
                "labels": time_labels,
                "series": trend_series,
                "heatmap": {
                    "hours": heatmap_hours,
                    "cities": heatmap_cities,
                    "matrix": heatmap_matrix,
                },
            },
            "locations": {
                "top10_cities": ranked_cities[:10],
                "all_cities": ranked_cities,
                "station_markers": station_markers,
            },
            "forecast_alerts": {
                "city": fc_city,
                "available_cities": valid_cities,
                "dates": fc_dates,
                "actual": actual_vals,
                "forecast": forecast_vals,
                "lower": lower_band,
                "upper": upper_band,
                "anomalies": anomalies,
                "clusters": cluster_rows,
            },
        }


class DashboardRequestHandler(BaseHTTPRequestHandler):
    service = DashboardDataService()
    template_path = os.path.join(os.path.dirname(__file__), "template.html")

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug("%s - %s", self.address_string(), format % args)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ["/", "/index.html"]:
            try:
                with open(self.template_path, "r", encoding="utf-8") as f:
                    html = f.read()
                body = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_error(500, str(e))
            return

        if parsed.path == "/api/dashboard-data":
            try:
                qs = parse_qs(parsed.query)
                payload = self.service.get_dashboard_payload(
                    country_filter=qs.get("country", ["all"])[0],
                    city_filter=qs.get("city", ["all"])[0],
                    station_filter=qs.get("station", ["all"])[0],
                    param_filter=qs.get("param", ["all"])[0],
                    trend_param=qs.get("trend_param", ["pm25"])[0],
                    granularity=qs.get("granularity", ["hour"])[0],
                    forecast_city=qs.get("forecast_city", ["Hà Nội"])[0],
                )
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                logger.error("Loi truy van dashboard API: %s", e)
                err_body = json.dumps({"error": str(e)}).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(err_body)))
                self.end_headers()
                self.wfile.write(err_body)
            return

        self.send_error(404, "Not Found")


def run_server(host: str = "0.0.0.0", port: int = 8050) -> None:
    server = HTTPServer((host, port), DashboardRequestHandler)
    logger.info("Web Dashboard Dark Mode dang chay tai http://%s:%d", host, port)
    server.serve_forever()


if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", "8050"))
    run_server(port=port)

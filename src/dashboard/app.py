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
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_dashboard_payload(
        self,
        city_filter: str = "all",
        station_filter: str = "all",
        param_filter: str = "all",
        trend_param: str = "pm25",
        granularity: str = "hour",
        forecast_city: str = "Hà Nội",
    ) -> Dict[str, Any]:
        # 1. Danh sach bo loc
        locations = self._query(
            "SELECT DISTINCT city, location_name, latitude, longitude FROM dim_location ORDER BY city, location_name"
        )
        cities = sorted(list({r["city"] for r in locations if r.get("city")}))
        stations = sorted(list({r["location_name"] for r in locations if r.get("location_name")}))

        # Dieu kien loc chung
        where_clauses = ["fm.aqi IS NOT NULL"]
        query_params: List[Any] = []
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

        min_date_str = kpi["min_date"].strftime("%d/%m/%Y") if kpi.get("min_date") else "20/10/2026"
        max_date_str = kpi["max_date"].strftime("%d/%m/%Y") if kpi.get("max_date") else "27/10/2026"

        # 3. Chi so AQI theo tung chat o nhiem
        pollutant_rows = self._query(
            """
            SELECT
                UPPER(dp.parameter_name) AS code,
                dp.display_name,
                dp.unit,
                ROUND(AVG(fm.aqi)::numeric, 0)::int AS avg_aqi,
                ROUND(AVG(fm.value)::numeric, 1)::float AS avg_val
            FROM fact_measurement fm
            JOIN dim_location dl ON dl.location_key = fm.location_key
            JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
            WHERE fm.aqi IS NOT NULL
            GROUP BY dp.parameter_name, dp.display_name, dp.unit
            """
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

        # 4. Xep hang Top thanh pho & Nhom muc o nhiem theo thanh pho
        city_aqi_rows = self._query(
            """
            SELECT
                dl.city,
                AVG(dl.latitude)::float AS lat,
                AVG(dl.longitude)::float AS lon,
                ROUND(AVG(fm.aqi)::numeric, 0)::int AS aqi
            FROM fact_measurement fm
            JOIN dim_location dl ON dl.location_key = fm.location_key
            JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
            WHERE dp.parameter_name = 'pm25'
            GROUP BY dl.city
            ORDER BY aqi DESC
            """
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
            order_expr = "dt.local_date"
        else:
            time_expr = "TO_CHAR(dt.datetime_utc + INTERVAL '7 hours', 'DD/MM HH24:00')"
            order_expr = "MIN(dt.datetime_utc)"

        focus_cities = ["Hà Nội", "TP. HCM", "Đà Nẵng", "Hải Phòng"]
        if city_filter and city_filter != "all" and city_filter not in focus_cities:
            focus_cities = [city_filter] + focus_cities[:3]

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
            GROUP BY {time_expr}, dl.city
            ORDER BY {order_expr} ASC
            """,
            (target_param, focus_cities),
        )
        time_labels: List[str] = []
        for r in trend_rows:
            if r["time_label"] not in time_labels:
                time_labels.append(r["time_label"])
        # Gioi han 36 diem gan nhat cho muot ma
        if len(time_labels) > 36:
            time_labels = time_labels[-36:]

        series_by_city: Dict[str, Dict[str, float]] = {c: {} for c in focus_cities}
        for r in trend_rows:
            if r["city"] in series_by_city:
                series_by_city[r["city"]][r["time_label"]] = r["avg_val"]

        trend_series = []
        city_colors = {
            "Hà Nội": "#f97316",
            "TP. HCM": "#3b82f6",
            "Đà Nẵng": "#10b981",
            "Hải Phòng": "#a855f7",
        }
        for c in focus_cities:
            trend_series.append({
                "city": c,
                "color": city_colors.get(c, "#38bdf8"),
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
        heatmap_cities = list(reversed(focus_cities))  # Hien thi Ha Noi o hang tren cung
        heatmap_hours = [f"{h}h" for h in range(24)]
        heatmap_matrix = []
        hm_lookup = {(r["city"], int(r["hour"])): int(r["avg_aqi"]) for r in heatmap_rows}
        for y_idx, c in enumerate(heatmap_cities):
            for h in range(24):
                val = hm_lookup.get((c, h), 55)
                heatmap_matrix.append([h, y_idx, val])

        # 7. Du bao ngan han (PM2.5) cho thanh pho duoc chon
        fc_city = forecast_city if forecast_city in cities else (cities[0] if cities else "Hà Nội")
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
            # Noi diem cuoi cua Thuc te voi diem dau cua Du bao
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

        # 8. Bang Cac diem bat thuong (Anomalies)
        anomaly_rows = self._query(
            """
            SELECT
                thoi_gian,
                tram,
                thong_so,
                gia_tri_do_duoc,
                nguong,
                muc_do,
                trang_thai,
                aqi
            FROM vw_anomaly_formatted
            LIMIT 12
            """
        )
        anomalies = []
        for r in anomaly_rows:
            anomalies.append({
                "time": r["thoi_gian"],
                "station": r["tram"],
                "param": "PM2.5" if r["thong_so"] == "PM25" else r["thong_so"],
                "value": r["gia_tri_do_duoc"].replace("ug/m3", "µg/m³"),
                "threshold": r["nguong"].replace("ug/m3", "µg/m³"),
                "severity": r["muc_do"],
                "status": r["trang_thai"],
            })

        # 9. Phan cum K-Means tram quan trac
        cluster_rows = self._query(
            """
            SELECT
                location_name,
                city,
                cluster,
                cluster_label,
                avg_aqi,
                max_aqi,
                unhealthy_pct,
                anomaly_pct
            FROM vw_ml_station_clusters
            ORDER BY avg_aqi DESC
            """
        )

        total_stations = len(stations)
        active_cnt = int(kpi.get("active_stations") or total_stations)

        return {
            "filters": {
                "cities": cities,
                "stations": stations,
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
                    "total": total_stations,
                    "pct": round(active_cnt * 100.0 / max(1, total_stations), 1),
                },
                "top_pollutant": top_pollutant,
                "pollutant_bars": pollutant_bars,
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
            },
            "forecast_alerts": {
                "city": fc_city,
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

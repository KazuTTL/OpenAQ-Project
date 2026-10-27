import json
import os
import requests
from typing import Dict, Any, List

SUPERSET_URL = os.getenv("SUPERSET_URL", "http://127.0.0.1:8088")
ADMIN_USER = "admin"
ADMIN_PASS = "admin"
DB_NAME = "PostgreSQL"

DARK_MODE_CSS = """
/* OpenAQ Vietnam Dark Mode Theme for Apache Superset */
.dashboard,
.dashboard-content,
.grid-container,
body {
  background-color: #070d19 !important;
  color: #f1f5f9 !important;
}

.header-with-actions,
.dashboard-header {
  background-color: #0b1324 !important;
  border-bottom: 1px solid #1e3158 !important;
  color: #ffffff !important;
}

.ant-tabs-nav {
  background-color: #0b1324 !important;
  border-bottom: 1px solid #1e3158 !important;
  padding: 0 16px !important;
}

.ant-tabs-tab {
  color: #94a3b8 !important;
  font-weight: 600 !important;
}

.ant-tabs-tab-active .ant-tabs-tab-btn {
  color: #38bdf8 !important;
}

.dashboard-component-chart-holder,
.chart-slice,
.slice_container {
  background: linear-gradient(180deg, #101b33 0%, #0d172c 100%) !important;
  border: 1px solid #1e3158 !important;
  border-radius: 12px !important;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35) !important;
  color: #f1f5f9 !important;
}

.chart-header,
.header-title,
.editable-title a,
.editable-title input {
  color: #f8fafc !important;
  font-weight: 700 !important;
}

.superset-chart-table table,
table.table {
  background-color: #101b33 !important;
  color: #e2e8f0 !important;
}

.superset-chart-table th,
table.table th {
  background-color: #15223f !important;
  color: #38bdf8 !important;
  border-bottom: 1px solid #1e3158 !important;
}

.superset-chart-table td,
table.table td {
  background-color: #101b33 !important;
  color: #e2e8f0 !important;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06) !important;
}
"""


class SupersetDashboardBuilder:
    def __init__(self, base_url: str = SUPERSET_URL):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.database_id = 1

    def authenticate(self) -> None:
        resp = self.session.post(
            f"{self.base_url}/api/v1/security/login",
            json={
                "username": ADMIN_USER,
                "password": ADMIN_PASS,
                "provider": "db",
                "refresh": True,
            },
            timeout=15,
        )
        resp.raise_for_status()
        token = resp.json()["access_token"]
        self.session.headers.update({"Authorization": f"Bearer {token}"})

        csrf_resp = self.session.get(f"{self.base_url}/api/v1/security/csrf_token/", timeout=15)
        csrf_resp.raise_for_status()
        csrf_token = csrf_resp.json()["result"]
        session_cookie = self.session.cookies.get_dict().get("session", "")
        self.session.headers.update({
            "X-CSRFToken": csrf_token,
            "Cookie": f"session={session_cookie}",
            "Referer": self.base_url,
            "Content-Type": "application/json",
        })

        dbs = self.session.get(f"{self.base_url}/api/v1/database/", timeout=15).json()
        if dbs.get("ids"):
            self.database_id = dbs["ids"][0]
        print(f"[OK] Authenticated with Superset. Using Database ID: {self.database_id}")

    def get_or_create_dataset(self, table_name: str, schema: str = "public") -> int:
        all_ds = self.session.get(
            f"{self.base_url}/api/v1/dataset/",
            params={"q": "(page_size:100)"},
            timeout=15,
        ).json()
        matching = [
            r for r in all_ds.get("result", [])
            if r.get("table_name") == table_name
        ]
        if matching:
            ds_id = matching[0]["id"]
            self.session.put(
                f"{self.base_url}/api/v1/dataset/{ds_id}/refresh",
                timeout=15,
            )
            print(f"[OK] Dataset '{table_name}' already exists (id={ds_id}), refreshed columns.")
            return ds_id

        create_resp = self.session.post(
            f"{self.base_url}/api/v1/dataset/",
            json={
                "database": self.database_id,
                "schema": schema,
                "table_name": table_name,
            },
            timeout=15,
        )
        if not create_resp.ok:
            print(f"[ERR] Create dataset '{table_name}' failed: {create_resp.status_code} {create_resp.text}")
        create_resp.raise_for_status()
        ds_id = create_resp.json()["id"]
        print(f"[OK] Created Dataset '{table_name}' (id={ds_id}).")
        return ds_id

    def create_or_update_chart(
        self,
        slice_name: str,
        viz_type: str,
        dataset_id: int,
        params: Dict[str, Any],
        description: str = "",
    ) -> int:
        params_with_ds = dict(params)
        params_with_ds["datasource"] = f"{dataset_id}__table"
        params_with_ds["viz_type"] = viz_type

        all_charts = self.session.get(
            f"{self.base_url}/api/v1/chart/",
            params={"q": "(page_size:100)"},
            timeout=15,
        ).json()
        matching = [
            r for r in all_charts.get("result", [])
            if r.get("slice_name") == slice_name
        ]

        payload = {
            "slice_name": slice_name,
            "viz_type": viz_type,
            "datasource_id": dataset_id,
            "datasource_type": "table",
            "params": json.dumps(params_with_ds),
            "description": description,
        }

        if matching:
            results = sorted(matching, key=lambda r: r["id"])
            chart_id = results[0]["id"]
            for dup in results[1:]:
                self.session.delete(f"{self.base_url}/api/v1/chart/{dup['id']}", timeout=15)
            resp = self.session.put(
                f"{self.base_url}/api/v1/chart/{chart_id}",
                json=payload,
                timeout=15,
            )
            if not resp.ok:
                print(f"[ERR] Update chart '{slice_name}' failed: {resp.status_code} {resp.text}")
            resp.raise_for_status()
            print(f"[OK] Updated Chart '{slice_name}' (id={chart_id}, viz={viz_type}).")
            return chart_id

        resp = self.session.post(
            f"{self.base_url}/api/v1/chart/",
            json=payload,
            timeout=15,
        )
        if not resp.ok:
            print(f"[ERR] Create chart '{slice_name}' failed: {resp.status_code} {resp.text}")
        resp.raise_for_status()
        chart_id = resp.json()["id"]
        print(f"[OK] Created Chart '{slice_name}' (id={chart_id}, viz={viz_type}).")
        return chart_id

    def create_or_update_dashboard(
        self,
        title: str,
        slug: str,
        rows_by_tab: Dict[str, List[List[Dict[str, Any]]]],
    ) -> int:
        position_json = self._build_tabbed_rows_layout(title, rows_by_tab)

        all_dash = self.session.get(
            f"{self.base_url}/api/v1/dashboard/",
            params={"q": "(page_size:100)"},
            timeout=15,
        ).json()
        matching = [
            r for r in all_dash.get("result", [])
            if r.get("slug") == slug
        ]

        payload = {
            "dashboard_title": title,
            "slug": slug,
            "position_json": json.dumps(position_json),
            "css": DARK_MODE_CSS,
            "published": True,
        }

        if matching:
            dash_id = matching[0]["id"]
            resp = self.session.put(
                f"{self.base_url}/api/v1/dashboard/{dash_id}",
                json=payload,
                timeout=15,
            )
            if not resp.ok:
                print(f"[ERR] Update dashboard '{title}' failed: {resp.status_code} {resp.text}")
            resp.raise_for_status()
            print(f"[OK] Updated Dashboard '{title}' (id={dash_id}, slug={slug}).")
        else:
            resp = self.session.post(
                f"{self.base_url}/api/v1/dashboard/",
                json=payload,
                timeout=15,
            )
            if not resp.ok:
                print(f"[ERR] Create dashboard '{title}' failed: {resp.status_code} {resp.text}")
            resp.raise_for_status()
            dash_id = resp.json()["id"]
            print(f"[OK] Created Dashboard '{title}' (id={dash_id}, slug={slug}).")

        linked_ids = set()
        for rows in rows_by_tab.values():
            for row in rows:
                for chart_info in row:
                    linked_ids.add(chart_info["id"])

        for cid in sorted(linked_ids):
            link_resp = self.session.put(
                f"{self.base_url}/api/v1/chart/{cid}",
                json={"dashboards": [dash_id]},
                timeout=15,
            )
            link_resp.raise_for_status()
        print(f"[OK] Linked {len(linked_ids)} charts to Dashboard id={dash_id}.")
        return dash_id

    @staticmethod
    def _build_tabbed_rows_layout(
        title: str,
        rows_by_tab: Dict[str, List[List[Dict[str, Any]]]],
    ) -> Dict[str, Any]:
        layout: Dict[str, Any] = {
            "DASHBOARD_VERSION_KEY": "v2",
            "ROOT_ID": {
                "type": "ROOT",
                "id": "ROOT_ID",
                "children": ["TABS-MAIN"],
            },
            "HEADER_ID": {
                "id": "HEADER_ID",
                "type": "HEADER",
                "meta": {"text": title},
            },
            "TABS-MAIN": {
                "id": "TABS-MAIN",
                "type": "TABS",
                "children": [],
                "parents": ["ROOT_ID"],
                "meta": {},
            },
        }

        for tab_idx, (tab_title, rows) in enumerate(rows_by_tab.items(), start=1):
            tab_id = f"TAB-PAGE-{tab_idx}"
            layout["TABS-MAIN"]["children"].append(tab_id)
            layout[tab_id] = {
                "id": tab_id,
                "type": "TAB",
                "children": [],
                "parents": ["ROOT_ID", "TABS-MAIN"],
                "meta": {
                    "text": tab_title,
                    "defaultText": tab_title,
                },
            }

            for row_idx, row_charts in enumerate(rows, start=1):
                row_id = f"ROW-PAGE-{tab_idx}-{row_idx}"
                layout[tab_id]["children"].append(row_id)
                layout[row_id] = {
                    "id": row_id,
                    "type": "ROW",
                    "children": [],
                    "parents": ["ROOT_ID", "TABS-MAIN", tab_id],
                    "meta": {"background": "BACKGROUND_TRANSPARENT"},
                }

                for chart_idx, chart_info in enumerate(row_charts, start=1):
                    chart_node_id = f"CHART-{tab_idx}-{row_idx}-{chart_idx}"
                    layout[row_id]["children"].append(chart_node_id)
                    layout[chart_node_id] = {
                        "id": chart_node_id,
                        "type": "CHART",
                        "children": [],
                        "parents": ["ROOT_ID", "TABS-MAIN", tab_id, row_id],
                        "meta": {
                            "chartId": chart_info["id"],
                            "sliceName": chart_info["name"],
                            "width": chart_info.get("width", 6),
                            "height": chart_info.get("height", 48),
                        },
                    }

        return layout


def main():
    builder = SupersetDashboardBuilder()
    builder.authenticate()

    # 1. Dang ky tat ca Views phan tich thanh Datasets tren Superset
    ds_kpi = builder.get_or_create_dataset("vw_kpi_overview")
    ds_cat = builder.get_or_create_dataset("vw_pollution_category_dist")
    ds_pollutant = builder.get_or_create_dataset("vw_pollutant_aqi_avg")
    ds_city_pm25 = builder.get_or_create_dataset("vw_city_pm25_hourly")
    ds_city_hm = builder.get_or_create_dataset("vw_city_hourly_heatmap")
    ds_top10 = builder.get_or_create_dataset("vw_city_top10_aqi")
    ds_map = builder.get_or_create_dataset("vw_station_map")
    ds_rank = builder.get_or_create_dataset("vw_station_ranking")
    ds_anom_fmt = builder.get_or_create_dataset("vw_anomaly_formatted")
    ds_cluster = builder.get_or_create_dataset("vw_ml_station_clusters")
    builder.get_or_create_dataset("vw_daily_aqi_trend")
    builder.get_or_create_dataset("vw_hourly_weekday_heatmap")
    builder.get_or_create_dataset("vw_anomaly_alerts")
    builder.get_or_create_dataset("vw_fact_enriched")

    # 2. Tao cac bieu do theo thiet ke Air Quality Monitoring Vietnam
    c1_kpi = builder.create_or_update_chart(
        slice_name="1.1 Chi so KPI Tong quan He thong",
        viz_type="table",
        dataset_id=ds_kpi,
        params={
            "query_mode": "raw",
            "all_columns": [
                "overall_avg_aqi",
                "active_stations_count",
                "total_measurements",
                "total_anomalies",
                "latest_data_timestamp",
            ],
            "row_limit": 10,
            "include_search": False,
        },
        description="AQI hien tai (toan quoc), So tram dang hoat dong va Tong phep do",
    )

    c1_pollutant_bars = builder.create_or_update_chart(
        slice_name="1.2 Chi so AQI theo Chat o nhiem (Trung binh toan quoc)",
        viz_type="dist_bar",
        dataset_id=ds_pollutant,
        params={
            "groupby": ["display_name"],
            "columns": [],
            "metrics": [
                {
                    "expressionType": "SIMPLE",
                    "column": {"column_name": "avg_aqi", "type": "INTEGER"},
                    "aggregate": "AVG",
                    "label": "Chi so AQI",
                }
            ],
            "adhoc_filters": [],
            "row_limit": 10,
            "show_legend": False,
            "y_axis_format": ",d",
            "color_scheme": "supersetColors",
        },
        description="So sanh chi so AQI trung binh toan quoc giua PM2.5, PM10, NO2, SO2, CO, O3",
    )

    c2_donut = builder.create_or_update_chart(
        slice_name="1.3 Nhom Muc do O nhiem (US EPA)",
        viz_type="pie",
        dataset_id=ds_cat,
        params={
            "groupby": ["pollution_category"],
            "metric": {
                "expressionType": "SIMPLE",
                "column": {"column_name": "measurement_count", "type": "BIGINT"},
                "aggregate": "SUM",
                "label": "So phep do",
            },
            "adhoc_filters": [],
            "row_limit": 20,
            "donut": True,
            "show_labels": True,
            "show_legend": True,
            "label_type": "key_percent",
            "color_scheme": "supersetColors",
        },
        description="Phan bo cac nhom muc o nhiem: Tot, Trung binh, Kem, Xau, Rat xau",
    )

    c3_trend = builder.create_or_update_chart(
        slice_name="2.1 Nong do PM2.5 (µg/m³) theo Thoi gian & Thanh pho",
        viz_type="echarts_timeseries_line",
        dataset_id=ds_city_pm25,
        params={
            "x_axis": "datetime_utc",
            "time_grain_sqla": "PT1H",
            "granularity_sqla": "datetime_utc",
            "time_range": "No filter",
            "metrics": [
                {
                    "expressionType": "SIMPLE",
                    "column": {"column_name": "concentration_ugm3", "type": "FLOAT"},
                    "aggregate": "AVG",
                    "label": "Nong do PM2.5 (ug/m3)",
                }
            ],
            "groupby": ["city"],
            "adhoc_filters": [],
            "row_limit": 2000,
            "show_legend": True,
            "rich_tooltip": True,
            "markerEnabled": False,
            "y_axis_format": ",.1f",
        },
        description="Xu huong nong do PM2.5 theo gio giua Ha Noi, TP. HCM, Da Nang, Hai Phong va cac tinh thanh",
    )

    c4_heatmap = builder.create_or_update_chart(
        slice_name="2.2 Ban do nhiet AQI theo Gio (Toan quoc)",
        viz_type="heatmap",
        dataset_id=ds_city_hm,
        params={
            "all_columns_x": "hour_label",
            "all_columns_y": "city",
            "metric": {
                "expressionType": "SIMPLE",
                "column": {"column_name": "avg_aqi", "type": "INTEGER"},
                "aggregate": "AVG",
                "label": "AQI Trung binh",
            },
            "adhoc_filters": [],
            "linear_color_scheme": "yl_or_rd",
            "xscale_interval": 2,
            "yscale_interval": 1,
            "show_legend": True,
            "show_values": False,
        },
        description="Ban do nhiet AQI theo khung gio (00h-23h) tai cac thanh pho lon",
    )

    c5_top10 = builder.create_or_update_chart(
        slice_name="3.1 Top 10 Thanh pho co AQI cao nhat",
        viz_type="table",
        dataset_id=ds_top10,
        params={
            "query_mode": "raw",
            "all_columns": [
                "rank_no",
                "thanh_pho",
                "aqi",
                "muc_do",
            ],
            "row_limit": 10,
            "include_search": False,
        },
        description="Bang xep hang Top 10 thanh pho co chi so AQI cao nhat Viet Nam",
    )

    c6_map_table = builder.create_or_update_chart(
        slice_name="3.2 Toa do Dia ly & Chi so AQI cac Tram quan trac",
        viz_type="table",
        dataset_id=ds_map,
        params={
            "query_mode": "raw",
            "all_columns": [
                "location_name",
                "city",
                "latitude",
                "longitude",
                "avg_aqi",
                "max_aqi",
                "unhealthy_hours",
            ],
            "row_limit": 20,
            "include_search": True,
        },
        description="Thong tin vi tri dia ly va chi so AQI chi tiet cua 12 tram quan trac",
    )

    c6_rank = builder.create_or_update_chart(
        slice_name="3.3 Bieu do So sanh AQI Trung binh & Cuc dai theo Tram",
        viz_type="dist_bar",
        dataset_id=ds_rank,
        params={
            "groupby": ["city", "location_name"],
            "columns": [],
            "metrics": [
                {
                    "expressionType": "SIMPLE",
                    "column": {"column_name": "average_aqi", "type": "FLOAT"},
                    "aggregate": "AVG",
                    "label": "AQI Trung binh",
                },
                {
                    "expressionType": "SIMPLE",
                    "column": {"column_name": "max_aqi", "type": "FLOAT"},
                    "aggregate": "MAX",
                    "label": "AQI Cuc dai",
                },
            ],
            "adhoc_filters": [],
            "row_limit": 20,
            "show_legend": True,
            "y_axis_format": ",.1f",
            "color_scheme": "supersetColors",
        },
        description="So sanh AQI trung binh va cuc dai giua cac tram quan trac",
    )

    c7_anomaly = builder.create_or_update_chart(
        slice_name="4.1 Cac diem bat thuong (Canh bao & Theo doi)",
        viz_type="table",
        dataset_id=ds_anom_fmt,
        params={
            "query_mode": "raw",
            "all_columns": [
                "thoi_gian",
                "tram",
                "thong_so",
                "gia_tri_do_duoc",
                "nguong",
                "muc_do",
                "trang_thai",
            ],
            "row_limit": 50,
            "include_search": True,
        },
        description="Danh sach cac diem do vuot nguong bat thuong kem muc do va trang thai Canh bao / Theo doi",
    )

    c8_cluster = builder.create_or_update_chart(
        slice_name="4.2 Phan cum Tram do K-Means (ML Clustering)",
        viz_type="table",
        dataset_id=ds_cluster,
        params={
            "query_mode": "raw",
            "all_columns": [
                "location_name",
                "city",
                "cluster",
                "cluster_label",
                "avg_aqi",
                "max_aqi",
                "unhealthy_pct",
                "anomaly_pct",
            ],
            "row_limit": 20,
            "include_search": False,
        },
        description="Ket qua phan cum 12 tram quan trac bang thuat toan K-Means",
    )

    # 3. Bo cuc Dashboard: Tab 1 (Bo cuc 2x2 Tong quan giong anh mau) + 4 Tab chi tiet
    rows_by_tab = {
        "Tong quan (Bo cuc 2x2)": [
            [
                {"id": c1_pollutant_bars, "name": "1.2 Chi so AQI theo Chat o nhiem (Trung binh toan quoc)", "width": 6, "height": 50},
                {"id": c3_trend, "name": "2.1 Nong do PM2.5 (µg/m³) theo Thoi gian & Thanh pho", "width": 6, "height": 50},
            ],
            [
                {"id": c5_top10, "name": "3.1 Top 10 Thanh pho co AQI cao nhat", "width": 5, "height": 52},
                {"id": c4_heatmap, "name": "2.2 Ban do nhiet AQI theo Gio (Toan quoc)", "width": 7, "height": 52},
            ],
            [
                {"id": c1_kpi, "name": "1.1 Chi so KPI Tong quan He thong", "width": 5, "height": 42},
                {"id": c7_anomaly, "name": "4.1 Cac diem bat thuong (Canh bao & Theo doi)", "width": 7, "height": 42},
            ],
        ],
        "Xu huong thoi gian": [
            [
                {"id": c3_trend, "name": "2.1 Nong do PM2.5 (µg/m³) theo Thoi gian & Thanh pho", "width": 12, "height": 52},
            ],
            [
                {"id": c4_heatmap, "name": "2.2 Ban do nhiet AQI theo Gio (Toan quoc)", "width": 12, "height": 52},
            ],
        ],
        "Theo vi tri": [
            [
                {"id": c5_top10, "name": "3.1 Top 10 Thanh pho co AQI cao nhat", "width": 5, "height": 55},
                {"id": c6_rank, "name": "3.3 Bieu do So sanh AQI Trung binh & Cuc dai theo Tram", "width": 7, "height": 55},
            ],
            [
                {"id": c6_map_table, "name": "3.2 Toa do Dia ly & Chi so AQI cac Tram quan trac", "width": 12, "height": 45},
            ],
        ],
        "Du bao & canh bao": [
            [
                {"id": c7_anomaly, "name": "4.1 Cac diem bat thuong (Canh bao & Theo doi)", "width": 7, "height": 55},
                {"id": c8_cluster, "name": "4.2 Phan cum Tram do K-Means (ML Clustering)", "width": 5, "height": 55},
            ],
            [
                {"id": c2_donut, "name": "1.3 Nhom Muc do O nhiem (US EPA)", "width": 12, "height": 45},
            ],
        ],
    }

    dash_id = builder.create_or_update_dashboard(
        title="AIR QUALITY MONITORING - Viet Nam",
        slug="openaq-air-quality-dashboard",
        rows_by_tab=rows_by_tab,
    )
    print(f"\n[DONE] Superset Dashboard san sang tai: {SUPERSET_URL}/superset/dashboard/openaq-air-quality-dashboard/ (id={dash_id})")


if __name__ == "__main__":
    main()

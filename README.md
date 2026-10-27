# He thong Data Warehouse va ETL phan tich chat luong khong khi tu OpenAQ

## 1. Gioi thieu de tai
Du an xay dung he thong Data Warehouse va quy trinh ETL nham thu thap, lam sach, tinh toan chi so chat luong khong khi (AQI theo chuan US EPA), luu tru du lieu lich su va phuc vu phan tich chuyen sau (thong ke mo ta, phat hien bat thuong, phan cum tram do, du doan o nhiem khong khi, truc quan hoa tren Power BI, Apache Superset va Web Dashboard Dark Mode).

- Nguon du lieu chinh: OpenAQ REST API v3 (tap trung khu vuc Viet Nam - ma quoc gia VN gom 12 tram quan trac tieu bieu tai 11 tinh/thanh pho lon: Ha Noi, TP. HCM, Da Nang, Hai Phong, Bien Hoa, Bac Ninh, Vinh, Thai Nguyen, Can Tho, Nha Trang, Da Lat).
- 6 thong so giam sat: PM2.5, PM10, O3, NO2, SO2, CO.

---

## 2. Kien truc tong the

```
[OpenAQ REST API v3 / Sensor Fallback]
                  |
            (Airflow DAG)
                  v
    [MinIO / S3 Raw Data Lake]
      (raw/openaq/YYYY/MM/DD/)
                  |
     (Transform: 7 buoc lam sach + tinh AQI)
                  v
  [MinIO / S3 Processed Data Lake]
  (measurements_cleaned.parquet)
                  |
     (Load: Staging -> Dimensions -> Fact)
                  v
[Data Warehouse (PostgreSQL - Star Schema)]
                  |
    +-------------+-------------+
    |                           |
    v                           v
[Phan tich & Machine Learning] [Truc quan hoa & Dashboard]
- Phat hien bat thuong (Z-score) - Web Dashboard Dark Mode (Port 8050)
- Phan cum K-Means (Silhouette)   - Apache Superset (Port 8088)
- Khai pha mau o nhiem (Heatmap)  - Power BI (air_quality_dashboard.pbix)
- Du bao PM2.5 (Random Forest)
```

---

## 3. Danh muc cong ket noi & Duong dan dich vu

| Dich vu / He thong | Duong dan truy cap (URL / Host) | Cong (Port) | Tai khoan / Mat khau | Muc dich su dung |
| :--- | :--- | :---: | :--- | :--- |
| **Web Dashboard (Dark Mode)** | `http://localhost:8050` | `8050` | Khong yeu cau (truy cap truc tiep) | Giao dien giam sat chat luong khong khi Viet Nam luoi 2x2, ban do SVG co Hoang Sa & Truong Sa, duong du bao PM2.5 va bang canh bao bat thuong. |
| **Apache Superset** | `http://localhost:8088/superset/dashboard/openaq-air-quality-dashboard/` | `8088` | `admin` / `admin` | Dashboard BI quan tri 4 tabs (Tong quan, Xu huong, Vi tri, Du bao & canh bao) da duoc tich hop CSS Dark Mode. |
| **Apache Airflow Web UI** | `http://localhost:8082` | `8082` | `airflow` / `airflow` | Giao dien quan ly lich trinh, theo doi trang thai va kich hoat pipeline `openaq_pipeline_dag`. |
| **MinIO Console (S3 Web UI)** | `http://localhost:9001` | `9001` | `minioadmin` / `minioadmin` | Giao dien quan ly S3 Data Lake (xem cac bucket `raw/` va `processed/`). |
| **MinIO S3 API Endpoint** | `http://localhost:9000` | `9000` | Access/Secret: `minioadmin` / `minioadmin` | Cong API S3 cho ma nguon Python va Airflow doc ghi du lieu. |
| **PostgreSQL Data Warehouse** | `localhost:5432` | `5432` | User/Pass: `postgres` / `postgres`<br>Database: `openaq_dw` | Kho du lieu DWH Star Schema (fact_measurement, dim_*, bang ML va 14 views). |
| **PostgreSQL Airflow DB** | `localhost:5432` | `5432` | User/Pass: `postgres` / `postgres`<br>Database: `airflow_db` | Co so du lieu metadata noi bo cua Airflow. |

---

## 4. Huong dan trien khai nhanh cho nguoi moi (Quick Start)

De nguoi khac co the clone ve va chay toan bo he thong tren may cua ho, thuc hien theo 4 buoc sau:

### Buoc 1: Clone ma nguon va chuyen sang nhanh moi nhat
```bash
git clone https://github.com/KazuTTL/OpenAQ-Project.git
cd OpenAQ-Project
git checkout feat/unified-pipeline-dashboard
```

### Buoc 2: Khoi tao file cau hinh moi truong
- Tren Windows PowerShell:
```powershell
Copy-Item .env.example .env
```
- Tren Linux / macOS:
```bash
cp .env.example .env
```
*(Luu y: Neu chua co OpenAQ API Key, he thong tu dong chuyen sang co che Sensor Fallback de sinh du lieu chuan 12 tram Viet Nam).*

### Buoc 3: Khoi dong ha tang Docker
Yeu cau da bat san Docker Desktop tren may:
```bash
docker compose -f docker/docker-compose.yml up -d
```
Lenh nay se khoi dong dong thoi 6 containers: `openaq_postgres`, `openaq_minio`, `openaq_airflow_init`, `openaq_airflow_scheduler`, `openaq_airflow_webserver`, `openaq_web_dashboard` va `openaq_superset`.

### Buoc 4: Chay Pipeline nap du lieu va mo Dashboard
1. Chay toan bo quy trinh ETL va AI/ML:
```bash
docker exec openaq_airflow_scheduler python -m src.pipeline
```
2. Mo trinh duyet va su dung:
- Web Dashboard Dark Mode: `http://localhost:8050`
- Apache Superset Dashboard: `http://localhost:8088` (neu su dung Superset lan dau, chay `python analytics/setup_superset_dashboard.py` de tu dong tao toan bo bieu do va dashboard).
- Airflow UI: `http://localhost:8082`

---

## 5. Quy trinh xu ly du lieu (7 buoc Transform)

1. **Remove Duplicate**: Loai bo trung lap hoan toan tren bo khoa tu nhien (tram, thong so, thoi gian).
2. **Handle Missing**: Xu ly cac ban ghi thieu thoi gian hoac thieu gia tri do.
3. **Validate Measurement**: Loai bo gia tri am, loc cac gia tri vuot nguong vat ly, danh dau loi cam bien.
4. **Data Quality Validation**: Xuat bao cao thong ke chat luong du lieu.
5. **Normalize Location**: Chuan hoa ten thanh pho, kiem tra toa do vi do `[-90, 90]` va kinh do `[-180, 180]`.
6. **Convert Timezone**: Dong bo gio UTC va tinh toan `local_datetime` (UTC+7 cho Viet Nam).
7. **Calculate AQI**: Tinh chi so chat luong khong khi (AQI) va phan cap muc do o nhiem theo cong thuc tieu chuan US EPA.

---

## 6. Mo hinh Data Warehouse (Star Schema)

- **Bang Staging**: `staging_measurement` tiep nhan du lieu sau transform.
- **Cac bang Dimension**:
  - `dim_time`: Cac chieu thoi gian (nam, quy, thang, ngay, gio, thu, mua).
  - `dim_location`: Tram do, toa do vi do, kinh do, thanh pho, quoc gia, mui gio.
  - `dim_parameter`: Danh muc 6 thong so do luong (PM2.5, PM10, O3, NO2, SO2, CO kem don vi).
- **Bang Fact**:
  - `fact_measurement`: Luu tru gia tri do, chi so AQI, phan cap o nhiem, co danh dau bat thuong (`is_anomaly`), diem bat thuong (`anomaly_score`), phuong phap (`anomaly_method`).
- **Cac bang ML & Views**:
  - `ml_station_cluster_result`: Ket qua phan cum K-Means tram do.
  - `ml_pollution_pattern`: Ket qua khai pha mau gio, ngay va dot o nhiem keo dai.
  - 14 Views phan tich SQL toi uu cho BI va Dashboard: `vw_fact_enriched`, `vw_kpi_overview`, `vw_pollution_category_dist`, `vw_pollutant_aqi_avg`, `vw_city_top10_aqi`, `vw_city_hourly_heatmap`, `vw_city_pm25_hourly`, `vw_station_map`, `vw_station_ranking`, `vw_anomaly_formatted`, `vw_ml_station_clusters`...

---

## 7. Chay kiem thu (Unit Tests)

Chay toan bo 38 bai kiem thu don vi cho ca tang ETL va Machine Learning:
```bash
python -m unittest discover tests
```

---

## 8. Cau truc thu muc ma nguon

```
OpenAQ-Project-Unified/
|-- analytics/                     # Tai nguyen truc quan hoa Dashboard
|   |-- air_quality_dashboard.pbix # File Dashboard Power BI
|   |-- queries.sql                # Truy van SQL phuc vu Power BI
|   `-- setup_superset_dashboard.py# Script tu dong hoa tao Dashboard tren Superset
|-- dags/                          # Airflow DAGs dinh ky
|   `-- openaq_pipeline_dag.py     # DAG dieu phoi Extract -> Transform -> Load -> ML
|-- docker/
|   |-- docker-compose.yml         # Cau hinh toan bo containers (Postgres, MinIO, Airflow, Superset, Web Dashboard)
|   `-- init-multiple-dbs.sh       # Script khoi tao nhieu database trong Postgres
|-- sql/
|   |-- create_tables.sql          # DDL khoi tao Star Schema DWH, bang ML va 14 Views
|   |-- analysis_queries.sql       # Cac cau truy van phan tich chuyen sau
|   `-- migrations/                # Cac script cap nhat co so du lieu
|-- src/
|   |-- extract/                   # Thu thap OpenAQ API v3 va ghi MinIO Raw
|   |-- transform/                 # 7 buoc lam sach du lieu va tinh AQI US EPA
|   |-- load/                      # Nap du lieu Staging, Dimensions, Fact
|   |-- analysis/                  # Phan he AI/ML: Anomaly Detection, K-Means, Pattern Mining, Forecast
|   |-- dashboard/                 # Web Dashboard Dark Mode (app.py & template.html)
|   |-- utils/                     # Ket noi CSDL, MinIO, cau hinh, ghi log
|   `-- pipeline.py                # File dieu phoi toan bo luong thuc thi
|-- tests/                         # 38 bo kiem thu don vi (Unit Tests cho ETL & ML)
|-- Implement/                     # Nhat ky va tien do trien khai tung phien
|-- PROJECT_OVERVIEW.md            # Tai lieu tong quan toan bo kien truc du an
|-- requirements.txt               # Danh sach thu vien tong hop
|-- .env.example                   # Mau bien moi truong
`-- README.md                      # Tai lieu huong dan du an
```

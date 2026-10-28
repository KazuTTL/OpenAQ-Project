# He thong Data Warehouse va ETL phan tich chat luong khong khi tu OpenAQ

## 1. Gioi thieu de tai
Du an xay dung he thong Data Warehouse va quy trinh ETL nham thu thap, lam sach, tinh toan chi so chat luong khong khi (AQI theo chuan US EPA), luu tru du lieu lich su va phuc vu phan tich chuyen sau (thong ke mo ta, phat hien bat thuong, phan cum tram do, du doan o nhiem khong khi, truc quan hoa tren Power BI, Apache Superset va Web Dashboard Dark Mode).

- Nguon du lieu chinh: OpenAQ REST API v3 (100% du lieu thuc te tu 52 tram quan trac thuoc 20 do thi Dong Nam A, uu tien Viet Nam: Ha Noi, TP. Ho Chi Minh va Thai Lan, tat ca cung mui gio UTC+7).
- Nguon du lieu khi tuong: Open-Meteo API tich hop lam giau nhiet do (do C) va do am (%) theo tung toa do va gio do.
- 6 thong so giam sat: PM2.5, PM10, O3, NO2, SO2, CO.
- Quy mo du lieu hien tai: Hon 50,000 ban ghi lich su 30 ngay qua trong kho du lieu DWH.

---

## 2. Kien truc tong the

```
[OpenAQ REST API v3]           [Open-Meteo API]
       |                               |
       +---------------+---------------+
                       |
                 (Airflow DAG - Hourly Micro-batching)
                       v
         [MinIO / S3 Raw Data Lake]
           (raw/openaq/YYYY/MM/DD/)
                       |
          (Transform: 7 buoc lam sach + Lam giau khi tuong + Tinh AQI)
                       v
       [MinIO / S3 Processed Data Lake]
       (measurements_cleaned.parquet / 30d_chunk_*.parquet)
                       |
          (Load: Staging -> Dimensions -> Fact)
                       v
     [Data Warehouse (PostgreSQL - Star Schema)]
                       |
         +-------------+-------------+
         |                           |
         v                           v
[Phan tich & Machine Learning]   [Truc quan hoa & Dashboard]
- Phat hien bat thuong           - Web Dashboard Dark Mode (Port 8050)
  (Isolation Forest, Z-score)      + Cascading Filter: Quoc gia -> Do thi -> Tram
- Phan cum K-Means dong            + Ban do Leaflet GIS mac dinh zoom Viet Nam
  (K toi uu, Silhouette 0.6747)    + The so sanh doi chuan Viet Nam vs Thai Lan
- Khai pha mau o nhiem             + Auto-refresh tu dong cap nhat
  (Gio, ngay, dot keo dai)       - Apache Superset (Port 8088)
- Du bao PM2.5 da bien             + Day du cac view Country & Regional Analytics
  (Random Forest Regressor +       - Power BI (air_quality_dashboard.pbix)
   Dac trung thoi tiet, R2: 0.640)
```

---

## 3. Danh muc cong ket noi & Duong dan dich vu

| Dich vu / He thong | Duong dan truy cap (URL / Host) | Cong (Port) | Tai khoan / Mat khau | Muc dich su dung |
| :--- | :--- | :---: | :--- | :--- |
| **Web Dashboard (Dark Mode)** | `http://localhost:8050` | `8050` | Khong yeu cau (truy cap truc tiep) | Giao dien giam sat chat luong khong khi Dong Nam A (uu tien Viet Nam), bo loc da tang Cascading, ban do Leaflet.js interactive zoom vao Viet Nam, the doi chuan VN vs TH, bieu do xu huong va du bao Random Forest. |
| **Apache Superset** | `http://localhost:8088/superset/dashboard/openaq-air-quality-dashboard/` | `8088` | `admin` / `admin` | Dashboard BI quan tri 4 tabs (Tong quan, Xu huong, Vi tri, Du bao & canh bao) ho tro phan tich da quoc gia va vung mien. |
| **Apache Airflow Web UI** | `http://localhost:8082` | `8082` | `airflow` / `airflow` | Giao dien quan ly lich trinh micro-batching theo gio `openaq_etl_hourly_pipeline`. |
| **MinIO Console (S3 Web UI)** | `http://localhost:9001` | `9001` | `minioadmin` / `minioadmin` | Giao dien quan ly S3 Data Lake (xem cac bucket `raw/` va `processed/`). |
| **MinIO S3 API Endpoint** | `http://localhost:9000` | `9000` | Access/Secret: `minioadmin` / `minioadmin` | Cong API S3 cho ma nguon Python va Airflow doc ghi du lieu. |
| **PostgreSQL Data Warehouse** | `localhost:5432` | `5432` | User/Pass: `postgres` / `postgres`<br>Database: `openaq_dw` | Kho du lieu DWH Star Schema (fact_measurement, dim_*, bang ML va cac views phan tich). |
| **PostgreSQL Airflow DB** | `localhost:5432` | `5432` | User/Pass: `postgres` / `postgres`<br>Database: `airflow_db` | Co so du lieu metadata noi bo cua Airflow. |

---

## 4. Huong dan trien khai nhanh (Quick Start)

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

### Buoc 3: Khoi dong ha tang Docker
Yeu cau da bat san Docker Desktop tren may:
```bash
docker compose -f docker/docker-compose.yml up -d
```
Lenh nay se khoi dong dong thoi cac containers: `openaq_postgres`, `openaq_minio`, `openaq_airflow_init`, `openaq_airflow_scheduler`, `openaq_airflow_webserver`, `openaq_web_dashboard` va `openaq_superset`.

### Buoc 4: Chay Pipeline nap du lieu va mo Dashboard
1. Chay toan bo quy trinh ETL va AI/ML:
```bash
docker exec openaq_airflow_scheduler python -m src.pipeline
```
2. Thu thap du lieu lich su 30 ngay cho 20 do thi (neu can backfill lai tu dau):
```bash
python scripts/backfill_30d.py
```
3. Mo trinh duyet va su dung:
- Web Dashboard Dark Mode: `http://localhost:8050`
- Apache Superset Dashboard: `http://localhost:8088`
- Airflow UI: `http://localhost:8082`

---

## 5. Quy trinh xu ly du lieu (7 buoc Transform)

1. **Remove Duplicate**: Loai bo trung lap hoan toan tren bo khoa tu nhien (tram, thong so, thoi gian).
2. **Handle Missing**: Xu ly cac ban ghi thieu thoi gian hoac thieu gia tri do.
3. **Validate Measurement**: Loai bo gia tri am, loc cac gia tri vuot nguong vat ly, danh dau loi cam bien.
4. **Data Quality Validation**: Xuat bao cao thong ke chat luong du lieu.
5. **Normalize Location**: Chuan hoa ten thanh pho, ma quoc gia (`country_code`), khu vuc (`region`), kiem tra toa do vi do `[-90, 90]` va kinh do `[-180, 180]`.
6. **Convert Timezone**: Dong bo gio UTC va tinh toan `local_datetime` (UTC+7).
7. **Calculate AQI**: Tinh chi so chat luong khong khi (AQI) va phan cap muc do o nhiem theo cong thuc tieu chuan US EPA.

---

## 6. Mo hinh Data Warehouse (Star Schema)

- **Bang Staging**: `staging_measurement` tiep nhan du lieu sau transform (19 thuoc tinh gom thoi tiet va vung dia ly).
- **Cac bang Dimension**:
  - `dim_time`: Cac chieu thoi gian (nam, quy, thang, ngay, gio, thu, mua).
  - `dim_location`: Tram do, toa do vi do, kinh do, thanh pho, quoc gia, ma quoc gia (`country_code`), vung mien (`region`), nguon du lieu (`data_source`).
  - `dim_parameter`: Danh muc 6 thong so do luong (PM2.5, PM10, O3, NO2, SO2, CO kem don vi).
- **Bang Fact**:
  - `fact_measurement`: Luu tru gia tri do, chi so AQI, phan cap o nhiem, thoi tiet (`temperature`, `humidity`), co danh dau bat thuong (`is_anomaly`), diem bat thuong (`anomaly_score`), phuong phap (`anomaly_method`).
- **Cac bang ML & Views**:
  - `ml_station_cluster_result`: Ket qua phan cum K-Means tram do theo Silhouette Score toi uu.
  - `ml_pollution_pattern`: Ket qua khai pha mau gio, ngay va dot o nhiem keo dai.
  - Cac Views SQL: `vw_fact_enriched`, `vw_kpi_overview`, `vw_pollution_category_dist`, `vw_country_comparison`, `vw_region_comparison`, `vw_station_map`, `vw_station_ranking`, `vw_anomaly_formatted`, `vw_ml_station_clusters`...

---

## 7. Chay kiem thu (Unit Tests)

Chay toan bo 43 bai kiem thu don vi cho ca tang ETL, Cau hinh Do thi, Client Thoi tiet, Schema DWH va Machine Learning:
```bash
python -m unittest discover tests
```

---

## 8. Cau truc thu muc ma nguon

```
OpenAQ-Project-Unified/
|-- config/
|   |-- cities.yaml                # Danh muc 20 thanh pho, 52 tram quan trac thuc te
|   `-- backfill_checkpoint.json   # Checkpoint luu trang thai thu thap 30 ngay
|-- scripts/
|   |-- discover_stations.py       # Script khao sat OpenAQ v3 tim kiem tram thuc te
|   `-- backfill_30d.py            # Script backfill 30 ngay theo chunk kem thoi tiet
|-- dags/                          # Airflow DAGs dinh ky
|   `-- openaq_pipeline_dag.py     # DAG micro-batching theo gio (openaq_etl_hourly_pipeline)
|-- docker/
|   |-- docker-compose.yml         # Cau hinh toan bo containers
|   `-- init-multiple-dbs.sh       # Script khoi tao nhieu database trong Postgres
|-- sql/
|   |-- create_tables.sql          # DDL Star Schema DWH, bang ML va toan bo Views
|   `-- analysis_queries.sql       # Cac cau truy van phan tich chuyen sau
|-- src/
|   |-- extract/                   # OpenAQ API v3 client & WeatherClient (Open-Meteo)
|   |-- transform/                 # 7 buoc lam sach du lieu va tinh AQI US EPA
|   |-- load/                      # Nap du lieu Staging, Dimensions, Fact
|   |-- analysis/                  # Phan he AI/ML: Anomaly Detection, K-Means, Pattern Mining, Forecast
|   |-- dashboard/                 # Web Dashboard Dark Mode (app.py & template.html)
|   |-- utils/                     # Ket noi CSDL, MinIO, cau hinh, ghi log
|   `-- pipeline.py                # File dieu phoi toan bo luong thuc thi
|-- tests/                         # 43 bo kiem thu don vi (Unit Tests cho ETL, Schema & ML)
|-- Implement/                     # Nhat ky va tien do trien khai tung phien
|-- PROJECT_OVERVIEW.md            # Tai lieu tong quan toan bo kien truc du an
|-- requirements.txt               # Danh sach thu vien tong hop
|-- .env.example                   # Mau bien moi truong
`-- README.md                      # Tai lieu huong dan du an
```

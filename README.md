# He thong Data Warehouse va ETL phan tich chat luong khong khi tu OpenAQ

## 1. Gioi thieu de tai
Du an xay dung he thong Data Warehouse va quy trinh ETL nham thu thap, lam sach, tinh toan chi so chat luong khong khi (AQI theo chuan US EPA), luu tru du lieu lich su va phuc vu phan tich chuyen sau (thong ke mo ta, phat hien bat thuong, phan cum tram do, du doan o nhiem khong khi, truc quan hoa tren Power BI va Apache Superset).

Nguon du lieu chinh: OpenAQ REST API v3 (tap trung khu vuc Viet Nam - ma quoc gia VN).

---

## 2. Kien truc tong the

```
[OpenAQ REST API v3]
         |
    (Airflow DAG)
         v
[Amazon S3 / MinIO (Raw JSON)]
         |
    (Transform: 7 buoc lam sach + tinh AQI)
         v
[Amazon S3 / MinIO (Processed Parquet)]
         |
    (Load: Staging -> Dimensions -> Fact)
         v
[Data Warehouse (PostgreSQL - Star Schema)]
         |
    +----+---------------------------+
    |                                |
    v                                v
[Phan tich & Khai pha (ML)]    [Truc quan hoa (Dashboard)]
- Thong ke mo ta               - Power BI (analytics/air_quality_dashboard.pbix)
- Phat hien bat thuong (Z-score) - Apache Superset
- Phan cum K-Means (Silhouette)
- Du doan chuoi thoi gian
- Khai pha mau hinh (Patterns)
```

---

## 3. Mo hinh Data Warehouse (Star Schema)

- Bang Staging:
  - `staging_measurement`: Bang tam tiep nhan toan bo du lieu sau buoc transform de chuan bi nap vao kho du lieu.
- Cac bang Dimension:
  - `dim_time`: Khai thac cac chieu thoi gian (nam, quy, thang, ngay, gio, thu trong tuan, mua).
  - `dim_location`: Thong tin tram do, toa do dia ly (vi do, kinh do), thanh pho, quoc gia, mui gio.
  - `dim_parameter`: Danh muc thong so do luong (PM2.5, PM10, O3, NO2, SO2, CO kem don vi do).
- Bang Fact:
  - `fact_measurement`: Luu tru nong do do luong, chi so AQI tinh toan, phan nhom muc do o nhiem, co danh dau bat thuong (`is_anomaly`), diem bat thuong (`anomaly_score`), phuong phap (`anomaly_method`).
- Cac bang ket qua ML:
  - `ml_station_cluster_result`: Luu ket qua phan cum tram do qua tung dot chay.
  - `ml_forecast_run`: Nhat ky chay huan luyen va danh gia mo hinh du bao.
  - `ml_forecast_prediction`: Luu gia tri du doan tuong lai kem gia tri thuc te.
  - `ml_pattern_mining_result`: Luu thong tin chu ky theo gio, ngay trong tuan va cac dot o nhiem dot bien.

---

## 4. Quy trinh xu ly du lieu (7 buoc Transform)

1. Loai bo trung lap (Remove duplicate): Khu cac ban ghi trung lap tren bo khoa tu nhien (tram do, thong so, thoi diem do).
2. Xu ly gia tri thieu (Handle missing value): Loai bo hoac hieu chinh cac ban ghi thieu moc thoi gian hoac gia tri nong do.
3. Kiem tra tinh hop le (Validate measurement): Loai bo gia tri am, loc cac gia tri do vuot nguong vat ly bat thuong, danh dau cam bien nghi ngo loi.
4. Chuyen doi kieu du lieu (Convert datatype): Ep kieu chuan xac cho moc thoi gian (timestamp), so thuc (float), ma dinh danh (integer).
5. Chuan hoa vi tri (Normalize location): Chuan hoa ten thanh pho, quoc gia, kiem tra tinh hop le cua toa do dia ly (vi do [-90, 90], kinh do [-180, 180]).
6. Dong bo mui gio (Convert timezone): Luu tru moc thoi gian chuan UTC va tinh toan thoi gian dia phuong (`Asia/Ho_Chi_Minh`).
7. Tinh toan chi so AQI va phan nhom (Calculate AQI / Category): Ap dung cong thuc noi suy tuyen tinh chuan US EPA cho tung chat do va phan nhom chat luong khong khi (Tot, Trung binh, Kem, Xau, Rat xau, Nguy hai).

---

## 5. Huong dan cai dat va van hanh

### 5.1 Khoi dong ha tang dich vu (Docker Compose)

Khoi dong dong thoi MinIO, PostgreSQL, Airflow va Superset bang lenh:

```bash
docker compose -f docker/docker-compose.yml up -d
```

Thong tin cong ket noi cac dich vu:
- MinIO S3 API: http://localhost:9000 (Tai khoan/Mat khau: minioadmin / minioadmin)
- MinIO Web Console: http://localhost:9001
- Airflow Webserver: http://localhost:8082 (Tai khoan/Mat khau: airflow / airflow)
- PostgreSQL Data Warehouse: localhost:5432 (Co so du lieu: openaq_dw / airflow_db, Tai khoan/Mat khau: postgres / postgres)
- Apache Superset: http://localhost:8088 (Tai khoan/Mat khau: admin / admin)

### 5.2 Cai dat thu vien Python moi truong cuc bo

```bash
pip install -r requirements.txt
```

### 5.3 Chay kiem thu toan bo duong ong ETL va ML tu Terminal

```bash
python -m src.pipeline
```

Lenh tren se tu dong thuc thi:
- Phase 1: Thu thap du lieu OpenAQ (Extract) va ghi JSON len MinIO Raw.
- Phase 2: Xu ly 7 buoc (Transform) va ghi Parquet len MinIO Processed.
- Phase 3: Nap du lieu vao Data Warehouse (Load vao Staging -> Dimension -> Fact).
- Phase 4: Chay pipeline ML Analytics (Phat hien bat thuong, Phan cum K-Means, Du bao PM2.5, Luu ket qua vao CSDL).

### 5.4 Chay kiem thu bo Unit Tests

```bash
python -m unittest discover tests
```

### 5.5 Truc quan hoa Dashboard

1. **Power BI**:
   - Mo file `analytics/air_quality_dashboard.pbix` bang Power BI Desktop.
   - Ket noi toi co so du lieu PostgreSQL DWH (`localhost:5432`, database: `openaq_dw`).
   - Tham khao cac cau truy van mau trong file `analytics/queries.sql`.

2. **Apache Superset**:
   - Truy cap http://localhost:8088.
   - Ket noi Database DWH voi connection string:
     `postgresql://postgres:postgres@postgres-dwh:5432/openaq_dw`
   - Su dung cac query trong `sql/analysis_queries.sql` de tao bieu do.

---

## 6. Cau truc thu muc du an

```
OpenAQ-Project-Unified/
|-- analytics/                     # Tai nguyen truc quan hoa Dashboard
|   |-- air_quality_dashboard.pbix # File Dashboard Power BI
|   `-- queries.sql                # Truy van SQL phuc vu bao cao
|-- dags/                          # Airflow DAGs dinh ky
|   `-- openaq_pipeline_dag.py     # DAG dieu phoi Extract -> Transform -> Load -> ML
|-- docker/
|   |-- docker-compose.yml         # Cau hinh container (MinIO, Postgres, Airflow, Superset)
|   `-- init-multiple-dbs.sh       # Script khoi tao nhieu database trong Postgres
|-- sql/
|   |-- create_tables.sql          # DDL khoi tao Star Schema DWH va cac bang ML
|   |-- analysis_queries.sql       # Cac cau truy van phan tich cho Superset
|   `-- migrations/                # Cac script nang cap co so du lieu
|       |-- 001_add_anomaly_metadata.sql
|       `-- 002_add_ml_result_tables.sql
|-- src/
|   |-- extract/                   # Thu thap OpenAQ API va luu tru MinIO/S3 Raw
|   |-- transform/                 # 7 buoc lam sach du lieu va tinh AQI (US EPA)
|   |-- load/                      # Nap du lieu Staging, Dimension, Fact
|   |-- analysis/                  # Phat hien bat thuong, Phan cum, Du bao, Luu ket qua
|   |   |-- analytics_runner.py    # Dieu phoi toan bo tien trinh ML
|   |   |-- anomaly_detection.py   # Z-score, IQR, Rolling MAD
|   |   |-- clustering.py          # K-Means danh gia Silhouette
|   |   |-- forecasting.py         # Du bao chuoi thoi gian (Lag, Rolling, RF)
|   |   |-- pattern_mining.py      # Khai pha mau hinh gio va chu ky tuan
|   |   |-- result_store.py        # Luu ket qua ML vao PostgreSQL
|   |   |-- statistics.py          # Thong ke mo ta va xep hang tram
|   |   `-- data_validation.py     # Kiem tra chat luong du lieu dau vao cho ML
|   `-- utils/                     # Ket noi CSDL, MinIO, cau hinh, ghi nhat ky
|-- tests/                         # Bo kiem thu don vi (Unit Tests cho ETL & ML)
|-- Implement/                     # Tai lieu tien do va nhat ky cac phien lam viec
|-- requirements.txt               # Danh sach thu vien tong hop
|-- .env.example                   # Mau bien moi truong
|-- .env                           # File bien moi truong thuc te
`-- README.md                      # Tai lieu huong dan du an
```

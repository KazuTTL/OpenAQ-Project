# Hệ thống Data Warehouse và ETL phân tích chất lượng không khí từ OpenAQ

## 1. Giới thiệu đề tài
Dự án xây dựng hệ thống Data Warehouse và quy trình ETL nhằm thu thập, làm sạch, tính toán chỉ số chất lượng không khí (AQI theo chuẩn US EPA), lưu trữ dữ liệu lịch sử và phục vụ phân tích chuyên sâu (thống kê mô tả, phát hiện bất thường, phân cụm trạm đo, dự đoán ô nhiễm không khí).

Nguồn dữ liệu chính: OpenAQ REST API v3 (tập trung phạm vi khu vực Việt Nam - mã quốc gia VN).

---

## 2. Kiến trúc tổng thể

```
[OpenAQ REST API v3]
         |
    (Airflow DAG)
         v
[Amazon S3 / MinIO (Raw JSON)]
         |
    (Transform: 7 bước làm sạch + tính AQI)
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
[Phân tích & Khai phá]       [Trực quan hóa Dashboard]
- Thống kê mô tả              - Apache Superset
- Phát hiện bất thường        - Power BI Desktop
- Phân cụm K-Means
- Dự đoán Random Forest
```

---

## 3. Mô hình Data Warehouse (Star Schema)

- Bảng Staging:
  - `staging_measurement`: Bảng tạm tiếp nhận toàn bộ dữ liệu sau bước transform để chuẩn bị nạp vào kho dữ liệu.
- Các bảng Dimension:
  - `dim_time`: Khai thác các chiều thời gian (năm, quý, tháng, ngày, giờ, thứ trong tuần, mùa).
  - `dim_location`: Thông tin trạm đo, tọa độ địa lý (vĩ độ, kinh độ), thành phố, quốc gia, múi giờ.
  - `dim_parameter`: Danh mục thông số đo lường (PM2.5, PM10, O3, NO2, SO2, CO kèm đơn vị đo).
- Bảng Fact:
  - `fact_measurement`: Lưu trữ nồng độ đo lường, chỉ số AQI tính toán, phân nhóm mức độ ô nhiễm, cờ đánh dấu dữ liệu bất thường (`is_anomaly`).

---

## 4. Quy trình xử lý dữ liệu (7 bước Transform)

1. Loại bỏ trùng lặp (Remove duplicate): Khử các bản ghi trùng lặp trên bộ khóa tự nhiên (trạm đo, thông số, thời điểm đo).
2. Xử lý giá trị thiếu (Handle missing value): Loại bỏ hoặc hiệu chỉnh các bản ghi thiếu mốc thời gian hoặc giá trị nồng độ.
3. Kiểm tra tính hợp lệ (Validate measurement): Loại bỏ giá trị âm, lọc các giá trị đo vượt ngưỡng vật lý bất thường, đánh dấu cảm biến nghi ngờ lỗi.
4. Chuyển đổi kiểu dữ liệu (Convert datatype): Ép kiểu chuẩn xác cho mốc thời gian (timestamp), số thực (float), mã định danh (integer).
5. Chuẩn hóa vị trí (Normalize location): Chuẩn hóa tên thành phố, quốc gia, kiểm tra tính hợp lệ của tọa độ địa lý (vĩ độ [-90, 90], kinh độ [-180, 180]).
6. Đồng bộ múi giờ (Convert timezone): Lưu trữ mốc thời gian chuẩn UTC và tính toán thời gian địa phương (`Asia/Ho_Chi_Minh`).
7. Tính toán chỉ số AQI và phân nhóm (Calculate AQI / Category): Áp dụng công thức nội suy tuyến tính chuẩn US EPA cho từng chất đo và phân nhóm chất lượng không khí (Tốt, Trung bình, Kém, Xấu, Rất xấu, Nguy hại).

---

## 5. Hướng dẫn cài đặt và vận hành

### 5.1 Khởi động hạ tầng dịch vụ (Docker Compose)

Khởi động đồng thời MinIO, PostgreSQL, Airflow và Superset bằng lệnh:

```bash
docker compose -f docker/docker-compose.yml up -d
```

Thông tin cổng kết nối các dịch vụ:
- MinIO S3 API: http://localhost:9000 (Tài khoản/Mật khẩu: minioadmin / minioadmin)
- MinIO Web Console: http://localhost:9001
- Airflow Webserver: http://localhost:8082 (Tài khoản/Mật khẩu: airflow / airflow)
- PostgreSQL Data Warehouse: localhost:5432 (Cơ sở dữ liệu: openaq_dw / airflow_db, Tài khoản/Mật khẩu: postgres / postgres)
- Apache Superset: http://localhost:8088 (Tài khoản/Mật khẩu: admin / admin)

### 5.2 Cài đặt thư viện Python môi trường cục bộ

```bash
pip install -r requirements.txt
```

### 5.3 Chạy kiểm thử đường ống ETL thủ công từ Terminal

```bash
python -m src.pipeline
```

### 5.4 Chạy kiểm thử bộ Unit Test

```bash
python -m unittest discover tests
```

### 5.5 Thực thi các mô-đun phân tích và khai phá dữ liệu

```bash
# 1. Thống kê mô tả và xếp hạng trạm ô nhiễm
python -c "from src.analysis.statistics import AirQualityStatistics; print(AirQualityStatistics.get_summary_statistics())"

# 2. Phát hiện bất thường bằng thuật toán Z-score
python -c "from src.analysis.anomaly_detection import AnomalyDetector; print(AnomalyDetector.detect_zscore_anomalies())"

# 3. Phân cụm đặc trưng trạm đo bằng K-Means
python -c "from src.analysis.clustering import StationClustering; print(StationClustering.run_kmeans())"

# 4. Huấn luyện mô hình dự đoán nồng độ PM2.5 (Random Forest)
python -c "from src.analysis.forecasting import AirQualityForecaster; print(AirQualityForecaster.train_and_evaluate())"
```

---

## 6. Cấu trúc thư mục dự án

```
OpenAQ_project/
|-- dags/                          # Airflow DAGs định kỳ
|   `-- openaq_pipeline_dag.py     # DAG điều phối toàn bộ luồng ETL
|-- docker/
|   |-- docker-compose.yml         # Cấu hình container (MinIO, Postgres, Airflow, Superset)
|   `-- init-multiple-dbs.sh       # Script khởi tạo nhiều database trong Postgres
|-- sql/
|   |-- create_tables.sql          # DDL khởi tạo cấu trúc Star Schema DWH
|   `-- analysis_queries.sql       # Các câu truy vấn phục vụ Dashboard báo cáo
|-- src/
|   |-- extract/                   # Mô-đun thu thập OpenAQ API và lưu trữ MinIO/S3
|   |-- transform/                 # 7 bước làm sạch dữ liệu và tính AQI
|   |-- load/                      # Mô-đun nạp dữ liệu Staging, Dimension, Fact
|   |-- analysis/                  # Thống kê, phát hiện bất thường, phân cụm, dự đoán
|   `-- utils/                     # Tiện ích kết nối CSDL, MinIO, cấu hình, ghi nhật ký
|-- tests/                         # Bộ kiểm thử đơn vị (Unit Tests)
|-- requirements.txt               # Danh sách thư viện phụ thuộc
|-- .env.example                   # Mẫu cấu hình biến môi trường
|-- .env                           # File cấu hình môi trường thực tế
`-- README.md                      # Tài liệu hướng dẫn dự án
Hãy tạo một file md chứa nội dung của toàn bộ phiên chat này, để lần làm việc sau AI chỉ cần đọc lại là hiểu. File md tên là ngày tháng cụ thể trong 

Implement
 
```

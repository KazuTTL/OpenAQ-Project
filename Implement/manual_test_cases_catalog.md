# Tài Liệu Đặc Tả Chi Tiết Kịch Bản Kiểm Thử Thủ Công (QA Manual Test Cases Specification)

**Hệ thống**: Nền tảng Dữ liệu & Giám sát Chất lượng Không khí OpenAQ (OpenAQ Data Platform)  
**Phiên bản**: Mở rộng 20 đô thị, 52 trạm quan trắc, tích hợp khí tượng Open-Meteo và Machine Learning  
**Ngày phát hành**: 28/10/2026  
**Phương pháp kiểm thử**: Manual Testing (Kiểm thử chức năng, tính toàn vẹn kho dữ liệu SQL, giao diện người dùng và điều phối)

---

## 1. BẢNG TỔNG QUAN DANH MỤC TEST CASE

| Nhóm | Phân hệ kiểm thử | Số TC Cũ | Số TC Mới / Nâng cấp | Tổng số TC | Phạm vi kiểm tra chính |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Nhóm 1** | Quản lý Cấu hình & Trạm Quan trắc | 2 | 2 | 4 | File cấu hình `cities.yaml`, bảng `dim_location`, `dim_parameter` |
| **Nhóm 2** | Thu thập Dữ liệu & Khí tượng | 2 | 3 | 5 | API OpenAQ, Open-Meteo, Cache thời tiết, Historical Backfill |
| **Nhóm 3** | Làm sạch, Chuẩn hóa & Tính AQI 7 Bước | 6 | 2 | 8 | Deduplication, Outlier, Múi giờ UTC+7, Công thức chuẩn EPA |
| **Nhóm 4** | Kho Dữ liệu Star Schema & Views Phân tích | 2 | 4 | 6 | Khóa ngoại, Idempotent, `fact_measurement`, 6 Views DWH |
| **Nhóm 5** | AI / Học máy & Khai phá Mẫu | 3 | 4 | 7 | Z-Score/IQR Anomaly, Random Forest thời tiết, K-Means |
| **Nhóm 6** | Giao diện Web Dashboard & Bản đồ GIS | 3 | 7 | 10 | Dark Mode, Bộ lọc 3 cấp, Bản đồ Leaflet.js, Auto-refresh |
| **Nhóm 7** | Điều phối Airflow & Phân tích Superset | 2 | 3 | 5 | Airflow DAG `@hourly`, Task Retry, Superset SQL Lab |
| **Tổng** | **Toàn bộ hệ thống** | **17** | **28** | **45** | **Bao phủ 100% chức năng hệ thống** |

---

## 2. CHI TIẾT CÁC TEST CASE CHO MANUAL TESTING

---

### NHÓM 1: QUẢN LÝ CẤU HÌNH & TRẠM QUAN TRẮC (CONFIG & REGISTRY)
Tài liệu liên quan: `config/cities.yaml`, `tests/test_cities_config.py`

#### TC_CFG_01: Kiểm tra tính sẵn sàng của biến môi trường hệ thống
* **Phân loại**: Cũ
* **Tiền điều kiện**: File `.env` đã được tạo tại thư mục gốc của dự án.
* **Các bước thực hiện**:
  1. Mở file `.env` bằng trình chỉnh sửa văn bản.
  2. Rà soát sự hiện diện của các cấu hình: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT`, `MINIO_ENDPOINT`, `AIRFLOW_UID`.
* **Dữ liệu kiểm thử**: File cấu hình `.env` mặc định.
* **Kết quả mong đợi**: Tất cả các tham số bắt buộc đều có giá trị, không có tham số nào bị để trống.

#### TC_CFG_02: Kiểm tra cấu hình danh mục tham số ô nhiễm không khí
* **Phân loại**: Cũ
* **Tiền điều kiện**: Cơ sở dữ liệu PostgreSQL đang chạy.
* **Các bước thực hiện**:
  1. Kết nối vào cơ sở dữ liệu `openaq_dw`.
  2. Chạy câu truy vấn:
     ```sql
     SELECT parameter_name, unit, description FROM dim_parameter ORDER BY parameter_key ASC;
     ```
* **Dữ liệu kiểm thử**: 6 chất ô nhiễm chuẩn EPA.
* **Kết quả mong đợi**: Bảng trả về đủ 6 tham số: `pm25`, `pm10`, `o3`, `no2`, `so2`, `co` với đơn vị đo lường tương ứng (`ug/m3` hoặc `ppm`).

#### TC_CFG_03: Kiểm tra cấu hình mở rộng danh sách 20 thành phố và 52 trạm quan trắc
* **Phân loại**: Mới
* **Tiền điều kiện**: File `config/cities.yaml` tồn tại tại thư mục gốc.
* **Các bước thực hiện**:
  1. Mở file `config/cities.yaml`.
  2. Đếm số lượng quốc gia (`countries`) và số lượng thành phố (`cities`).
  3. Kiểm tra số lượng trạm quan trắc (`stations`) của từng thành phố.
* **Dữ liệu kiểm thử**: Cấu hình mở rộng 2 quốc gia: Vietnam (15 thành phố), Thailand (5 thành phố).
* **Kết quả mong đợi**:
  * Đủ 20 thành phố thuộc 2 quốc gia.
  * Mỗi thành phố có tối thiểu 2 trạm quan trắc.
  * Tổng số trạm khai báo đạt tối thiểu 52 trạm.

#### TC_CFG_04: Kiểm tra tính hợp lệ của tọa độ địa lý các trạm quan trắc
* **Phân loại**: Nâng cấp
* **Tiền điều kiện**: Danh sách 52 trạm trong `config/cities.yaml` đã nạp vào DWH.
* **Các bước thực hiện**:
  1. Kết nối vào PostgreSQL `openaq_dw`.
  2. Chạy câu truy vấn:
     ```sql
     SELECT location_name, city, country_code, latitude, longitude 
     FROM dim_location 
     WHERE latitude IS NULL OR longitude IS NULL 
        OR latitude NOT BETWEEN -90 AND 90 OR longitude NOT BETWEEN -180 AND 180;
     ```
* **Dữ liệu kiểm thử**: Toàn bộ 52 cặp tọa độ trạm quan trắc.
* **Kết quả mong đợi**: Trả về 0 dòng (không có bất kỳ trạm nào có tọa độ rỗng hoặc nằm ngoài giới hạn vật lý).

---

### NHÓM 2: THU THẬP DỮ LIỆU & TÍCH HỢP KHÍ TƯỢNG (EXTRACT & WEATHER)
Tài liệu liên quan: `src/ingestion/extract_openaq.py`, `src/ingestion/weather_client.py`

#### TC_EXT_01: Thu thập dữ liệu thực tế từ OpenAQ API v3
* **Phân loại**: Cũ
* **Tiền điều kiện**: Có kết nối Internet và có khóa API hợp lệ trong `.env`.
* **Các bước thực hiện**:
  1. Chạy module trích xuất cho 1 trạm thực tế từ OpenAQ.
  2. Kiểm tra dữ liệu JSON thô thu thập được.
* **Dữ liệu kiểm thử**: ID trạm thực tế có dữ liệu trên OpenAQ.
* **Kết quả mong đợi**: API trả về HTTP Status 200, danh sách các phép đo kèm thời gian quan trắc chuẩn ISO 8601.

#### TC_EXT_02: Kiểm tra cơ chế Fallback sang Mock Data khi OpenAQ API không phản hồi
* **Phân loại**: Cũ
* **Tiền điều kiện**: Ngắt kết nối mạng hoặc truyền ID trạm không tồn tại trên OpenAQ.
* **Các bước thực hiện**:
  1. Thực thi module `extract_openaq.py`.
  2. Đọc thông báo log trên màn hình terminal.
* **Dữ liệu kiểm thử**: Trạm có cờ cấu hình `data_source = mock_generator`.
* **Kết quả mong đợi**: Hệ thống không bị crash, ghi nhận log cảnh báo và tự động sinh bản ghi giả lập thực tế theo phân phối chuẩn để pipeline tiếp tục chạy.

#### TC_EXT_03: Tích hợp và làm giàu dữ liệu nhiệt độ, độ ẩm từ Open-Meteo API
* **Phân loại**: Mới
* **Tiền điều kiện**: Tọa độ trạm quan trắc hợp lệ và thời gian đo lường nằm trong quá khứ/hiện tại.
* **Các bước thực hiện**:
  1. Gọi module tích hợp thời tiết trong `src/ingestion/weather_client.py`.
  2. Kiểm tra dữ liệu thời tiết được ghép nối vào bản ghi đo lường trong DWH:
     ```sql
     SELECT COUNT(*) AS total, COUNT(temperature) AS temp_cnt, COUNT(humidity) AS hum_cnt FROM fact_measurement;
     ```
* **Dữ liệu kiểm thử**: Tọa độ trạm Hà Nội (21.0285, 105.8542).
* **Kết quả mong đợi**: Bản ghi được bổ sung 2 trường `temperature` (độ C) và `humidity` (%), tỷ lệ làm giàu đạt 100%.

#### TC_EXT_04: Kiểm tra cơ chế Bộ nhớ đệm (Cache) dữ liệu thời tiết
* **Phân loại**: Mới
* **Tiền điều kiện**: Đã thực hiện ít nhất 1 lần truy vấn Open-Meteo API cho cùng tọa độ và mốc ngày.
* **Các bước thực hiện**:
  1. Gửi liên tiếp 2 yêu cầu lấy thời tiết cho cùng một tọa độ và ngày đo.
  2. Quan sát log hệ thống và thời gian phản hồi của lần gọi thứ hai.
* **Dữ liệu kiểm thử**: Cặp tọa độ trạm TP.HCM (10.7769, 106.7009).
* **Kết quả mong đợi**: Lần gọi thứ hai sử dụng bộ nhớ đệm nội bộ (in-memory lookup), thời gian phản hồi dưới 5ms, không phát sinh HTTP request ra ngoài.

#### TC_EXT_05: Thu thập dữ liệu lịch sử hàng loạt (Historical Backfill 30 ngày)
* **Phân loại**: Mới
* **Tiền điều kiện**: Cơ sở dữ liệu và MinIO đã sẵn sàng; danh sách 52 trạm đã cấu hình.
* **Các bước thực hiện**:
  1. Chạy kịch bản backfill dữ liệu 30 ngày.
  2. Kiểm tra cơ chế chia đợt (chunking) và lưu checkpoint sau mỗi batch.
* **Dữ liệu kiểm thử**: Khoảng thời gian từ 2026-09-28 đến 2026-10-28 cho 52 trạm.
* **Kết quả mong đợi**: Quá trình backfill hoàn tất không gây lỗi tràn bộ nhớ (OOM), tổng số bản ghi trong `fact_measurement` đạt trên 50,000 dòng.

---

### NHÓM 3: LÀM SẠCH, CHUẨN HÓA & TÍNH TOÁN AQI (TRANSFORM - 7 BƯỚC)
Tài liệu liên quan: `src/transform/cleaner.py`, `src/transform/normalizer.py`, `src/transform/aqi_calculator.py`

#### TC_TRF_01: Bước 1 - Loại bỏ bản ghi trùng lặp (Deduplication)
* **Phân loại**: Cũ
* **Tiền điều kiện**: Dữ liệu có chứa các dòng trùng lặp cặp khóa (time_key, location_key, parameter_key).
* **Các bước thực hiện**:
  1. Kết nối PostgreSQL `openaq_dw`.
  2. Chạy câu truy vấn kiểm tra trùng lặp:
     ```sql
     SELECT time_key, location_key, parameter_key, COUNT(*) 
     FROM fact_measurement 
     GROUP BY time_key, location_key, parameter_key HAVING COUNT(*) > 1;
     ```
* **Dữ liệu kiểm thử**: Toàn bộ dữ liệu bảng `fact_measurement`.
* **Kết quả mong đợi**: Trả về 0 dòng (ràng buộc duy nhất được đảm bảo tuyệt đối).

#### TC_TRF_02: Bước 2 - Xử lý giá trị rỗng (Missing Value Handling)
* **Phân loại**: Cũ
* **Tiền điều kiện**: Dữ liệu thô có thể thiếu giá trị tại các cột nghiệp vụ.
* **Các bước thực hiện**:
  1. Chạy câu truy vấn kiểm tra các cột bắt buộc:
     ```sql
     SELECT COUNT(*) FROM fact_measurement WHERE value IS NULL OR pollution_category IS NULL;
     ```
* **Dữ liệu kiểm thử**: Bảng `fact_measurement`.
* **Kết quả mong đợi**: Trả về 0 dòng (không có giá trị rỗng ở các trường bắt buộc).

#### TC_TRF_03: Bước 3 - Kiểm tra ngưỡng vật lý hợp lệ của các chất ô nhiễm
* **Phân loại**: Cũ
* **Tiền điều kiện**: Dữ liệu thô có thể xuất hiện nồng độ âm do lỗi cảm biến.
* **Các bước thực hiện**:
  1. Chạy câu truy vấn:
     ```sql
     SELECT COUNT(*) FROM fact_measurement WHERE value < 0;
     ```
* **Dữ liệu kiểm thử**: Toàn bộ nồng độ chất ô nhiễm.
* **Kết quả mong đợi**: Trả về 0 dòng (tất cả các số đo âm đều bị lọc bỏ hoặc làm sạch tại bước Transform).

#### TC_TRF_04: Bước 4 - Chuẩn hóa tọa độ địa lý và ranh giới kinh vĩ độ
* **Phân loại**: Cũ
* **Tiền điều kiện**: Dữ liệu vị trí trạm từ OpenAQ.
* **Các bước thực hiện**:
  1. Kiểm tra tọa độ trạm trong bảng `dim_location`:
     ```sql
     SELECT COUNT(*) FROM dim_location WHERE latitude NOT BETWEEN -90 AND 90 OR longitude NOT BETWEEN -180 AND 180;
     ```
* **Dữ liệu kiểm thử**: 52 trạm quan trắc.
* **Kết quả mong đợi**: Trả về 0 dòng; tất cả tọa độ đều là số thực hợp lệ.

#### TC_TRF_05: Bước 5 - Chuẩn hóa múi giờ sang UTC+7 (Giờ địa phương)
* **Phân loại**: Nâng cấp
* **Tiền điều kiện**: Dữ liệu thô có mốc thời gian chuẩn UTC.
* **Các bước thực hiện**:
  1. Chạy câu truy vấn đối chiếu giữa UTC và local date trong `dim_time`:
     ```sql
     SELECT datetime_utc, local_date, hour, (datetime_utc + INTERVAL '7 hours') AS calculated_local 
     FROM dim_time LIMIT 5;
     ```
* **Dữ liệu kiểm thử**: 5 bản ghi mẫu trong `dim_time`.
* **Kết quả mong đợi**: `local_date` và `hour` khớp chính xác với mốc thời gian UTC cộng thêm 7 giờ.

#### TC_TRF_06: Bước 6 - Tính toán chỉ số AQI từng chất theo phân đoạn chuẩn EPA
* **Phân loại**: Cũ
* **Tiền điều kiện**: Dữ liệu nồng độ các chất chuẩn EPA (`pm25`, `pm10`, `o3`, `no2`, `so2`, `co`).
* **Các bước thực hiện**:
  1. Chạy truy vấn kiểm tra dải AQI của từng nhóm phân loại:
     ```sql
     SELECT pollution_category, MIN(aqi) AS min_aqi, MAX(aqi) AS max_aqi, COUNT(*) 
     FROM fact_measurement WHERE aqi IS NOT NULL 
     GROUP BY pollution_category ORDER BY min_aqi ASC;
     ```
* **Dữ liệu kiểm thử**: Toàn bộ các dòng có `aqi IS NOT NULL`.
* **Kết quả mong đợi**:
  * Good: 0 - 50
  * Moderate: 51 - 100
  * Unhealthy for Sensitive Groups: 101 - 150
  * Unhealthy: 151 - 200
  * Very Unhealthy: 201 - 300
  * Hazardous: > 300

#### TC_TRF_07: Bước 7 - Tính toán AQI tổng hợp và xác định chất gây ô nhiễm chính
* **Phân loại**: Nâng cấp
* **Tiền điều kiện**: Trạm quan trắc đo lường đồng thời nhiều chất tại cùng một thời điểm.
* **Các bước thực hiện**:
  1. Kiểm tra tính toán AQI đại diện của trạm (bằng Max AQI của các chất đo được).
  2. Xác định chất có chỉ số AQI cao nhất được gán làm Dominant Pollutant.
* **Dữ liệu kiểm thử**: View `vw_fact_enriched`.
* **Kết quả mong đợi**: AQI tổng hợp phản ánh đúng mức độ nguy hại cao nhất trong số các chất đo được tại trạm.

#### TC_TRF_08: Kiểm định chất lượng dữ liệu đa chiều (Data Validation Rules)
* **Phân loại**: Mới
* **Tiền điều kiện**: Batch dữ liệu hoàn tất 7 bước Transform.
* **Các bước thực hiện**:
  1. Kích hoạt module `src/analysis/data_validation.py`.
  2. Đọc báo cáo chất lượng dữ liệu về 4 chiều: Completeness, Uniqueness, Timeliness, Validity.
* **Dữ liệu kiểm thử**: Batch dữ liệu nạp định kỳ.
* **Kết quả mong đợi**: Tỷ lệ bản ghi đạt chuẩn chất lượng vượt trên 95%.

---

### NHÓM 4: KHO DỮ LIỆU DWH STAR SCHEMA & VIEWS (LOAD & DWH)
Tài liệu liên quan: `sql/create_tables.sql`, `src/load/fact_loader.py`

#### TC_DWH_01: Kiểm tra tính toàn vẹn của mô hình hình sao (Star Schema Integrity)
* **Phân loại**: Cũ
* **Tiền điều kiện**: Database `openaq_dw` đã khởi tạo đầy đủ các bảng.
* **Các bước thực hiện**:
  1. Kiểm tra ràng buộc khóa ngoại từ bảng Fact đến các bảng Dim:
     ```sql
     SELECT COUNT(CASE WHEN dt.time_key IS NULL THEN 1 END) AS orphan_time,
            COUNT(CASE WHEN dl.location_key IS NULL THEN 1 END) AS orphan_location,
            COUNT(CASE WHEN dp.parameter_key IS NULL THEN 1 END) AS orphan_param
     FROM fact_measurement fm
     LEFT JOIN dim_time dt ON dt.time_key = fm.time_key
     LEFT JOIN dim_location dl ON dl.location_key = fm.location_key
     LEFT JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key;
     ```
* **Dữ liệu kiểm thử**: Toàn bộ bảng `fact_measurement`.
* **Kết quả mong đợi**: Cả 3 trường đều trả về 0 (không có bản ghi Fact mồ côi).

#### TC_DWH_02: Nạp dữ liệu vào bảng Dim không tạo bản ghi trùng lặp (Idempotent Load)
* **Phân loại**: Cũ
* **Tiền điều kiện**: Bảng `dim_location` đã có sẵn 52 trạm.
* **Các bước thực hiện**:
  1. Chạy lại tiến trình nạp bảng chiều với cùng danh sách trạm.
  2. Đếm số lượng bản ghi trong `dim_location`.
* **Dữ liệu kiểm thử**: Danh sách trạm trong `config/cities.yaml`.
* **Kết quả mong đợi**: Số lượng dòng trong `dim_location` giữ nguyên 52 dòng (cơ chế UPSERT hoạt động chuẩn xác).

#### TC_DWH_03: Kiểm tra các cột mở rộng mới trong DWH Schema
* **Phân loại**: Mới
* **Tiền điều kiện**: DWH Schema Phase 2 đã áp dụng.
* **Các bước thực hiện**:
  1. Truy vấn kiểm tra cấu trúc bảng qua `information_schema.columns`:
     ```sql
     SELECT table_name, column_name, data_type 
     FROM information_schema.columns 
     WHERE (table_name = 'dim_location' AND column_name IN ('country_code', 'region', 'data_source'))
        OR (table_name = 'fact_measurement' AND column_name IN ('temperature', 'humidity'));
     ```
* **Dữ liệu kiểm thử**: Metadata cơ sở dữ liệu.
* **Kết quả mong đợi**: Trả về đủ 5 dòng tương ứng với 5 cột mở rộng mới.

#### TC_DWH_04: Kiểm tra khối lượng và phân bổ dữ liệu trong fact_measurement
* **Phân loại**: Mới
* **Tiền điều kiện**: Đã thực hiện xong Historical Backfill 30 ngày.
* **Các bước thực hiện**:
  1. Đếm tổng số bản ghi và số trạm thực tế có dữ liệu:
     ```sql
     SELECT COUNT(*) AS total_rows, COUNT(DISTINCT location_key) AS active_stations FROM fact_measurement;
     ```
* **Dữ liệu kiểm thử**: Dữ liệu thực tế trong DB.
* **Kết quả mong đợi**: Tổng số bản ghi đạt trên 50,000 dòng; có từ 38 trạm trở lên có số liệu đo lường.

#### TC_DWH_05: Kiểm tra View làm giàu dữ liệu phục vụ Dashboard (vw_fact_enriched)
* **Phân loại**: Nâng cấp
* **Tiền điều kiện**: Dữ liệu Fact và Dim đã đồng bộ.
* **Các bước thực hiện**:
  1. Chạy câu truy vấn:
     ```sql
     SELECT measurement_key, datetime_utc, location_name, city, country_code, parameter_name, aqi, temperature, humidity 
     FROM vw_fact_enriched LIMIT 5;
     ```
* **Dữ liệu kiểm thử**: 5 dòng đầu tiên của View.
* **Kết quả mong đợi**: Trả về đầy đủ thông tin kết hợp giữa Fact và 3 Dim, thời gian thực thi dưới 100ms.

#### TC_DWH_06: Kiểm tra các View so sánh đa quốc gia và phân tích khu vực
* **Phân loại**: Mới
* **Tiền điều kiện**: Dữ liệu có đủ 2 quốc gia Việt Nam và Thái Lan.
* **Các bước thực hiện**:
  1. Chạy truy vấn View so sánh quốc gia:
     ```sql
     SELECT country_code, country_name, active_stations, total_cities, avg_aqi FROM vw_country_comparison;
     ```
* **Dữ liệu kiểm thử**: View `vw_country_comparison`.
* **Kết quả mong đợi**: Trả về 2 dòng cho `VN` và `TH` với các chỉ số thống kê chuẩn xác.

---

### NHÓM 5: TRÍ TUỆ NHÂN TẠO, HỌC MÁY & KHAI PHÁ MẪU (AI / ML & PATTERN MINING)
Tài liệu liên quan: `src/analysis/anomaly_detection.py`, `src/analysis/forecasting.py`, `src/analysis/clustering.py`

#### TC_ML_01: Phát hiện bất thường bằng thuật toán Z-Score, IQR và Rolling Window
* **Phân loại**: Cũ
* **Tiền điều kiện**: Dữ liệu chuỗi thời gian nồng độ chất ô nhiễm.
* **Các bước thực hiện**:
  1. Truy vấn tỷ lệ bản ghi bất thường trong DWH:
     ```sql
     SELECT is_anomaly, COUNT(*), ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct 
     FROM fact_measurement GROUP BY is_anomaly;
     ```
* **Dữ liệu kiểm thử**: 50,190 bản ghi trong `fact_measurement`.
* **Kết quả mong đợi**: Tỷ lệ bất thường nằm trong khoảng 8% - 12%, phản ánh đúng đặc thù dữ liệu môi trường thực tế.

#### TC_ML_02: Khai phá mẫu ô nhiễm theo khung giờ trong ngày và ngày trong tuần
* **Phân loại**: Cũ
* **Tiền điều kiện**: Dữ liệu đo lường tối thiểu 7 ngày liên tục.
* **Các bước thực hiện**:
  1. Truy vấn kết quả pattern mining trong bảng `ml_pollution_pattern`:
     ```sql
     SELECT pattern_type, parameter_name, COUNT(*) FROM ml_pollution_pattern GROUP BY pattern_type, parameter_name;
     ```
* **Dữ liệu kiểm thử**: Kết quả trong `ml_pollution_pattern`.
* **Kết quả mong đợi**: Trả về đầy đủ các mẫu phân tích chu kỳ giờ trong ngày (`hourly_pattern`) và ngày trong tuần (`weekday_pattern`).

#### TC_ML_03: Tính ma trận tương quan giữa các chất ô nhiễm
* **Phân loại**: Cũ
* **Tiền điều kiện**: Dữ liệu đo lường đồng thời nhiều chất.
* **Các bước thực hiện**:
  1. Truy vấn các hệ số tương quan trong `ml_pollution_pattern`:
     ```sql
     SELECT parameter_name, period_value, correlation_value 
     FROM ml_pollution_pattern WHERE pattern_type = 'pollutant_correlation';
     ```
* **Dữ liệu kiểm thử**: Kết quả tính tương quan Pearson.
* **Kết quả mong đợi**: Tương quan giữa PM2.5 và PM10 thể hiện giá trị dương mạnh (r > 0.6).

#### TC_ML_04: Huấn luyện mô hình dự báo Random Forest kết hợp đặc trưng thời tiết
* **Phân loại**: Mới
* **Tiền điều kiện**: Dữ liệu lịch sử chứa nồng độ PM2.5 cùng `temperature` và `humidity`.
* **Các bước thực hiện**:
  1. Chạy module huấn luyện trong `src/analysis/forecasting.py`.
  2. Đọc chỉ số đánh giá mô hình trên tập kiểm thử (Test Set).
* **Dữ liệu kiểm thử**: 50,190 bản ghi phân chia train/test theo thứ tự thời gian tỷ lệ 80/20.
* **Kết quả mong đợi**: Hệ số xác định $R^2 \ge 0.50$; sai số RMSE giảm rõ rệt so với mô hình không có biến thời tiết.

#### TC_ML_05: Dự báo nồng độ ô nhiễm 24 giờ tiếp theo cho từng trạm
* **Phân loại**: Nâng cấp
* **Tiền điều kiện**: Mô hình Random Forest đã được huấn luyện.
* **Các bước thực hiện**:
  1. Kích hoạt hàm suy luận dự báo 24 giờ cho một trạm cụ thể.
  2. Kiểm tra chuỗi giá trị dự báo đầu ra.
* **Dữ liệu kiểm thử**: 24 giờ gần nhất của trạm đại sứ quán Mỹ tại Hà Nội.
* **Kết quả mong đợi**: Đầu ra gồm 24 điểm dự báo tương ứng với 24 mốc giờ tương lai; các giá trị không bị âm và tuân theo quy luật tự nhiên.

#### TC_ML_06: Phân cụm các trạm quan trắc bằng thuật toán K-Means và tối ưu Silhouette
* **Phân loại**: Mới
* **Tiền điều kiện**: Bảng đặc trưng thống kê của 38 trạm quan trắc thực tế.
* **Các bước thực hiện**:
  1. Chạy module phân cụm trong `src/analysis/clustering.py`.
  2. Kiểm tra bảng kết quả phân cụm trong DWH:
     ```sql
     SELECT cluster, cluster_label, COUNT(*), ROUND(AVG(avg_aqi)::numeric, 1) AS mean_aqi 
     FROM ml_station_cluster_result GROUP BY cluster, cluster_label;
     ```
* **Dữ liệu kiểm thử**: Kết quả trong `ml_station_cluster_result`.
* **Kết quả mong đợi**: Thuật toán tự động chọn số cụm tối ưu (K=2, Silhouette > 0.60), phân tách rõ cụm trạm ô nhiễm cao và cụm trạm ô nhiễm trung bình/thấp.

#### TC_ML_07: Lưu trữ và đồng bộ kết quả phân tích AI/ML vào các bảng kết quả
* **Phân loại**: Nâng cấp
* **Tiền điều kiện**: Pipeline `src/analysis/analytics_runner.py` hoàn tất.
* **Các bước thực hiện**:
  1. Kiểm tra sự hiện diện dữ liệu trong các bảng: `ml_station_cluster_result`, `ml_pollution_pattern`.
* **Dữ liệu kiểm thử**: Toàn bộ kết quả chạy ML.
* **Kết quả mong đợi**: Các bảng kết quả được ghi nhận đầy đủ kèm timestamp của lần chạy, không phát sinh lỗi khóa ngoại.

---

### NHÓM 6: GIAO DIỆN WEB DASHBOARD DARK MODE & BẢN ĐỒ GIS (WEB UI & FILTERS)
Tài liệu liên quan: `src/dashboard/app.py`, `src/dashboard/template.html`

#### TC_UI_01: Kiểm tra khả năng khởi chạy và hiển thị giao diện Web Dashboard
* **Phân loại**: Cũ
* **Tiền điều kiện**: Container `openaq_web_dashboard` đang chạy ở cổng 8050.
* **Các bước thực hiện**:
  1. Mở trình duyệt web và truy cập: `http://localhost:8050`.
  2. Quan sát quá trình tải trang và các thành phần giao diện.
* **Dữ liệu kiểm thử**: URL `http://localhost:8050`.
* **Kết quả mong đợi**: Trang tải thành công dưới 3 giây, hiển thị đầy đủ tiêu đề, các thẻ KPI và không có thông báo lỗi JavaScript.

#### TC_UI_02: Kiểm tra giao diện chủ đề tối (Dark Mode Design System)
* **Phân loại**: Nâng cấp
* **Tiền điều kiện**: Dashboard đã tải xong trên trình duyệt.
* **Các bước thực hiện**:
  1. Quan sát màu nền chính, màu thẻ card, thanh sidebar và màu chữ.
* **Dữ liệu kiểm thử**: Giao diện trực quan.
* **Kết quả mong đợi**: Màu nền đồng nhất tông màu tối cao cấp (#0f172a / #1e293b), chữ màu trắng/xám sáng, độ tương phản đạt chuẩn dễ đọc.

#### TC_UI_03: Kiểm tra hiển thị các thẻ KPI thống kê tổng quan (Summary Cards)
* **Phân loại**: Nâng cấp
* **Tiền điều kiện**: Dữ liệu DWH đã nạp đầy đủ.
* **Các bước thực hiện**:
  1. Kiểm tra 4 thẻ KPI trên đầu trang: Tổng số trạm, Tổng số thành phố, AQI trung bình, Mốc dữ liệu mới nhất.
  2. Đối chiếu số liệu với câu truy vấn `SELECT * FROM vw_kpi_overview;`.
* **Dữ liệu kiểm thử**: Số liệu từ `vw_kpi_overview`.
* **Kết quả mong đợi**: Số liệu trên thẻ KPI hiển thị chính xác khớp 100% với số liệu trong kho dữ liệu DWH.

#### TC_UI_04: Kiểm tra bộ lọc phân cấp cấp 1 - Lọc theo Quốc gia (Country Filter)
* **Phân loại**: Mới
* **Tiền điều kiện**: Dropdown Quốc gia đang hiển thị "All Countries".
* **Các bước thực hiện**:
  1. Bấm vào dropdown chọn Quốc gia.
  2. Chọn "Vietnam".
  3. Quan sát sự thay đổi của dropdown Thành phố và các biểu đồ bên dưới.
* **Dữ liệu kiểm thử**: Lựa chọn "Vietnam".
* **Kết quả mong đợi**:
  * Dropdown Thành phố tự động cập nhật, chỉ hiển thị danh sách 15 thành phố của Việt Nam.
  * Toàn bộ biểu đồ và bản đồ làm mới chỉ hiển thị dữ liệu của Việt Nam.

#### TC_UI_05: Kiểm tra bộ lọc phân cấp cấp 2 - Lọc theo Thành phố (City Filter)
* **Phân loại**: Mới
* **Tiền điều kiện**: Đã chọn Quốc gia "Vietnam".
* **Các bước thực hiện**:
  1. Bấm vào dropdown Thành phố.
  2. Chọn "Hanoi".
  3. Quan sát dropdown Trạm quan trắc (`Station`).
* **Dữ liệu kiểm thử**: Lựa chọn "Hanoi".
* **Kết quả mong đợi**:
  * Dropdown Trạm chỉ hiển thị các trạm tại Hà Nội (Lưu Quang Vũ, Nhân Chính, Giải Phóng,...).
  * Bản đồ tự động canh chỉnh (pan/zoom) tập trung về khu vực Hà Nội.

#### TC_UI_06: Kiểm tra bộ lọc phân cấp cấp 3 - Lọc theo Trạm quan trắc (Station Filter)
* **Phân loại**: Mới
* **Tiền điều kiện**: Đã chọn Thành phố "Hanoi".
* **Các bước thực hiện**:
  1. Chọn 1 trạm cụ thể từ danh sách.
  2. Quan sát biểu đồ xu hướng chuỗi thời gian (Time-series chart).
* **Dữ liệu kiểm thử**: Trạm "Lưu Quang Vũ".
* **Kết quả mong đợi**: Biểu đồ chỉ vẽ chuỗi dữ liệu nồng độ và AQI của riêng trạm được chọn theo từng mốc giờ.

#### TC_UI_07: Kiểm tra hiển thị Bản đồ số GIS không gian (Leaflet.js Map)
* **Phân loại**: Mới
* **Tiền điều kiện**: Có kết nối mạng tải OpenStreetMap tiles; Dashboard đang mở.
* **Các bước thực hiện**:
  1. Cuộn tới khu vực Bản đồ chất lượng không khí không gian.
  2. Kiểm tra tâm bản đồ mặc định và các điểm đánh dấu trạm quan trắc.
* **Dữ liệu kiểm thử**: Tọa độ các trạm Đông Nam Á.
* **Kết quả mong đợi**:
  * Tâm bản đồ đặt chính xác tại tọa độ trung tâm Việt Nam [16.04, 107.5].
  * Các trạm hiển thị bằng các điểm đánh dấu tròn mang màu sắc tương ứng chuẩn màu EPA AQI (Xanh: Tốt, Vàng: Trung bình, Cam: Nhạy cảm, Đỏ: Xấu, Tím: Rất nguy hại, Nâu: Nguy hiểm).

#### TC_UI_08: Kiểm tra tính năng tương tác Popup trên điểm đánh dấu bản đồ
* **Phân loại**: Mới
* **Tiền điều kiện**: Bản đồ đã hiển thị đầy đủ các điểm đánh dấu trạm.
* **Các bước thực hiện**:
  1. Nhấp chuột vào một điểm đánh dấu trạm bất kỳ trên bản đồ.
  2. Đọc nội dung hiển thị trong khung Popup.
* **Dữ liệu kiểm thử**: Điểm trạm tại TP. Hồ Chí Minh.
* **Kết quả mong đợi**: Khung Popup mở ra ngay lập tức, hiển thị đầy đủ: Tên trạm, Thành phố, Quốc gia, Giá trị AQI, Chất ô nhiễm chính, Nhiệt độ và Độ ẩm.

#### TC_UI_09: Kiểm tra thẻ so sánh chất lượng không khí song phương (Vietnam vs Thailand Card)
* **Phân loại**: Mới
* **Tiền điều kiện**: Kho dữ liệu có số đo của cả 2 quốc gia.
* **Các bước thực hiện**:
  1. Quan sát thẻ đối chuẩn quốc gia trên Dashboard.
  2. Đối chiếu số liệu hiển thị: AQI trung bình của Việt Nam so với Thái Lan.
* **Dữ liệu kiểm thử**: Dữ liệu từ view `vw_country_comparison`.
* **Kết quả mong đợi**: Thẻ hiển thị rõ ràng chỉ số so sánh AQI trung bình giữa 2 quốc gia, trực quan hóa quốc gia có mức độ trong lành cao hơn.

#### TC_UI_10: Kiểm tra tính năng Bật/Tắt Tự động làm mới dữ liệu (Auto-Refresh Toggle)
* **Phân loại**: Mới
* **Tiền điều kiện**: Dashboard đang hoạt động bình thường.
* **Các bước thực hiện**:
  1. Gạt công tắc "Auto-Refresh" trên thanh điều hướng sang "ON".
  2. Chờ 60 giây và quan sát biểu hiện cập nhật dữ liệu.
  3. Gạt công tắc trở lại "OFF".
* **Dữ liệu kiểm thử**: Thao tác toggle switch.
* **Kết quả mong đợi**: Khi "ON", giao diện tự động gửi request cập nhật dữ liệu định kỳ mỗi 60 giây mà không cần F5; khi "OFF", giao diện dừng hoàn toàn việc gửi request ngầm.

---

### NHÓM 7: ĐIỀU PHỐI LẬP LỊCH AIRFLOW & PHÂN TÍCH SUPERSET (ORCHESTRATION & BI)
Tài liệu liên quan: `dags/openaq_pipeline_dag.py`

#### TC_OPS_01: Kiểm tra việc tải và phân tích cú pháp DAG trong Apache Airflow
* **Phân loại**: Cũ
* **Tiền điều kiện**: Airflow Webserver và Scheduler đang chạy ở cổng 8082.
* **Các bước thực hiện**:
  1. Mở giao diện Airflow tại `http://localhost:8082`.
  2. Tìm kiếm DAG `openaq_etl_hourly_pipeline`.
  3. Kiểm tra thông báo lỗi import DAG.
* **Dữ liệu kiểm thử**: File DAG `dags/openaq_pipeline_dag.py`.
* **Kết quả mong đợi**: DAG được phân tích cú pháp thành công (No DAG import errors), hiển thị đầy đủ trên danh sách DAGs.

#### TC_OPS_02: Kích hoạt thủ công luồng pipeline (Trigger DAG Run)
* **Phân loại**: Nâng cấp
* **Tiền điều kiện**: DAG đang ở trạng thái Unpaused.
* **Các bước thực hiện**:
  1. Nhấn nút "Trigger DAG" trên giao diện Airflow.
  2. Chuyển sang chế độ xem Graph View.
  3. Theo dõi trạng thái chuyển màu của từng Task qua các giai đoạn: Queued -> Running -> Success.
* **Dữ liệu kiểm thử**: 1 lượt chạy thủ công.
* **Kết quả mong đợi**: Toàn bộ 4 tác vụ liên kết (`extract_openaq_data` -> `transform_openaq_data` -> `load_into_data_warehouse` -> `run_ml_analytics`) đều chuyển sang màu xanh lá cây (Success) theo đúng thứ tự phụ thuộc.

#### TC_OPS_03: Kiểm tra cấu hình lập lịch chu kỳ hàng giờ (Hourly Schedule)
* **Phân loại**: Mới
* **Tiền điều kiện**: DAG đã được cấu hình biểu thức Cron.
* **Các bước thực hiện**:
  1. Xem thuộc tính `schedule_interval` của DAG trên giao diện Airflow.
  2. Kiểm tra mốc thời gian kích hoạt tiếp theo (Next Run).
* **Dữ liệu kiểm thử**: Cấu hình `schedule_interval="0 * * * *"`.
* **Kết quả mong đợi**: Lịch trình thể hiện rõ chu kỳ kích hoạt vào đầu mỗi giờ; trường Next Run hiển thị đúng mốc giờ chẵn tiếp theo.

#### TC_OPS_04: Kiểm tra cơ chế tự động thử lại khi tác vụ thất bại (Task Retry)
* **Phân loại**: Mới
* **Tiền điều kiện**: Cấu hình `retries = 3`, `retry_delay = timedelta(minutes=2)`.
* **Các bước thực hiện**:
  1. Kiểm tra tham số `default_args` trong file DAG.
  2. Quan sát phản ứng khi một task gặp sự cố mạng tạm thời.
* **Dữ liệu kiểm thử**: File cấu hình DAG.
* **Kết quả mong đợi**: Task gặp sự cố chuyển sang trạng thái "Up for retry", tự động thực hiện lại sau khoảng thời gian trễ đã định trước khi kết luận thất bại.

#### TC_OPS_05: Kiểm tra kết nối và truy vấn dữ liệu từ Apache Superset SQL Lab
* **Phân loại**: Nâng cấp
* **Tiền điều kiện**: Superset container đang chạy ở cổng 8088; database `openaq_dw` đã kết nối.
* **Các bước thực hiện**:
  1. Đăng nhập Superset tại `http://localhost:8088`.
  2. Truy cập **SQL Lab** -> **SQL Editor**.
  3. Chọn Database: `openaq_dw`, Schema: `public`.
  4. Thực hiện câu lệnh truy vấn:
     ```sql
     SELECT country_code, city, AVG(aqi) AS avg_aqi 
     FROM vw_fact_enriched 
     WHERE aqi IS NOT NULL
     GROUP BY country_code, city 
     ORDER BY avg_aqi DESC LIMIT 10;
     ```
  5. Bấm nút **RUN**.
* **Dữ liệu kiểm thử**: Dữ liệu từ View `vw_fact_enriched`.
* **Kết quả mong đợi**: Superset thực thi câu lệnh thành công trong dưới 2 giây, trả về danh sách 10 thành phố có AQI trung bình cao nhất kèm đúng tên cột.

---

## 3. HƯỚNG DẪN THỰC HIỆN KIỂM THỬ THỦ CÔNG (EXECUTION WORKFLOW)

Khi thực hiện kiểm thử thực tế, khuyến nghị tiến hành theo 3 giai đoạn:

1. **Giai đoạn 1: Kiểm thử Kho dữ liệu (Database & Views)**:
   * Chạy tuần tự các câu truy vấn SQL trong **Nhóm 1, 3, 4** trên Superset SQL Lab hoặc DBeaver.
   * Xác nhận tính toàn vẹn khóa ngoại, tính duy nhất của trạm và kết quả tính toán AQI.
2. **Giai đoạn 2: Kiểm thử Giao diện Người dùng (Web Dashboard)**:
   * Truy cập `http://localhost:8050` và thực hiện các test case trong **Nhóm 6**.
   * Kiểm tra bộ lọc phân cấp (Country -> City -> Station), tương tác bản đồ Leaflet.js và công tắc Auto-Refresh.
3. **Giai đoạn 3: Kiểm thử Điều phối & Trí tuệ Nhân tạo (Airflow & ML)**:
   * Truy cập `http://localhost:8082` kích hoạt Trigger DAG và đối chiếu với kết quả lưu trong các bảng ML ở **Nhóm 5**.

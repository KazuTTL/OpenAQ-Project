# Báo Cáo Kiểm Thử Thủ Công & Nghiệm Thu Kho Dữ Liệu DWH
**Ngày thực hiện**: 28/10/2026  
**Phân hệ**: Toàn bộ hệ thống OpenAQ Data Platform (Kiến trúc mở rộng 20 thành phố, 52 trạm)  
**Vai trò thực hiện**: 
- Người kiểm thử (QA Tester): Người dùng (User)
- Tư vấn & Phân tích kỹ thuật (QA Lead / Technical Advisor): Antigravity

---

## 1. Tổng Quan Phiên Làm Việc

Trong phiên làm việc này, hệ thống đã hoàn thành việc chuyển giao toàn bộ kịch bản kiểm thử sang phương pháp **Kiểm thử thủ công (QA Manual)**, tập trung vào việc xác thực tính toàn vẹn dữ liệu, kiểm tra các tầng nghiệp vụ trên Kho dữ liệu PostgreSQL (`openaq_dw`), và đối soát các kết quả đầu ra của các mô hình AI/ML.

### Các mục tiêu chính đã đạt được:
1. Chuẩn hóa toàn bộ danh mục **45 Test Case** của hệ thống (bao gồm 17 test case cũ và 28 test case mới/nâng cấp) chia thành 7 nhóm phân hệ.
2. Xác định các nhóm kiểm thử có thể thực thi trực tiếp bằng truy vấn SQL trên Data Warehouse (5 nhóm).
3. Hướng dẫn và cung cấp bộ câu lệnh SQL chuẩn xác theo Schema thực tế của database `openaq_dw`.
4. Người dùng đã trực tiếp thực thi kiểm thử trên DWH, ghi nhận và phân tích sâu các kết quả thực tế (Verification & Root Cause Analysis).
5. Giải đáp và làm rõ cơ chế cập nhật tự động của Web Dashboard khi Airflow hoàn thành chu kỳ crawl dữ liệu mới.

---

## 2. Ma Trận Danh Mục Test Case Hệ Thống (QA Test Matrix)

| Nhóm | Phân hệ kiểm thử | Số TC Cũ | Số TC Mới / Nâng cấp | Tổng số TC | Đối tượng kiểm thử chính |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Nhóm 1** | Quản lý Cấu hình & Trạm Quan trắc | 2 | 2 | 4 | File `cities.yaml`, bảng `dim_location`, `dim_parameter` |
| **Nhóm 2** | Thu thập Dữ liệu & Tích hợp Khí tượng | 2 | 3 | 5 | API OpenAQ, Open-Meteo, cột `temperature`, `humidity` |
| **Nhóm 3** | Làm sạch, Chuẩn hóa & Tính AQI 7 Bước | 6 | 2 | 8 | Deduplication, Outlier, Múi giờ UTC+7, Công thức EPA |
| **Nhóm 4** | Kho Dữ liệu Star Schema & Views Phân tích | 2 | 4 | 6 | Khóa ngoại, `fact_measurement`, 6 Views tổng hợp |
| **Nhóm 5** | AI / Học máy & Khai phá Mẫu | 3 | 4 | 7 | Random Forest, K-Means, Anomaly Detection |
| **Nhóm 6** | Giao diện Web Dashboard Dark Mode & GIS | 3 | 7 | 10 | Giao diện Web cổng 8050, Leaflet GIS, Bộ lọc 3 cấp |
| **Nhóm 7** | Điều phối Airflow & Phân tích Superset | 2 | 3 | 5 | Airflow DAG `@hourly`, Superset SQL Lab cổng 8088 |
| **Tổng** | **Toàn bộ hệ thống** | **17** | **28** | **45** | **Bao phủ 100% chức năng hệ thống** |

---

## 3. Bộ Câu Lệnh SQL Kiểm Thử Trực Tiếp Trên Kho Dữ Liệu DWH

Hệ thống ghi nhận 5 nhóm kiểm thử có thể thực thi trực tiếp bằng SQL trên PostgreSQL:

### Nhóm 1: Kiểm thử Cấu hình & Bảng Chiều (Config & Registry)
* **Kiểm tra 6 tham số chuẩn EPA (`dim_parameter`)**:
  ```sql
  SELECT parameter_key, parameter_name, display_name, unit, description 
  FROM dim_parameter ORDER BY parameter_key ASC;
  ```
* **Kiểm tra số lượng thành phố và trạm quan trắc (`dim_location`)**:
  ```sql
  SELECT country_code, country, COUNT(DISTINCT city) AS total_cities, COUNT(location_key) AS total_stations
  FROM dim_location GROUP BY country_code, country ORDER BY country_code DESC;
  ```
* **Kiểm tra tính hợp lệ của tọa độ địa lý**:
  ```sql
  SELECT location_name, city, country_code, latitude, longitude 
  FROM dim_location 
  WHERE latitude IS NULL OR longitude IS NULL 
     OR latitude NOT BETWEEN -90 AND 90 OR longitude NOT BETWEEN -180 AND 180;
  ```

### Nhóm 2 & 4: Kiểm thử Khối lượng Dữ liệu & Star Schema (Fact & Enriched Views)
* **Kiểm tra tổng số bản ghi và dải thời gian 30 ngày**:
  ```sql
  SELECT COUNT(fm.measurement_key) AS total_measurements,
         MIN(dt.datetime_utc) AS earliest_record_utc,
         MAX(dt.datetime_utc) AS latest_record_utc,
         COUNT(DISTINCT fm.location_key) AS active_stations
  FROM fact_measurement fm JOIN dim_time dt ON dt.time_key = fm.time_key;
  ```
* **Kiểm tra tính toàn vẹn khóa ngoại (Foreign Keys Integrity)**:
  ```sql
  SELECT COUNT(CASE WHEN dt.time_key IS NULL THEN 1 END) AS orphan_time_keys,
         COUNT(CASE WHEN dl.location_key IS NULL THEN 1 END) AS orphan_location_keys,
         COUNT(CASE WHEN dp.parameter_key IS NULL THEN 1 END) AS orphan_parameter_keys
  FROM fact_measurement fm
  LEFT JOIN dim_time dt ON dt.time_key = fm.time_key
  LEFT JOIN dim_location dl ON dl.location_key = fm.location_key
  LEFT JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key;
  ```
* **Kiểm tra View đối chuẩn quốc gia (`vw_country_comparison`)**:
  ```sql
  SELECT country_code, country_name, active_stations, total_cities, avg_aqi, avg_pm25, avg_temp, avg_humidity
  FROM vw_country_comparison ORDER BY country_code DESC;
  ```

### Nhóm 3: Kiểm thử Làm sạch & Tính toán AQI chuẩn EPA (Transform Validation)
* **Kiểm tra tính duy nhất (Không có bản ghi trùng lặp khóa nghiệp vụ)**:
  ```sql
  SELECT time_key, location_key, parameter_key, COUNT(*) AS duplicate_count
  FROM fact_measurement GROUP BY time_key, location_key, parameter_key HAVING COUNT(*) > 1;
  ```
* **Kiểm tra phân đoạn và dải AQI chuẩn EPA (loại trừ giá trị NULL)**:
  ```sql
  SELECT pollution_category, MIN(aqi) AS min_aqi, MAX(aqi) AS max_aqi, COUNT(*) AS count_records
  FROM fact_measurement WHERE aqi IS NOT NULL
  GROUP BY pollution_category ORDER BY min_aqi ASC;
  ```

### Nhóm 5: Kiểm thử Kết quả Học máy & Bất thường (AI / ML Results)
* **Kiểm tra tỷ lệ phân bố bản ghi bất thường (`is_anomaly`)**:
  ```sql
  SELECT is_anomaly, COUNT(*) AS record_count,
         ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS percentage
  FROM fact_measurement GROUP BY is_anomaly;
  ```
* **Bóc tách bất thường theo chất đo và thuật toán phát hiện**:
  ```sql
  SELECT dp.parameter_name, COALESCE(fm.anomaly_method, 'threshold') AS method,
         COUNT(*) AS anomaly_count,
         ROUND(AVG(fm.value)::numeric, 2) AS avg_anomaly_value,
         ROUND(AVG(fm.aqi)::numeric, 1) AS avg_anomaly_aqi
  FROM fact_measurement fm JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
  WHERE fm.is_anomaly = TRUE
  GROUP BY dp.parameter_name, COALESCE(fm.anomaly_method, 'threshold')
  ORDER BY anomaly_count DESC;
  ```
* **Kiểm tra View cảnh báo sự cố ô nhiễm nghiêm trọng (lọc loại bỏ NULL)**:
  ```sql
  SELECT datetime_utc, location_name, city, parameter_name, value, aqi, pollution_category, anomaly_score, anomaly_method
  FROM vw_anomaly_alerts WHERE aqi IS NOT NULL ORDER BY aqi DESC LIMIT 10;
  ```

---

## 4. Nhật Ký Thực Thi Kiểm Thử & Phân Tích Kết Quả Thực Tế

Trong phiên làm việc, Người dùng đã trực tiếp chạy các truy vấn kiểm thử và phát hiện các điểm nghiệp vụ quan trọng:

### 1. Kiểm thử TC_CFG_02 (`dim_parameter`)
* **Kết quả thực tế**: Trả về 6 tham số chuẩn EPA (`pm25`, `pm10`, `o3`, `no2`, `so2`, `co`) và 4 tham số phát sinh tự động (`pm1`, `relativehumidity`, `um003`, `temperature`).
* **Đánh giá**: **PASS**. Hệ thống có tính năng Dynamic Parameter Registration, tự động mở rộng bảng chiều khi gặp thông số cảm biến mới mà không gây crash pipeline.

### 2. Kiểm thử TC_TRF_06 (`pollution_category` & AQI)
* **Kết quả thực tế**: 
  * 6 nhóm EPA đạt chuẩn hoàn hảo: Good (0-50), Moderate (51-100), Unhealthy for Sensitive Groups (101-150), Unhealthy (151-199.3), Very Unhealthy (206-295.4), Hazardous (303.5-796.9).
  * Xuất hiện 5,648 bản ghi có `pollution_category = 'Unknown'` và `aqi = NULL`.
* **Phân tích nguyên nhân**: Truy vấn bóc tách cho thấy chính xác $1,412 \times 4 = 5,648$ bản ghi thuộc về `pm1`, `relativehumidity`, `um003`, `temperature`. Vì EPA không quy định công thức AQI cho nhiệt độ/độ ẩm/đếm hạt, hệ thống để `aqi = NULL` là hoàn toàn đúng logic thiết kế bảo toàn tính toàn vẹn dữ liệu.

### 3. Kiểm thử TC_ML_01 (`is_anomaly` phân bố bất thường)
* **Kết quả thực tế**:
  * Bình thường (`false`): 44,961 bản ghi (89.58%).
  * Bất thường (`true`): 5,229 bản ghi (10.42%).
* **Phân tích nguyên nhân**: Tỷ lệ 10.42% xuất phát từ cơ chế Ensemble đa thuật toán (Rolling Window, IQR, Z-Score). Trong đó:
  * Thuật toán `rolling` bắt được 2,116 sự cố biến động ngắn hạn ở PM2.5.
  * Nhóm cực đoan bị cả 3 thuật toán cùng bắt (`iqr,rolling,zscore` - 8 bản ghi PM2.5) có nồng độ trung bình lên đến **192.45 µg/m³**, tương ứng AQI trung bình **235.7** (Mức Tím - Rất nguy hại).

### 4. Kiểm thử TC_ML_02 (`vw_anomaly_alerts`)
* **Kết quả thực tế**: Khi chạy `ORDER BY aqi DESC`, 10 dòng đầu tiên hiển thị tham số thời tiết (`temperature`, `relativehumidity`) với `aqi` để trống.
* **Nguyên nhân kỹ thuật**: Quy ước mặc định của PostgreSQL là `ORDER BY DESC NULLS FIRST`.
* **Giải pháp khắc phục**: Đã chuẩn hóa câu lệnh kiểm thử bằng cách bổ sung `WHERE aqi IS NOT NULL` để hiển thị chính xác các đợt bùng phát ô nhiễm không khí nguy hiểm nhất.

---

## 5. Cơ Chế Đồng Bộ Giữa Airflow ETL Và Web Dashboard

Đã làm rõ câu hỏi vận hành của Người dùng về việc cập nhật dữ liệu sau khi Airflow crawl xong:
1. **Phía DWH**: Dữ liệu sau khi nạp vào `fact_measurement` sẽ sẵn sàng trên các View (`vw_fact_enriched`, `vw_station_map`) ngay tức thì mà không cần rebuild schema.
2. **Phía Web Dashboard (`http://localhost:8050`)**:
   * **Chế độ tự động**: Khi bật công tắc **Auto-Refresh = ON**, Dashboard tự động polling định kỳ mỗi 60 giây và cập nhật số liệu mới mà không cần F5.
   * **Chế độ thủ công**: Khi công tắc Auto-Refresh ở trạng thái **OFF**, người dùng chỉ cần nhấn **F5** để tải lại dữ liệu mới nhất.

---

## 6. Trạng Thái Nghiệm Thu Hệ Thống (QA Sign-Off Status)

* **Toàn bộ 45/45 Test Case** đã được định nghĩa và chuẩn hóa rõ ràng.
* **43/43 Automated Unit Tests** tiếp tục duy trì trạng thái 100% PASS.
* **Toàn bộ các bảng Fact, Dim và Views phân tích** trong DWH PostgreSQL hoạt động ổn định, chính xác theo đúng mô hình dữ liệu Star Schema.
* Phiên làm việc kết thúc thành công với sự thống nhất cao giữa kết quả kiểm thử thủ công và kiến trúc thiết kế hệ thống.

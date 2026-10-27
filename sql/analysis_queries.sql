-- TAP LENH TRUY VAN VA VIEW PHAN TICH DU LIEU (DUNG CHO SUPERSET / POWER BI)

-- ============================================================================
-- PHAN A: KHOI TAO CAC VIEW PHAN TICH TRUC QUAN HOA TRONG DATA WAREHOUSE
-- ============================================================================

CREATE OR REPLACE VIEW vw_fact_enriched AS
SELECT
    fm.measurement_key,
    dt.datetime_utc,
    dt.local_date::timestamp AS local_date,
    dt.hour,
    dt.day_of_week,
    TRIM(dt.day_name) AS day_name,
    dt.month,
    dt.season,
    dl.source_location_id,
    dl.location_name,
    dl.city,
    dl.country,
    dl.latitude,
    dl.longitude,
    dp.parameter_name,
    dp.display_name AS parameter_display,
    dp.unit,
    fm.value,
    fm.aqi,
    fm.pollution_category,
    fm.is_anomaly,
    fm.anomaly_score,
    fm.anomaly_method
FROM fact_measurement fm
JOIN dim_time dt ON dt.time_key = fm.time_key
JOIN dim_location dl ON dl.location_key = fm.location_key
JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key;

CREATE OR REPLACE VIEW vw_kpi_overview AS
SELECT 
    COUNT(DISTINCT fm.location_key) AS active_stations_count,
    ROUND(AVG(fm.aqi)::numeric, 1)::float AS overall_avg_aqi,
    COUNT(fm.measurement_key) AS total_measurements,
    COUNT(CASE WHEN fm.is_anomaly = TRUE THEN 1 END) AS total_anomalies,
    MAX(dt.datetime_utc) AS latest_data_timestamp
FROM fact_measurement fm
JOIN dim_time dt ON dt.time_key = fm.time_key;

CREATE OR REPLACE VIEW vw_pollution_category_dist AS
SELECT 
    fm.pollution_category,
    COUNT(fm.measurement_key) AS measurement_count,
    ROUND(COUNT(fm.measurement_key) * 100.0 / NULLIF(SUM(COUNT(fm.measurement_key)) OVER(), 0), 2)::float AS percentage
FROM fact_measurement fm
WHERE fm.pollution_category IS NOT NULL
GROUP BY fm.pollution_category;

CREATE OR REPLACE VIEW vw_daily_aqi_trend AS
SELECT 
    dt.local_date::timestamp AS local_date,
    dl.city,
    dl.location_name,
    dp.parameter_name,
    ROUND(AVG(fm.value)::numeric, 3)::float AS avg_concentration,
    ROUND(AVG(fm.aqi)::numeric, 1)::float AS avg_aqi,
    ROUND(MAX(fm.aqi)::numeric, 1)::float AS max_aqi
FROM fact_measurement fm
JOIN dim_time dt ON dt.time_key = fm.time_key
JOIN dim_location dl ON dl.location_key = fm.location_key
JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
GROUP BY dt.local_date, dl.city, dl.location_name, dp.parameter_name;

CREATE OR REPLACE VIEW vw_hourly_weekday_heatmap AS
SELECT 
    TRIM(dt.day_name) AS day_name,
    dt.day_of_week,
    dt.hour,
    dl.city,
    dp.parameter_name,
    ROUND(AVG(fm.aqi)::numeric, 1)::float AS avg_aqi,
    COUNT(fm.measurement_key) AS measurement_count
FROM fact_measurement fm
JOIN dim_time dt ON dt.time_key = fm.time_key
JOIN dim_location dl ON dl.location_key = fm.location_key
JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
GROUP BY TRIM(dt.day_name), dt.day_of_week, dt.hour, dl.city, dp.parameter_name;

CREATE OR REPLACE VIEW vw_station_map AS
SELECT 
    dl.source_location_id,
    dl.location_name,
    dl.city,
    dl.country,
    dl.latitude,
    dl.longitude,
    ROUND(AVG(fm.aqi)::numeric, 1)::float AS avg_aqi,
    ROUND(MAX(fm.aqi)::numeric, 1)::float AS max_aqi,
    COUNT(fm.measurement_key) AS recorded_data_points,
    COUNT(CASE WHEN fm.aqi > 100 THEN 1 END) AS unhealthy_hours
FROM fact_measurement fm
JOIN dim_location dl ON dl.location_key = fm.location_key
WHERE dl.latitude IS NOT NULL AND dl.longitude IS NOT NULL
GROUP BY dl.source_location_id, dl.location_name, dl.city, dl.country, dl.latitude, dl.longitude;

CREATE OR REPLACE VIEW vw_station_ranking AS
SELECT 
    RANK() OVER (ORDER BY AVG(fm.aqi) DESC) AS ranking,
    dl.location_name,
    dl.city,
    ROUND(AVG(fm.aqi)::numeric, 1)::float AS average_aqi,
    ROUND(MAX(fm.aqi)::numeric, 1)::float AS max_aqi,
    COUNT(CASE WHEN fm.aqi > 100 THEN 1 END) AS unhealthy_hours,
    COUNT(CASE WHEN fm.is_anomaly = TRUE THEN 1 END) AS anomaly_count,
    COUNT(fm.measurement_key) AS total_measurements
FROM fact_measurement fm
JOIN dim_location dl ON dl.location_key = fm.location_key
WHERE fm.aqi IS NOT NULL
GROUP BY dl.location_name, dl.city;

CREATE OR REPLACE VIEW vw_anomaly_alerts AS
SELECT 
    dt.datetime_utc,
    dl.location_name,
    dl.city,
    dp.parameter_name,
    ROUND(fm.value::numeric, 3)::float AS value,
    dp.unit,
    ROUND(fm.aqi::numeric, 1)::float AS aqi,
    fm.pollution_category,
    ROUND(COALESCE(fm.anomaly_score, 0)::numeric, 2)::float AS anomaly_score,
    COALESCE(fm.anomaly_method, 'threshold') AS anomaly_method
FROM fact_measurement fm
JOIN dim_time dt ON dt.time_key = fm.time_key
JOIN dim_location dl ON dl.location_key = fm.location_key
JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
WHERE fm.is_anomaly = TRUE OR fm.aqi > 150;

CREATE OR REPLACE VIEW vw_ml_station_clusters AS
SELECT 
    c.run_timestamp,
    dl.location_name,
    dl.city,
    dl.latitude,
    dl.longitude,
    c.cluster,
    c.cluster_label,
    ROUND(c.avg_aqi::numeric, 1)::float AS avg_aqi,
    ROUND(c.std_aqi::numeric, 2)::float AS std_aqi,
    ROUND(c.max_aqi::numeric, 1)::float AS max_aqi,
    ROUND((c.unhealthy_rate * 100)::numeric, 1)::float AS unhealthy_pct,
    ROUND((c.anomaly_rate * 100)::numeric, 1)::float AS anomaly_pct
FROM ml_station_cluster_result c
JOIN dim_location dl ON dl.location_key = c.location_key
WHERE c.run_timestamp = (SELECT MAX(run_timestamp) FROM ml_station_cluster_result);

-- ============================================================================
-- PHAN B: CAC CAU TRUY VAN TRUC TIEP THEO 4 TRANG BAO CAO
-- ============================================================================

-- 1. TRANG 1: TONG QUAN
-- 1.1 So lieu KPI Tong the
SELECT 
    COUNT(DISTINCT fm.location_key) as active_stations_count,
    ROUND(AVG(fm.aqi)::numeric, 1) as overall_avg_aqi,
    COUNT(fm.measurement_key) as total_measurements,
    MAX(dt.datetime_utc) as latest_data_timestamp
FROM fact_measurement fm
JOIN dim_time dt ON dt.time_key = fm.time_key;

-- 1.2 Phan bo cac muc do o nhiem (Donut / Pie Chart)
SELECT 
    fm.pollution_category,
    COUNT(fm.measurement_key) as measurement_count,
    ROUND(COUNT(fm.measurement_key) * 100.0 / SUM(COUNT(fm.measurement_key)) OVER(), 2) as percentage
FROM fact_measurement fm
WHERE fm.pollution_category IS NOT NULL
GROUP BY fm.pollution_category
ORDER BY measurement_count DESC;

-- 2. TRANG 2: XU HUONG THOI GIAN
-- 2.1 Xu huong AQI trung binh theo ngay (Line Chart)
SELECT 
    dt.local_date,
    dp.parameter_name,
    ROUND(AVG(fm.value)::numeric, 2) as avg_concentration,
    ROUND(AVG(fm.aqi)::numeric, 1) as avg_aqi
FROM fact_measurement fm
JOIN dim_time dt ON dt.time_key = fm.time_key
JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
GROUP BY dt.local_date, dp.parameter_name
ORDER BY dt.local_date ASC, dp.parameter_name;

-- 2.2 Heatmap: Gio trong ngay x Ngay trong tuan (Gio cao diem o nhiem)
SELECT 
    dt.day_name,
    dt.day_of_week,
    dt.hour,
    ROUND(AVG(fm.aqi)::numeric, 1) as avg_aqi
FROM fact_measurement fm
JOIN dim_time dt ON dt.time_key = fm.time_key
GROUP BY dt.day_name, dt.day_of_week, dt.hour
ORDER BY dt.day_of_week, dt.hour;

-- 3. TRANG 3: DIA DIEM
-- 3.1 Thong tin toa do va muc o nhiem trung binh tung tram (Ban do Bubble Map)
SELECT 
    dl.source_location_id,
    dl.location_name,
    dl.city,
    dl.country,
    dl.latitude,
    dl.longitude,
    ROUND(AVG(fm.aqi)::numeric, 1) as avg_aqi,
    MAX(fm.pollution_category) as worst_recorded_category,
    COUNT(fm.measurement_key) as recorded_data_points
FROM fact_measurement fm
JOIN dim_location dl ON dl.location_key = fm.location_key
WHERE dl.latitude IS NOT NULL AND dl.longitude IS NOT NULL
GROUP BY dl.source_location_id, dl.location_name, dl.city, dl.country, dl.latitude, dl.longitude;

-- 3.2 Bang xep hang tram co muc o nhiem cao nhat
SELECT 
    RANK() OVER (ORDER BY AVG(fm.aqi) DESC) as ranking,
    dl.location_name,
    dl.city,
    ROUND(AVG(fm.aqi)::numeric, 1) as average_aqi,
    COUNT(CASE WHEN fm.aqi > 150 THEN 1 END) as unhealthy_hours
FROM fact_measurement fm
JOIN dim_location dl ON dl.location_key = fm.location_key
WHERE fm.aqi IS NOT NULL
GROUP BY dl.location_name, dl.city
LIMIT 20;

-- 4. TRANG 4: DU DOAN & BAT THUONG
-- 4.1 Danh sach cac phep do bat thuong can ra soat (Alert Table)
SELECT 
    dt.datetime_utc,
    dl.location_name,
    dl.city,
    dp.parameter_name,
    fm.value,
    dp.unit,
    fm.aqi,
    fm.pollution_category
FROM fact_measurement fm
JOIN dim_time dt ON dt.time_key = fm.time_key
JOIN dim_location dl ON dl.location_key = fm.location_key
JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
WHERE fm.is_anomaly = TRUE OR fm.aqi > 300
ORDER BY dt.datetime_utc DESC
LIMIT 50;

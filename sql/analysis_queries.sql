-- TAP LENH TRUY VAN PHAN TICH DU LIEU (DUNG CHO SUPERSET / POWER BI)

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

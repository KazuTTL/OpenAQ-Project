-- 1. Thống kê AQI trung bình theo ngày
SELECT t.local_date, AVG(f.aqi) as avg_aqi
FROM fact_measurement f
JOIN dim_time t ON f.time_key = t.time_key
GROUP BY t.local_date;

-- 2. Top 5 trạm đo ô nhiễm nhất
SELECT l.location_name, AVG(f.aqi) as avg_aqi
FROM fact_measurement f
JOIN dim_location l ON f.location_key = l.location_key
GROUP BY l.location_name
ORDER BY avg_aqi DESC LIMIT 5;

-- 3. Truy xuất các thời điểm có chỉ số bất thường
SELECT t.datetime_utc, l.location_name, p.parameter_name, f.value
FROM fact_measurement f
JOIN dim_time t ON f.time_key = t.time_key
JOIN dim_location l ON f.location_key = l.location_key
JOIN dim_parameter p ON f.parameter_key = p.parameter_key
WHERE f.is_anomaly = TRUE;
\c openaq_dw;

-- Script khoi tao Data Warehouse Schema cho he thong phan tich OpenAQ
-- Mo hinh: Star Schema (1 Fact Table + 3 Dimension Tables + Staging Table)

-- 1. Tao bang Staging (chua du lieu tho sau khi extract/transform de chuan bi load)
CREATE TABLE IF NOT EXISTS staging_measurement (
    staging_id BIGSERIAL PRIMARY KEY,
    source_location_id INTEGER,
    location_name VARCHAR(255),
    city VARCHAR(255),
    country VARCHAR(100),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    timezone VARCHAR(50),
    parameter_name VARCHAR(50),
    unit VARCHAR(20),
    measurement_value DOUBLE PRECISION,
    datetime_utc TIMESTAMP NOT NULL,
    local_datetime TIMESTAMP,
    aqi DOUBLE PRECISION,
    pollution_category VARCHAR(50),
    country_code VARCHAR(10) DEFAULT 'VN',
    region VARCHAR(50),
    data_source VARCHAR(20) DEFAULT 'openaq',
    temperature DOUBLE PRECISION,
    humidity DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index cho bang staging de toi uu qua trinh tra cuu va load
CREATE INDEX IF NOT EXISTS idx_staging_datetime ON staging_measurement(datetime_utc);
CREATE INDEX IF NOT EXISTS idx_staging_location ON staging_measurement(source_location_id);
CREATE INDEX IF NOT EXISTS idx_staging_param ON staging_measurement(parameter_name);

-- 2. Bang Dimension: dim_time
CREATE TABLE IF NOT EXISTS dim_time (
    time_key SERIAL PRIMARY KEY,
    datetime_utc TIMESTAMP NOT NULL UNIQUE,
    local_date DATE NOT NULL,
    hour SMALLINT NOT NULL CHECK (hour BETWEEN 0 AND 23),
    day_of_week SMALLINT NOT NULL CHECK (day_of_week BETWEEN 1 AND 7), -- 1: Monday, 7: Sunday
    day_name VARCHAR(15) NOT NULL,
    month SMALLINT NOT NULL CHECK (month BETWEEN 1 AND 12),
    month_name VARCHAR(15) NOT NULL,
    quarter SMALLINT NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    year INTEGER NOT NULL,
    season VARCHAR(20) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dim_time_date ON dim_time(local_date);
CREATE INDEX IF NOT EXISTS idx_dim_time_year_month ON dim_time(year, month);

-- 3. Bang Dimension: dim_location
CREATE TABLE IF NOT EXISTS dim_location (
    location_key SERIAL PRIMARY KEY,
    source_location_id INTEGER NOT NULL UNIQUE,
    location_name VARCHAR(255) NOT NULL,
    city VARCHAR(255),
    country VARCHAR(100) DEFAULT 'Vietnam',
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    timezone VARCHAR(50) DEFAULT 'Asia/Ho_Chi_Minh',
    country_code VARCHAR(10) DEFAULT 'VN',
    region VARCHAR(50),
    data_source VARCHAR(20) DEFAULT 'openaq',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dim_location_city ON dim_location(city);
CREATE INDEX IF NOT EXISTS idx_dim_location_coords ON dim_location(latitude, longitude);

-- 4. Bang Dimension: dim_parameter
CREATE TABLE IF NOT EXISTS dim_parameter (
    parameter_key SERIAL PRIMARY KEY,
    parameter_name VARCHAR(50) NOT NULL UNIQUE, -- pm25, pm10, o3, no2, so2, co...
    display_name VARCHAR(50) NOT NULL,
    unit VARCHAR(20) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Bang Fact: fact_measurement
CREATE TABLE IF NOT EXISTS fact_measurement (
    measurement_key BIGSERIAL PRIMARY KEY,
    time_key INTEGER NOT NULL REFERENCES dim_time(time_key),
    location_key INTEGER NOT NULL REFERENCES dim_location(location_key),
    parameter_key INTEGER NOT NULL REFERENCES dim_parameter(parameter_key),
    value DOUBLE PRECISION NOT NULL,
    aqi DOUBLE PRECISION,
    pollution_category VARCHAR(50),
    temperature DOUBLE PRECISION,
    humidity DOUBLE PRECISION,
    is_anomaly BOOLEAN DEFAULT FALSE,
    anomaly_score DOUBLE PRECISION,
    anomaly_method VARCHAR(100),
    anomaly_detected_at TIMESTAMP,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_fact_measurement UNIQUE (time_key, location_key, parameter_key)
);

CREATE INDEX IF NOT EXISTS idx_fact_time ON fact_measurement(time_key);
CREATE INDEX IF NOT EXISTS idx_fact_location ON fact_measurement(location_key);
CREATE INDEX IF NOT EXISTS idx_fact_parameter ON fact_measurement(parameter_key);
CREATE INDEX IF NOT EXISTS idx_fact_category ON fact_measurement(pollution_category);
CREATE INDEX IF NOT EXISTS idx_fact_aqi ON fact_measurement(aqi);

-- 6. Bang luu ket qua phan cum tram theo tung lan chay ML
CREATE TABLE IF NOT EXISTS ml_station_cluster_result (
    result_id BIGSERIAL PRIMARY KEY,
    run_timestamp TIMESTAMP NOT NULL,
    location_key INTEGER NOT NULL REFERENCES dim_location(location_key),
    cluster INTEGER NOT NULL,
    cluster_label VARCHAR(100),
    avg_aqi DOUBLE PRECISION,
    std_aqi DOUBLE PRECISION,
    max_aqi DOUBLE PRECISION,
    unhealthy_rate DOUBLE PRECISION,
    anomaly_rate DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ml_cluster_run ON ml_station_cluster_result(run_timestamp);

-- 7. Bang luu ket qua pattern mining va tuong quan pollutant
CREATE TABLE IF NOT EXISTS ml_pollution_pattern (
    pattern_id BIGSERIAL PRIMARY KEY,
    run_timestamp TIMESTAMP NOT NULL,
    pattern_type VARCHAR(50) NOT NULL,
    location_key INTEGER REFERENCES dim_location(location_key),
    parameter_name VARCHAR(50),
    period_value VARCHAR(50),
    episode_start TIMESTAMP,
    episode_end TIMESTAMP,
    duration_hours DOUBLE PRECISION,
    measurement_count INTEGER,
    mean_value DOUBLE PRECISION,
    max_value DOUBLE PRECISION,
    correlation_value DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ml_pattern_run ON ml_pollution_pattern(run_timestamp);
CREATE INDEX IF NOT EXISTS idx_ml_pattern_type ON ml_pollution_pattern(pattern_type);

-- Khoi tao du lieu mac dinh cho bang dim_parameter
INSERT INTO dim_parameter (parameter_name, display_name, unit, description)
VALUES 
    ('pm25', 'PM2.5', 'ug/m3', 'Bui min kich thuoc duoi 2.5 micromet'),
    ('pm10', 'PM10', 'ug/m3', 'Bui min kich thuoc duoi 10 micromet'),
    ('o3', 'Ozone (O3)', 'ppm', 'Khi Ozone tang mat dat'),
    ('no2', 'Nitrogen Dioxide (NO2)', 'ppm', 'Khi NO2 phat thai tu giao thong/cong nghiep'),
    ('so2', 'Sulfur Dioxide (SO2)', 'ppm', 'Khi SO2 phat thai tu dot nhien lieu hoa thach'),
    ('co', 'Carbon Monoxide (CO)', 'ppm', 'Khi CO khong mau khong mui do dot khong hoan toan')
ON CONFLICT (parameter_name) DO NOTHING;

-- 8. Cac View phan tich truc quan hoa phuc vu Superset va Power BI
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
    dl.country_code,
    dl.region,
    dl.latitude,
    dl.longitude,
    dp.parameter_name,
    dp.display_name AS parameter_display,
    dp.unit,
    fm.value,
    fm.aqi,
    fm.pollution_category,
    fm.temperature,
    fm.humidity,
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
    dl.country_code,
    dl.region,
    dl.latitude,
    dl.longitude,
    ROUND(AVG(fm.aqi)::numeric, 1)::float AS avg_aqi,
    ROUND(MAX(fm.aqi)::numeric, 1)::float AS max_aqi,
    ROUND(AVG(fm.temperature)::numeric, 1)::float AS avg_temperature,
    ROUND(AVG(fm.humidity)::numeric, 1)::float AS avg_humidity,
    COUNT(fm.measurement_key) AS recorded_data_points,
    COUNT(CASE WHEN fm.aqi > 100 THEN 1 END) AS unhealthy_hours
FROM fact_measurement fm
JOIN dim_location dl ON dl.location_key = fm.location_key
WHERE dl.latitude IS NOT NULL AND dl.longitude IS NOT NULL
GROUP BY dl.source_location_id, dl.location_name, dl.city, dl.country, dl.country_code, dl.region, dl.latitude, dl.longitude;

CREATE OR REPLACE VIEW vw_country_comparison AS
SELECT 
    dl.country_code,
    CASE 
        WHEN dl.country_code = 'VN' THEN 'Việt Nam'
        WHEN dl.country_code = 'TH' THEN 'Thái Lan'
        ELSE dl.country_code
    END AS country_name,
    COUNT(DISTINCT dl.location_key) AS active_stations,
    COUNT(DISTINCT dl.city) AS total_cities,
    ROUND(AVG(fm.aqi)::numeric, 1)::float AS avg_aqi,
    ROUND(AVG(CASE WHEN dp.parameter_name = 'pm25' THEN fm.value END)::numeric, 1)::float AS avg_pm25,
    ROUND(AVG(fm.temperature)::numeric, 1)::float AS avg_temp,
    ROUND(AVG(fm.humidity)::numeric, 1)::float AS avg_humidity,
    ROUND(COUNT(CASE WHEN fm.aqi > 100 THEN 1 END) * 100.0 / NULLIF(COUNT(fm.measurement_key), 0), 2)::float AS unhealthy_hours_pct,
    COUNT(fm.measurement_key) AS total_measurements
FROM fact_measurement fm
JOIN dim_location dl ON dl.location_key = fm.location_key
JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
GROUP BY dl.country_code;

CREATE OR REPLACE VIEW vw_region_comparison AS
SELECT 
    dl.country_code,
    dl.region,
    COUNT(DISTINCT dl.location_key) AS active_stations,
    ROUND(AVG(fm.aqi)::numeric, 1)::float AS avg_aqi,
    ROUND(AVG(CASE WHEN dp.parameter_name = 'pm25' THEN fm.value END)::numeric, 1)::float AS avg_pm25,
    ROUND(AVG(fm.temperature)::numeric, 1)::float AS avg_temp,
    ROUND(AVG(fm.humidity)::numeric, 1)::float AS avg_humidity
FROM fact_measurement fm
JOIN dim_location dl ON dl.location_key = fm.location_key
JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
WHERE dl.region IS NOT NULL
GROUP BY dl.country_code, dl.region
ORDER BY avg_aqi DESC;

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

CREATE OR REPLACE VIEW vw_pollutant_aqi_avg AS
SELECT
    UPPER(dp.parameter_name) AS pollutant_code,
    dp.display_name,
    dp.unit,
    ROUND(AVG(fm.aqi)::numeric, 0)::int AS avg_aqi,
    ROUND(AVG(fm.value)::numeric, 2)::float AS avg_concentration
FROM fact_measurement fm
JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
WHERE fm.aqi IS NOT NULL
GROUP BY dp.parameter_name, dp.display_name, dp.unit;

CREATE OR REPLACE VIEW vw_city_top10_aqi AS
SELECT
    ROW_NUMBER() OVER (ORDER BY AVG(CASE WHEN dp.parameter_name = 'pm25' THEN fm.aqi ELSE NULL END) DESC)::int AS rank_no,
    dl.city AS thanh_pho,
    ROUND(AVG(CASE WHEN dp.parameter_name = 'pm25' THEN fm.aqi ELSE NULL END)::numeric, 0)::int AS aqi,
    CASE
        WHEN AVG(CASE WHEN dp.parameter_name = 'pm25' THEN fm.aqi ELSE NULL END) <= 50 THEN 'Tốt'
        WHEN AVG(CASE WHEN dp.parameter_name = 'pm25' THEN fm.aqi ELSE NULL END) <= 100 THEN 'Trung bình'
        WHEN AVG(CASE WHEN dp.parameter_name = 'pm25' THEN fm.aqi ELSE NULL END) <= 150 THEN 'Kém'
        WHEN AVG(CASE WHEN dp.parameter_name = 'pm25' THEN fm.aqi ELSE NULL END) <= 200 THEN 'Xấu'
        ELSE 'Rất xấu'
    END AS muc_do
FROM fact_measurement fm
JOIN dim_location dl ON dl.location_key = fm.location_key
JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
GROUP BY dl.city
ORDER BY aqi DESC
LIMIT 10;

CREATE OR REPLACE VIEW vw_city_hourly_heatmap AS
SELECT
    dl.city,
    dt.hour,
    LPAD(dt.hour::text, 2, '0') || 'h' AS hour_label,
    ROUND(AVG(fm.aqi)::numeric, 0)::int AS avg_aqi
FROM fact_measurement fm
JOIN dim_time dt ON dt.time_key = fm.time_key
JOIN dim_location dl ON dl.location_key = fm.location_key
JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
WHERE dp.parameter_name = 'pm25'
GROUP BY dl.city, dt.hour;

CREATE OR REPLACE VIEW vw_city_pm25_hourly AS
SELECT
    dt.datetime_utc,
    dt.local_date::timestamp AS local_date,
    dl.city,
    dp.parameter_name,
    ROUND(AVG(fm.value)::numeric, 1)::float AS concentration_ugm3,
    ROUND(AVG(fm.aqi)::numeric, 1)::float AS avg_aqi
FROM fact_measurement fm
JOIN dim_time dt ON dt.time_key = fm.time_key
JOIN dim_location dl ON dl.location_key = fm.location_key
JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
WHERE dp.parameter_name = 'pm25'
GROUP BY dt.datetime_utc, dt.local_date, dl.city, dp.parameter_name;

CREATE OR REPLACE VIEW vw_anomaly_formatted AS
SELECT
    TO_CHAR(dt.datetime_utc + INTERVAL '7 hours', 'DD/MM HH24:MI') AS thoi_gian,
    dt.datetime_utc,
    dl.location_name AS tram,
    dl.city AS thanh_pho,
    UPPER(dp.parameter_name) AS thong_so,
    ROUND(fm.value::numeric, 1) || ' ' || dp.unit AS gia_tri_do_duoc,
    CASE
        WHEN dp.parameter_name = 'pm25' THEN '75 ug/m3'
        WHEN dp.parameter_name = 'pm10' THEN '100 ug/m3'
        WHEN dp.parameter_name = 'no2' THEN '0.053 ppm'
        WHEN dp.parameter_name = 'so2' THEN '0.035 ppm'
        ELSE '50 ' || dp.unit
    END AS nguong,
    CASE
        WHEN fm.aqi >= 150 THEN 'Cao'
        ELSE 'Trung bình'
    END AS muc_do,
    CASE
        WHEN fm.aqi >= 150 THEN 'Cảnh báo'
        ELSE 'Theo dõi'
    END AS trang_thai,
    ROUND(fm.aqi::numeric, 1)::float AS aqi,
    ROUND(fm.value::numeric, 3)::float AS raw_value
FROM fact_measurement fm
JOIN dim_time dt ON dt.time_key = fm.time_key
JOIN dim_location dl ON dl.location_key = fm.location_key
JOIN dim_parameter dp ON dp.parameter_key = fm.parameter_key
WHERE fm.is_anomaly = TRUE OR fm.aqi > 150
ORDER BY dt.datetime_utc DESC;

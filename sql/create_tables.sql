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

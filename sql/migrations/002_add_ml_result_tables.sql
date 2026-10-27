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
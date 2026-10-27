ALTER TABLE fact_measurement
    ADD COLUMN IF NOT EXISTS anomaly_score DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS anomaly_method VARCHAR(100),
    ADD COLUMN IF NOT EXISTS anomaly_detected_at TIMESTAMP;

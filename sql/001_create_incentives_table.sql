-- ==============================================================================
-- LetzRyd Stream 5: Uber Vehicle Incentives & Ingestion Logs Schema (PostgreSQL)
-- ==============================================================================

-- 1. VEHICLE INCENTIVES DATA TABLE
CREATE TABLE IF NOT EXISTS uber_vehicle_incentives_raw (
    id                          BIGSERIAL PRIMARY KEY,
    city                        VARCHAR(50) NOT NULL,
    vehicle_name                VARCHAR(150),
    number_plate                VARCHAR(50) NOT NULL,
    start_date                  TIMESTAMP NOT NULL,
    end_date                    TIMESTAMP NOT NULL,
    acceptance_rate             NUMERIC(6,2),
    target_acceptance_rate      NUMERIC(6,2),
    trips_completed             INTEGER DEFAULT 0,
    trip_target                 INTEGER DEFAULT 0,
    total_payout                NUMERIC(12,2) DEFAULT 0.00,
    status                      VARCHAR(50),
    driver_trip_count_breakdown TEXT,
    org_name                    VARCHAR(150),
    ingested_at                 TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_vehicle_incentive_window UNIQUE (city, number_plate, start_date, end_date)
);

CREATE INDEX IF NOT EXISTS idx_uber_inc_city ON uber_vehicle_incentives_raw(city);
CREATE INDEX IF NOT EXISTS idx_uber_inc_plate ON uber_vehicle_incentives_raw(number_plate);
CREATE INDEX IF NOT EXISTS idx_uber_inc_window ON uber_vehicle_incentives_raw(start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_uber_inc_status ON uber_vehicle_incentives_raw(status);


-- 2. PIPELINE INGESTION LOG TABLE (With GCS File Links)
CREATE TABLE IF NOT EXISTS uber_ingestion_logs (
    id                          BIGSERIAL PRIMARY KEY,
    execution_date              DATE NOT NULL,
    attempt_number              INTEGER NOT NULL DEFAULT 1,
    status                      VARCHAR(50) NOT NULL, -- 'SUCCESS' or 'FAILED'
    date_window_start           TIMESTAMP,
    date_window_end             TIMESTAMP,
    blr_rows                    INTEGER DEFAULT 0,
    mum_rows                    INTEGER DEFAULT 0,
    hyd_rows                    INTEGER DEFAULT 0,
    total_rows                  INTEGER DEFAULT 0,
    blr_file_url                TEXT,
    mum_file_url                TEXT,
    hyd_file_url                TEXT,
    master_file_url             TEXT,
    execution_duration_sec      NUMERIC(10,2),
    error_message               TEXT,
    created_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_uber_logs_date ON uber_ingestion_logs(execution_date);
CREATE INDEX IF NOT EXISTS idx_uber_logs_status ON uber_ingestion_logs(status);

-- ==============================================================================
-- LetzRyd Stream 5: Uber Vehicle Incentives Table (PostgreSQL)
-- ==============================================================================

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

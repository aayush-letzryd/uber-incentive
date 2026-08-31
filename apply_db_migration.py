import sys, io
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import psycopg2

DB_CONFIG = {
    "host": "35.200.196.113",
    "port": "5432",
    "dbname": "postgres",
    "user": "postgres",
    "password": r"8S5]U3@L^Xz)\FH}"
}

CREATE_TABLES_SQL = """
-- 1. Full-fidelity Uber Vehicle Incentives Table (11 columns matching official export)
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


-- 2. Ingestion Execution Log Table (matching LetzRyd standard with GCS URLs)
CREATE TABLE IF NOT EXISTS uber_incentives_ingestion_log (
    id                          BIGSERIAL PRIMARY KEY,
    execution_date              DATE NOT NULL,
    attempt_number              INTEGER NOT NULL DEFAULT 1,
    status                      VARCHAR(50) NOT NULL,
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

CREATE INDEX IF NOT EXISTS idx_uber_inc_log_date ON uber_incentives_ingestion_log(execution_date);
CREATE INDEX IF NOT EXISTS idx_uber_inc_log_status ON uber_incentives_ingestion_log(status);
"""

try:
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    print("Applying table migrations to PostgreSQL database...")
    cur.execute(CREATE_TABLES_SQL)
    conn.commit()
    print("✅ Tables 'uber_vehicle_incentives_raw' and 'uber_incentives_ingestion_log' successfully verified & created in PostgreSQL!")
    cur.close()
    conn.close()
except Exception as e:
    print(f"❌ Error applying migration: {e}")

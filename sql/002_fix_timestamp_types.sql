-- ==============================================================================
-- LetzRyd Migration 002: Fix Timestamp / Date Types
-- Run this once in Cloud SQL or direct psql to apply schema corrections.
-- ==============================================================================

-- Fix 1: Change date_window_start / date_window_end in log table
--         from TIMESTAMP → DATE (they store dates only, not datetimes)
ALTER TABLE uber_incentives_ingestion_log
    ALTER COLUMN date_window_start TYPE DATE
        USING date_window_start::DATE;

ALTER TABLE uber_incentives_ingestion_log
    ALTER COLUMN date_window_end TYPE DATE
        USING date_window_end::DATE;

-- Fix 2: Add IST offset comment to ingested_at column so devs know it's IST
COMMENT ON COLUMN uber_vehicle_incentives_raw.ingested_at
    IS 'Timestamp of ingestion in IST (UTC+5:30). Stored as naive timestamp, treat as IST.';

COMMENT ON COLUMN uber_incentives_ingestion_log.created_at
    IS 'Auto-set by DB (CURRENT_TIMESTAMP = UTC). Convert to IST (+5:30) when displaying.';

-- Fix 3: Add index on ingested_at for time-based queries
CREATE INDEX IF NOT EXISTS idx_uber_inc_ingested ON uber_vehicle_incentives_raw(ingested_at);

-- Fix 4: Add index on created_at for log table queries
CREATE INDEX IF NOT EXISTS idx_uber_logs_created ON uber_incentives_ingestion_log(created_at);

-- ==============================================================================
-- LetzRyd Migration 003: Schema Cleanliness & Index Verification
-- Run this ONCE against the production PostgreSQL database.
-- ==============================================================================

-- 1. Ensure the unique constraint uq_vehicle_incentive_window exists for upsert idempotency
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_vehicle_incentive_window'
    ) THEN
        ALTER TABLE uber_vehicle_incentives_raw
            ADD CONSTRAINT uq_vehicle_incentive_window UNIQUE (city, number_plate, start_date, end_date, trip_target);
    END IF;
END $$;

-- 2. Drop unused dead column org_name if it exists
ALTER TABLE uber_vehicle_incentives_raw
    DROP COLUMN IF EXISTS org_name;

-- 3. Verify
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'uber_vehicle_incentives_raw'
ORDER BY ordinal_position;

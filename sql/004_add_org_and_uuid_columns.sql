-- ==============================================================================
-- LetzRyd Migration 004: Add org_name and org_uuid columns & update unique key
-- Run this against the production PostgreSQL database.
-- ==============================================================================

-- 1. Add org_name and org_uuid columns if they do not exist
ALTER TABLE uber_vehicle_incentives_raw
    ADD COLUMN IF NOT EXISTS org_name VARCHAR(150),
    ADD COLUMN IF NOT EXISTS org_uuid VARCHAR(100);

-- 2. Drop old constraint on city
ALTER TABLE uber_vehicle_incentives_raw
    DROP CONSTRAINT IF EXISTS uq_vehicle_incentive_window;

-- 3. Create unique constraint using org_uuid for exact multi-org precision
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_vehicle_incentive_org_window'
    ) THEN
        ALTER TABLE uber_vehicle_incentives_raw
            ADD CONSTRAINT uq_vehicle_incentive_org_window
            UNIQUE (org_uuid, number_plate, start_date, end_date, trip_target);
    END IF;
END $$;

-- 4. Create indexes for high-speed filtering by org and city
CREATE INDEX IF NOT EXISTS idx_uber_inc_org_uuid ON uber_vehicle_incentives_raw(org_uuid);
CREATE INDEX IF NOT EXISTS idx_uber_inc_org_name ON uber_vehicle_incentives_raw(org_name);

-- 5. Verify columns
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'uber_vehicle_incentives_raw'
ORDER BY ordinal_position;

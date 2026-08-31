import sys, io
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import psycopg2

DB_CONFIG = {
    "host": "35.200.196.113",
    "port": "5432",
    "dbname": "postgres",
    "user": "postgres",
    "password": r""
}

FIX_SCHEMA_SQL = """
-- Drop old constraint and recreate with trip_target
ALTER TABLE uber_vehicle_incentives_raw DROP CONSTRAINT IF EXISTS uq_vehicle_incentive_window;

ALTER TABLE uber_vehicle_incentives_raw 
ADD CONSTRAINT uq_vehicle_incentive_window UNIQUE (city, number_plate, start_date, end_date, trip_target);
"""

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()
cur.execute(FIX_SCHEMA_SQL)
conn.commit()
print("✅ Updated unique constraint to (city, number_plate, start_date, end_date, trip_target)!")
cur.close()
conn.close()

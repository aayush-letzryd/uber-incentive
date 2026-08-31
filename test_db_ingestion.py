import sys, io
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import psycopg2
from psycopg2.extras import execute_values
import pandas as pd
from pathlib import Path

DB_CONFIG = {
    "host": "35.200.196.113",
    "port": "5432",
    "dbname": "postgres",
    "user": "postgres",
    "password": r""
}

blr_file = Path(r"C:\Users\anura\Downloads\20260824-20260831-vehicle_incentives-SAMVREEDDHI_MOBILITY_Pvt_Ltd_BLR_P.csv")

if not blr_file.exists():
    print("Bangalore file not found.")
    sys.exit(0)

print(f"Reading {blr_file.name}...")
df = pd.read_csv(blr_file)
print(f"Read {len(df):,} rows.")
df = df.drop_duplicates(subset=['Number plate', 'Start date', 'End date', 'Trip target'], keep='last')
print(f"Cleaned unique records: {len(df):,} rows.")

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

query = """
INSERT INTO uber_vehicle_incentives_raw (
    city, vehicle_name, number_plate, start_date, end_date,
    acceptance_rate, target_acceptance_rate, trips_completed,
    trip_target, total_payout, status, driver_trip_count_breakdown
) VALUES %s
ON CONFLICT (city, number_plate, start_date, end_date, trip_target) DO UPDATE SET
    acceptance_rate = EXCLUDED.acceptance_rate,
    target_acceptance_rate = EXCLUDED.target_acceptance_rate,
    trips_completed = EXCLUDED.trips_completed,
    total_payout = EXCLUDED.total_payout,
    status = EXCLUDED.status,
    driver_trip_count_breakdown = EXCLUDED.driver_trip_count_breakdown,
    ingested_at = CURRENT_TIMESTAMP;
"""

records = []
for _, r in df.iterrows():
    records.append((
        "Bangalore",
        str(r.get("Vehicle name", "")) if pd.notnull(r.get("Vehicle name")) else None,
        str(r.get("Number plate", "")),
        r.get("Start date"),
        r.get("End date"),
        float(r.get("Acceptance rate")) if pd.notnull(r.get("Acceptance rate")) else None,
        float(r.get("Target acceptance rate")) if pd.notnull(r.get("Target acceptance rate")) else None,
        int(r.get("Trips completed", 0)) if pd.notnull(r.get("Trips completed")) else 0,
        int(r.get("Trip target", 0)) if pd.notnull(r.get("Trip target")) else 0,
        float(r.get("Total payout", 0)) if pd.notnull(r.get("Total payout")) else 0.0,
        str(r.get("Status", "")) if pd.notnull(r.get("Status")) else None,
        str(r.get("Driver trip count breakdown", "")) if pd.notnull(r.get("Driver trip count breakdown")) else None
    ))

print(f"Upserting {len(records):,} records into uber_vehicle_incentives_raw in batches...")
execute_values(cur, query, records, page_size=2000)
conn.commit()

cur.execute("SELECT count(*) FROM uber_vehicle_incentives_raw;")
total_in_db = cur.fetchone()[0]
print(f"🎉 Total Rows currently in uber_vehicle_incentives_raw table: {total_in_db:,}")

# Insert test log
log_query = """
INSERT INTO uber_incentives_ingestion_log (
    execution_date, attempt_number, status, date_window_start, date_window_end,
    blr_rows, mum_rows, hyd_rows, total_rows,
    blr_file_url, mum_file_url, hyd_file_url, master_file_url,
    execution_duration_sec
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
"""
cur.execute(log_query, (
    "2026-08-31", 1, "SUCCESS", "2026-08-24 04:00:00", "2026-08-31 04:00:00",
    len(df), 0, 0, len(df),
    "https://storage.googleapis.com/letzryd-uber-reports/daily_exports/2026-08-31/20260824-20260831-vehicle_incentives-SAMVREEDDHI_BLR_P.xlsx",
    "https://storage.googleapis.com/letzryd-uber-reports/daily_exports/2026-08-31/20260824-20260831-vehicle_incentives-Samvreeddhi_Mobility_Pvt_Ltd_MUM_P.xlsx",
    "https://storage.googleapis.com/letzryd-uber-reports/daily_exports/2026-08-31/20260824-20260831-vehicle_incentives-Samvreeddhi_Mobility_Pvt_Ltd_HYD_P.xlsx",
    "https://storage.googleapis.com/letzryd-uber-reports/daily_exports/2026-08-31/20260831-vehicle_incentives-SAMVREEDDHI_ALL_3_CITIES.xlsx",
    720.0
))
conn.commit()
print("✅ Ingestion log record created successfully in uber_incentives_ingestion_log!")

cur.close()
conn.close()

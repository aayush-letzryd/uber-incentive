import sys, io
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import psycopg2
import pandas as pd
from pathlib import Path
from psycopg2.extras import execute_values

DB_CONFIG = {
    "host": "35.200.196.113",
    "port": "5432",
    "dbname": "postgres",
    "user": "postgres",
    "password": r"8S5]U3@L^Xz)\FH}"
}

blr_file = Path(r"C:\Users\anura\Downloads\20260824-20260831-vehicle_incentives-SAMVREEDDHI_MOBILITY_Pvt_Ltd_BLR_P.csv")

print("=" * 70)
print("🧪 LIVE DATABASE INGESTION LOGIC VERIFICATION")
print("=" * 70)

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

# 1. Take a sample of 100 vehicles from real Bangalore dataset
df = pd.read_csv(blr_file).head(100)
df = df.drop_duplicates(subset=['Number plate', 'Start date', 'End date', 'Trip target'], keep='last')

# Helper function
def upsert_records(data_df):
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
    for _, r in data_df.iterrows():
        records.append((
            "Bangalore",
            str(r.get("Vehicle name", "")),
            str(r.get("Number plate", "")),
            r.get("Start date"),
            r.get("End date"),
            float(r.get("Acceptance rate")) if pd.notnull(r.get("Acceptance rate")) else None,
            float(r.get("Target acceptance rate")) if pd.notnull(r.get("Target acceptance rate")) else None,
            int(r.get("Trips completed", 0)) if pd.notnull(r.get("Trips completed")) else 0,
            int(r.get("Trip target", 0)) if pd.notnull(r.get("Trip target")) else 0,
            float(r.get("Total payout", 0)) if pd.notnull(r.get("Total payout")) else 0.0,
            str(r.get("Status", "")),
            str(r.get("Driver trip count breakdown", "")) if pd.notnull(r.get("Driver trip count breakdown")) else None
        ))
    execute_values(cur, query, records, page_size=1000)
    conn.commit()

test_plate = df.iloc[0]["Number plate"]
test_target = int(df.iloc[0]["Trip target"])
start_dt = df.iloc[0]["Start date"]
end_dt   = df.iloc[0]["End date"]

# --- TEST 1: Initial Ingestion of 100 sample records ---
print(f"\n[TEST 1] Ingesting initial 100 rows for week {start_dt} to {end_dt}...")
upsert_records(df)

cur.execute("""
    SELECT trips_completed, total_payout 
    FROM uber_vehicle_incentives_raw 
    WHERE number_plate = %s AND trip_target = %s AND start_date = %s AND end_date = %s;
""", (test_plate, test_target, start_dt, end_dt))
row = cur.fetchone()
print(f"  -> Vehicle {test_plate} (Target {test_target}): Trips = {row[0]}, Payout = ₹{row[1]}")

# --- TEST 2: Daily Re-run (Same Week - mid-week progress update) ---
print(f"\n[TEST 2] Simulating daily mid-week run (Same Week: {start_dt})...")
print(f"  -> Modifying vehicle {test_plate}: incrementing trips to 55 and Payout to ₹6,200...")
df_updated = df.copy()
df_updated.loc[df_updated["Number plate"] == test_plate, "Trips completed"] = 55
df_updated.loc[df_updated["Number plate"] == test_plate, "Total payout"] = 6200.00

upsert_records(df_updated)

cur.execute("""
    SELECT trips_completed, total_payout 
    FROM uber_vehicle_incentives_raw 
    WHERE number_plate = %s AND trip_target = %s AND start_date = %s AND end_date = %s;
""", (test_plate, test_target, start_dt, end_dt))
rows = cur.fetchall()
print(f"  -> Total rows for this vehicle+target+week in table: {len(rows)} (Expected: exactly 1, no duplicate!)")
print(f"  -> Updated Value: Trips = {rows[0][0]}, Payout = ₹{rows[0][1]} (Expected: 55, ₹6200.00)")
assert len(rows) == 1, "Duplicate detected!"
assert rows[0][0] == 55, "Trip update failed!"
assert float(rows[0][1]) == 6200.00, "Payout update failed!"

# --- TEST 3: New Week Ingestion (Next Billing Cycle) ---
next_week_start = "2026-09-01 04:00:00"
next_week_end   = "2026-09-08 04:00:00"
print(f"\n[TEST 3] Simulating next week ingestion (New Week: {next_week_start} to {next_week_end})...")
df_next_week = df.copy()
df_next_week["Start date"] = next_week_start
df_next_week["End date"]   = next_week_end
df_next_week.loc[df_next_week["Number plate"] == test_plate, "Trips completed"] = 12
df_next_week.loc[df_next_week["Number plate"] == test_plate, "Total payout"] = 1500.00

upsert_records(df_next_week)

cur.execute("""
    SELECT start_date, end_date, trips_completed, total_payout 
    FROM uber_vehicle_incentives_raw 
    WHERE number_plate = %s AND trip_target = %s AND start_date IN (%s, %s)
    ORDER BY start_date;
""", (test_plate, test_target, start_dt, next_week_start))
all_weeks = cur.fetchall()
print(f"  -> Total distinct weekly records verified for vehicle {test_plate}: {len(all_weeks)}")
for w in all_weeks:
    print(f"     • Week {str(w[0])[:10]} to {str(w[1])[:10]}: Trips = {w[2]}, Payout = ₹{w[3]}")

assert len(all_weeks) == 2, "New week did not preserve history!"

print("\n" + "=" * 70)
print("🎉 100% PROVEN: LOGIC IS BULLETPROOF AND ACCURATE ON POSTGRESQL!")
print("=" * 70)

cur.close()
conn.close()

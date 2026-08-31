import sys, io
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import os
import psycopg2

DB_CONFIG = {
    "host": os.getenv("PG_HOST", "35.200.196.113"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "dbname": os.getenv("PG_DATABASE", "postgres"),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", r"")
}

print("=" * 70)
print("🧹 CLEANING INCENTIVE TABLES IN POSTGRESQL FOR CLEAN CLOUD RUN")
print("=" * 70)

conn = None
cur = None
try:
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("TRUNCATE TABLE uber_vehicle_incentives_raw RESTART IDENTITY;")
    print("✅ Truncated table: uber_vehicle_incentives_raw (0 rows, ID reset to 1)")

    cur.execute("TRUNCATE TABLE uber_incentives_ingestion_log RESTART IDENTITY;")
    print("✅ Truncated table: uber_incentives_ingestion_log (0 rows, ID reset to 1)")

    conn.commit()

    cur.execute("SELECT count(*) FROM uber_vehicle_incentives_raw;")
    print(f"📊 Current row count in uber_vehicle_incentives_raw: {cur.fetchone()[0]}")

    cur.execute("SELECT count(*) FROM uber_incentives_ingestion_log;")
    print(f"📊 Current row count in uber_incentives_ingestion_log: {cur.fetchone()[0]}")

    print("\n🎉 Database is 100% clean and ready for Google Cloud production execution!")

except Exception as e:
    print(f"❌ Error during cleanup: {e}")
    if conn:
        conn.rollback()
finally:
    if cur: cur.close()
    if conn: conn.close()

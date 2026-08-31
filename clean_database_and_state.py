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

print("=" * 70)
print("🧹 CLEANING INCENTIVE TABLES IN POSTGRESQL FOR CLEAN CLOUD RUN")
print("=" * 70)

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

    cur.close()
    conn.close()
    print("\n🎉 Database is 100% clean and ready for Google Cloud production execution!")

except Exception as e:
    print(f"❌ Error during cleanup: {e}")

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

tables_to_inspect = [
    "raw_uber_incentives",
    "uber_incentive",
    "uber_pipeline_execution_logs",
    "ola_ingestion_log"
]

try:
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    for tbl in tables_to_inspect:
        print(f"\n================ TABLE: {tbl} ================")
        cur.execute(f"""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = '{tbl}'
            ORDER BY ordinal_position;
        """)
        cols = cur.fetchall()
        if cols:
            for col, dtype, null in cols:
                print(f"  • {col} ({dtype})")
        else:
            print("  (Table does not exist)")

    conn.close()

except Exception as e:
    print(f"Error: {e}")

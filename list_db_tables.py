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

try:
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    print("Connected to PostgreSQL successfully.\n")

    cur.execute("""
        SELECT table_schema, table_name, table_type
        FROM information_schema.tables
        WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
        ORDER BY table_schema, table_name;
    """)

    rows = cur.fetchall()
    print(f"📊 Total Tables/Views in Database: {len(rows)}\n")
    for schema, name, t_type in rows:
        print(f"  • [{t_type.upper()}] {schema}.{name}")

    conn.close()

except Exception as e:
    print(f"❌ DB Connection Error: {e}")

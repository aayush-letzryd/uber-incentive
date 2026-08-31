import os
import psycopg2

conn = None
cur = None
try:
    conn = psycopg2.connect(
        host=os.getenv('PG_HOST', '35.200.196.113'),
        port=int(os.getenv('PG_PORT', '5432')),
        dbname=os.getenv('PG_DATABASE', 'postgres'),
        user=os.getenv('PG_USER', 'postgres'),
        password=os.getenv('PG_PASSWORD', r'')
    )
    cur = conn.cursor()

    cur.execute("""
        SELECT number_plate, start_date, end_date, trip_target, total_payout, trips_completed, count(*)
        FROM uber_vehicle_incentives_raw
        WHERE number_plate = 'KA51AM3848'
        GROUP BY number_plate, start_date, end_date, trip_target, total_payout, trips_completed;
    """)

    rows = cur.fetchall()
    print(f"Rows for KA51AM3848: {len(rows)}")
    for r in rows:
        print(r)
finally:
    if cur: cur.close()
    if conn: conn.close()

import psycopg2

conn = psycopg2.connect(host='35.200.196.113', port='5432', dbname='postgres', user='postgres', password=r'8S5]U3@L^Xz)\FH}')
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

conn.close()

"""
LETZRYD · UBER VEHICLE INCENTIVES CLOUD RUNNER (PRODUCTION v4.0)
================================================================
Orchestrates:
1. Hourly Retry Triggers (07:00, 08:00, 09:00, 10:00 IST)
2. State idempotency (exits instantly if already succeeded today)
3. Uber Official CSV Download across Bangalore, Mumbai, Hyderabad
4. Multi-city Excel generation & Master 3-City Consolidation
5. GCS Cloud Storage Bucket Upload
6. PostgreSQL Database Upsert Ingestion
7. Green Success Email (on 1st success) & Red Failure Alert (only after final retry)
"""

import sys, io
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import os
import time
import json
import shutil
import datetime
from pathlib import Path
import pandas as pd

from mailer import send_success_email, send_failure_email

# Optional GCS & PostgreSQL imports
try:
    from google.cloud import storage
    HAS_GCS = True
except ImportError:
    HAS_GCS = False

try:
    import psycopg2
    from psycopg2.extras import execute_values
    HAS_PG = True
except ImportError:
    HAS_PG = False

# ==============================================================================
# CONFIGURATION
# ==============================================================================
BUCKET_NAME  = os.getenv("GCS_BUCKET_NAME", "letzryd-uber-reports")
DATABASE_URL = os.getenv("DATABASE_URL", "")
RECIPIENTS   = [r.strip() for r in os.getenv("EMAIL_RECIPIENTS", "vendor_aayush@letzryd.com").split(",") if r.strip()]

BASE        = Path(__file__).parent
OUT_DIR     = BASE / "uber_reports"
STATE_DIR   = BASE / "state"

for d in [OUT_DIR, STATE_DIR]:
    d.mkdir(exist_ok=True)


def get_today_str():
    return datetime.datetime.now().strftime("%Y-%m-%d")


def check_gcs_state(today_str: str) -> dict:
    """Checks if today's ingestion has already succeeded."""
    local_state_file = STATE_DIR / f"{today_str}.json"
    if local_state_file.exists():
        try:
            return json.loads(local_state_file.read_text())
        except Exception:
            pass

    if HAS_GCS and os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        try:
            client = storage.Client()
            bucket = client.bucket(BUCKET_NAME)
            blob = bucket.blob(f"state/{today_str}.json")
            if blob.exists():
                data = json.loads(blob.download_as_text())
                local_state_file.write_text(json.dumps(data))
                return data
        except Exception as e:
            print(f"[*] GCS state check note: {e}", flush=True)

    return {"status": "PENDING", "attempts": 0}


def save_gcs_state(today_str: str, state_data: dict):
    local_state_file = STATE_DIR / f"{today_str}.json"
    local_state_file.write_text(json.dumps(state_data, indent=2))

    if HAS_GCS and os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        try:
            client = storage.Client()
            bucket = client.bucket(BUCKET_NAME)
            blob = bucket.blob(f"state/{today_str}.json")
            blob.upload_from_string(json.dumps(state_data, indent=2), content_type="application/json")
        except Exception as e:
            print(f"[*] GCS state save note: {e}", flush=True)


def upload_reports_to_gcs(today_str: str, files_to_upload: list[Path]) -> list[str]:
    """Uploads individual and master CSV & Excel files to GCS."""
    uploaded_urls = []
    if not (HAS_GCS and os.getenv("GOOGLE_APPLICATION_CREDENTIALS")):
        print("[*] GCS credentials not present locally, skipped cloud bucket upload.", flush=True)
        return uploaded_urls

    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        for f in files_to_upload:
            if f.exists():
                blob_path = f"daily_exports/{today_str}/{f.name}"
                blob = bucket.blob(blob_path)
                blob.upload_from_filename(str(f))
                print(f"☁️ Uploaded to GCS: gs://{BUCKET_NAME}/{blob_path}", flush=True)
                uploaded_urls.append(f"gs://{BUCKET_NAME}/{blob_path}")
    except Exception as e:
        print(f"[-] GCS upload error: {e}", flush=True)
    return uploaded_urls


def ingest_df_to_postgres(df: pd.DataFrame, city: str):
    """Upserts incentives DataFrame to PostgreSQL table."""
    if not (HAS_PG and DATABASE_URL):
        return

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        query = """
        INSERT INTO uber_vehicle_incentives_raw (
            city, vehicle_name, number_plate, start_date, end_date,
            acceptance_rate, target_acceptance_rate, trips_completed,
            trip_target, total_payout, status, driver_trip_count_breakdown
        ) VALUES %s
        ON CONFLICT (city, number_plate, start_date, end_date) DO UPDATE SET
            acceptance_rate = EXCLUDED.acceptance_rate,
            target_acceptance_rate = EXCLUDED.target_acceptance_rate,
            trips_completed = EXCLUDED.trips_completed,
            trip_target = EXCLUDED.trip_target,
            total_payout = EXCLUDED.total_payout,
            status = EXCLUDED.status,
            driver_trip_count_breakdown = EXCLUDED.driver_trip_count_breakdown,
            ingested_at = CURRENT_TIMESTAMP;
        """

        records = []
        for _, r in df.iterrows():
            records.append((
                city,
                str(r.get("Vehicle name", "")),
                str(r.get("Number plate", "")),
                r.get("Start date"),
                r.get("End date"),
                float(r.get("Acceptance rate", 0)) if pd.notnull(r.get("Acceptance rate")) else None,
                float(r.get("Target acceptance rate", 0)) if pd.notnull(r.get("Target acceptance rate")) else None,
                int(r.get("Trips completed", 0)) if pd.notnull(r.get("Trips completed")) else 0,
                int(r.get("Trip target", 0)) if pd.notnull(r.get("Trip target")) else 0,
                float(r.get("Total payout", 0)) if pd.notnull(r.get("Total payout")) else 0.0,
                str(r.get("Status", "")),
                str(r.get("Driver trip count breakdown", "")) if pd.notnull(r.get("Driver trip count breakdown")) else None
            ))

        execute_values(cur, query, records)
        conn.commit()
        cur.close()
        conn.close()
        print(f"🗄️ Ingested {len(records):,} records into PostgreSQL ({city})", flush=True)
    except Exception as e:
        print(f"[-] Database ingestion error: {e}", flush=True)


def run_pipeline():
    today_str = get_today_str()
    state = check_gcs_state(today_str)

    # 1. Check if already succeeded today
    if state.get("status") == "SUCCESS":
        print(f"✅ [IDEMPOTENT] Today's Uber Incentives ({today_str}) already successfully ingested on Attempt {state.get('attempts', 1)}.")
        print("⚡ Exiting immediately with 0 extra compute.")
        return

    current_attempt = state.get("attempts", 0) + 1
    print(f"\n==========================================================")
    print(f"   STARTING UBER INCENTIVES PIPELINE - ATTEMPT {current_attempt} of 4")
    print(f"   Date: {today_str} | Time: {datetime.datetime.now().strftime('%H:%M:%S IST')}")
    print(f"==========================================================")

    start_time = time.time()
    success = False
    error_reason = ""

    try:
        import uber_full_automation
        uber_full_automation.main()

        # Check output directory for master report
        master_files = list(OUT_DIR.glob(f"*{today_str.replace('-', '')}*ALL_3_CITIES.xlsx"))
        if not master_files:
            master_files = list(OUT_DIR.glob(f"*ALL_3_CITIES.xlsx"))

        if master_files:
            master_path = master_files[0]
            master_df = pd.read_excel(master_path)

            # Ingest to DB
            for city in master_df["City"].unique():
                city_df = master_df[master_df["City"] == city]
                ingest_df_to_postgres(city_df, city)

            # Upload all files to GCS Bucket
            all_reports = list(OUT_DIR.glob("*.xlsx")) + list(OUT_DIR.glob("*.csv"))
            upload_reports_to_gcs(today_str, all_reports)

            # Row stats
            blr_rows = len(master_df[master_df["City"] == "Bangalore"])
            mum_rows = len(master_df[master_df["City"] == "Mumbai"])
            hyd_rows = len(master_df[master_df["City"] == "Hyderabad"])
            total_rows = len(master_df)

            start_dt = str(master_df["Start date"].iloc[0])[:10] if "Start date" in master_df.columns and len(master_df) > 0 else today_str
            end_dt   = str(master_df["End date"].iloc[0])[:10] if "End date" in master_df.columns and len(master_df) > 0 else today_str
            date_window = f"{start_dt} to {end_dt}"
            duration_str = f"{(time.time() - start_time) / 60:.1f} minutes"

            # Dispatch Green Success Email with Master Report Attached
            send_success_email(
                date_window=date_window,
                blr_rows=blr_rows,
                mum_rows=mum_rows,
                hyd_rows=hyd_rows,
                total_rows=total_rows,
                duration_str=duration_str,
                attachment_paths=[master_path],
                recipients=RECIPIENTS
            )

            # Mark state as SUCCESS
            state["status"] = "SUCCESS"
            state["attempts"] = current_attempt
            state["completed_at"] = datetime.datetime.now().isoformat()
            save_gcs_state(today_str, state)
            success = True

    except Exception as e:
        error_reason = str(e)
        print(f"[-] Execution error during attempt {current_attempt}: {e}", flush=True)

    if not success:
        state["status"] = "FAILED"
        state["attempts"] = current_attempt
        state["last_error"] = error_reason
        save_gcs_state(today_str, state)

        # Only send failure alert if this is the 4th (final) attempt
        if current_attempt >= 4:
            print(f"🚨 Final attempt {current_attempt} failed. Dispatching Red Alert Email to operations team...")
            send_failure_email(
                date_window=today_str,
                failure_reason=f"Statement export could not be secured from Uber portal after all {current_attempt} retry attempts. Last error: {error_reason}",
                attempts_count=current_attempt,
                recipients=RECIPIENTS
            )
        else:
            print(f"⚠️ Attempt {current_attempt} failed. Waiting for next hourly retry trigger (Attempt {current_attempt + 1}). No alert email sent yet.")


if __name__ == "__main__":
    run_pipeline()

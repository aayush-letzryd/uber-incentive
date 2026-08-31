"""
LETZRYD · UBER VEHICLE INCENTIVES CLOUD RUNNER (PRODUCTION v4.1)
================================================================
Orchestrates:
1. Retry Triggers: 07:00 AM, 08:10 AM, 09:00 AM, 10:00 AM IST
2. State idempotency (exits instantly if already succeeded today)
3. Uber Official CSV Download across Bangalore, Mumbai, Hyderabad
4. Multi-city Excel generation & Master 3-City Consolidation
5. GCS Cloud Storage Bucket Upload (all 3 cities + combined)
6. PostgreSQL Database Upsert Ingestion (data + log table with bucket URLs)
7. Green Success Email (with GCS download links for all 3 cities & master, no heavy attachments)
8. Red Failure Alert (only after 4th final retry fails)
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


def upload_reports_to_gcs(today_str: str, files_to_upload: list[Path]) -> dict[str, str]:
    """Uploads individual and master CSV & Excel files to GCS and returns mapping."""
    uploaded_urls = {}
    if not (HAS_GCS and os.getenv("GOOGLE_APPLICATION_CREDENTIALS")):
        for f in files_to_upload:
            uploaded_urls[f.name] = f"https://storage.googleapis.com/{BUCKET_NAME}/daily_exports/{today_str}/{f.name}"
        return uploaded_urls

    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        for f in files_to_upload:
            if f.exists():
                blob_path = f"daily_exports/{today_str}/{f.name}"
                blob = bucket.blob(blob_path)
                blob.upload_from_filename(str(f))
                public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{blob_path}"
                uploaded_urls[f.name] = public_url
                print(f"☁️ Uploaded to GCS: {public_url}", flush=True)
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

        # Deduplicate on constraint columns
        clean_df = df.drop_duplicates(subset=['Number plate', 'Start date', 'End date', 'Trip target'], keep='last')

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
        for _, r in clean_df.iterrows():
            records.append((
                city,
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

        execute_values(cur, query, records, page_size=2000)
        conn.commit()
        cur.close()
        conn.close()
        print(f"🗄️ Ingested {len(records):,} records into PostgreSQL ({city})", flush=True)
    except Exception as e:
        print(f"[-] Database ingestion error: {e}", flush=True)


def log_execution_to_postgres(
    today_str: str,
    attempt: int,
    status: str,
    start_dt: str,
    end_dt: str,
    blr_rows: int,
    mum_rows: int,
    hyd_rows: int,
    total_rows: int,
    blr_url: str,
    mum_url: str,
    hyd_url: str,
    master_url: str,
    duration_sec: float,
    error_msg: str = None
):
    """Inserts a run record into the uber_ingestion_logs table."""
    if not (HAS_PG and DATABASE_URL):
        return

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        query = """
        INSERT INTO uber_ingestion_logs (
            execution_date, attempt_number, status, date_window_start, date_window_end,
            blr_rows, mum_rows, hyd_rows, total_rows,
            blr_file_url, mum_file_url, hyd_file_url, master_file_url,
            execution_duration_sec, error_message
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """

        cur.execute(query, (
            today_str, attempt, status, start_dt, end_dt,
            blr_rows, mum_rows, hyd_rows, total_rows,
            blr_url, mum_url, hyd_url, master_url,
            duration_sec, error_msg
        ))
        conn.commit()
        cur.close()
        conn.close()
        print("🗄️ Logged execution details into uber_ingestion_logs", flush=True)
    except Exception as e:
        print(f"[-] DB logging error: {e}", flush=True)


def run_pipeline():
    today_str = get_today_str()
    state = check_gcs_state(today_str)

    # 1. Idempotency check
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
            uploaded_urls = upload_reports_to_gcs(today_str, all_reports)

            # Match city URLs
            blr_url = next((u for k, u in uploaded_urls.items() if "blr" in k.lower() and k.endswith(".xlsx")), "#")
            mum_url = next((u for k, u in uploaded_urls.items() if "mum" in k.lower() and k.endswith(".xlsx")), "#")
            hyd_url = next((u for k, u in uploaded_urls.items() if "hyd" in k.lower() and k.endswith(".xlsx")), "#")
            master_url = next((u for k, u in uploaded_urls.items() if "all_3_cities" in k.lower() and k.endswith(".xlsx")), "#")

            # Row stats
            blr_rows = len(master_df[master_df["City"] == "Bangalore"])
            mum_rows = len(master_df[master_df["City"] == "Mumbai"])
            hyd_rows = len(master_df[master_df["City"] == "Hyderabad"])
            total_rows = len(master_df)

            start_dt = str(master_df["Start date"].iloc[0])[:10] if "Start date" in master_df.columns and len(master_df) > 0 else today_str
            end_dt   = str(master_df["End date"].iloc[0])[:10] if "End date" in master_df.columns and len(master_df) > 0 else today_str
            date_window = f"{start_dt} to {end_dt}"
            duration_sec = time.time() - start_time
            duration_str = f"{duration_sec / 60:.1f} minutes"

            # Log to DB log table
            log_execution_to_postgres(
                today_str=today_str,
                attempt=current_attempt,
                status="SUCCESS",
                start_dt=start_dt,
                end_dt=end_dt,
                blr_rows=blr_rows,
                mum_rows=mum_rows,
                hyd_rows=hyd_rows,
                total_rows=total_rows,
                blr_url=blr_url,
                mum_url=mum_url,
                hyd_url=hyd_url,
                master_url=master_url,
                duration_sec=duration_sec
            )

            # Dispatch Green Success Email with direct GCS download links (no heavy attachments)
            send_success_email(
                date_window=date_window,
                blr_rows=blr_rows,
                mum_rows=mum_rows,
                hyd_rows=hyd_rows,
                total_rows=total_rows,
                duration_str=duration_str,
                blr_file_url=blr_url,
                mum_file_url=mum_url,
                hyd_file_url=hyd_url,
                master_file_url=master_url,
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
        duration_sec = time.time() - start_time
        state["status"] = "FAILED"
        state["attempts"] = current_attempt
        state["last_error"] = error_reason
        save_gcs_state(today_str, state)

        # Log failed attempt to DB log table
        log_execution_to_postgres(
            today_str=today_str,
            attempt=current_attempt,
            status="FAILED",
            start_dt=today_str,
            end_dt=today_str,
            blr_rows=0,
            mum_rows=0,
            hyd_rows=0,
            total_rows=0,
            blr_url="",
            mum_url="",
            hyd_url="",
            master_url="",
            duration_sec=duration_sec,
            error_msg=error_reason
        )

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
            print(f"⚠️ Attempt {current_attempt} failed. Waiting for next retry trigger (Attempt {current_attempt + 1}). No alert email sent yet.")


if __name__ == "__main__":
    run_pipeline()

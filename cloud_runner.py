"""
LETZRYD · UBER VEHICLE INCENTIVES CLOUD RUNNER (PRODUCTION v4.2)
================================================================
Orchestrates:
1. Retry Triggers: 07:00 AM, 08:10 AM, 09:10 AM, 10:10 AM IST
2. State idempotency (exits instantly if already succeeded today)
3. Session cookie sync to/from GCS bucket
4. Uber Official CSV Download across Bangalore, Mumbai, Hyderabad
5. Multi-city Excel generation & Master 3-City Consolidation
6. GCS Cloud Storage Bucket Upload (all 3 cities + combined)
7. PostgreSQL Database Upsert Ingestion (data + log table with bucket URLs)
8. Green Success Email (with GCS download links for all 3 cities & master, no heavy attachments)
9. Red Failure Alert (only after 4th final retry fails)
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

# GCS & PostgreSQL imports
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
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:8S5%5DU3%40L%5EXz%29%5CFH%7D@35.200.196.113:5432/postgres")
RECIPIENTS   = [r.strip() for r in os.getenv("EMAIL_RECIPIENTS", "vendor_aayush@letzryd.com").split(",") if r.strip()]

BASE        = Path(__file__).parent
OUT_DIR     = BASE / "uber_reports"
STATE_DIR   = BASE / "state"
COOKIES_F   = BASE / "cookies.json"
STATE_F     = BASE / "storage_state.json"

for d in [OUT_DIR, STATE_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def get_gcs_client():
    if not HAS_GCS:
        return None
    try:
        return storage.Client()
    except Exception as e:
        print(f"[*] GCS client init note: {e}", flush=True)
        return None


def sync_cookies_from_gcs():
    """Downloads saved session cookies from GCS bucket if running in fresh container."""
    client = get_gcs_client()
    if not client:
        return

    try:
        bucket = client.bucket(BUCKET_NAME)
        for fname, local_path in [("cookies.json", COOKIES_F), ("storage_state.json", STATE_F)]:
            blob = bucket.blob(f"sessions/{fname}")
            if blob.exists():
                blob.download_to_filename(str(local_path))
                print(f"🔑 Synced {fname} from gs://{BUCKET_NAME}/sessions/", flush=True)
    except Exception as e:
        print(f"[*] Cookie download from GCS note: {e}", flush=True)


def sync_cookies_to_gcs():
    """Uploads active session cookies to GCS bucket to persist between ephemeral container runs."""
    client = get_gcs_client()
    if not client:
        return

    try:
        bucket = client.bucket(BUCKET_NAME)
        for fname, local_path in [("cookies.json", COOKIES_F), ("storage_state.json", STATE_F)]:
            if local_path.exists():
                blob = bucket.blob(f"sessions/{fname}")
                blob.upload_from_filename(str(local_path))
                print(f"☁️ Backed up {fname} to gs://{BUCKET_NAME}/sessions/", flush=True)
    except Exception as e:
        print(f"[*] Cookie backup to GCS note: {e}", flush=True)


def get_today_str():
    return datetime.datetime.now().strftime("%Y-%m-%d")


def check_gcs_state(today_str: str) -> dict:
    local_state_file = STATE_DIR / f"{today_str}.json"
    if local_state_file.exists():
        try:
            return json.loads(local_state_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    client = get_gcs_client()
    if client:
        try:
            bucket = client.bucket(BUCKET_NAME)
            blob = bucket.blob(f"state/{today_str}.json")
            if blob.exists():
                data = json.loads(blob.download_as_text())
                local_state_file.write_text(json.dumps(data), encoding="utf-8")
                return data
        except Exception as e:
            print(f"[*] GCS state check note: {e}", flush=True)

    return {"status": "PENDING", "attempts": 0}


def save_gcs_state(today_str: str, state_data: dict):
    local_state_file = STATE_DIR / f"{today_str}.json"
    local_state_file.write_text(json.dumps(state_data, indent=2), encoding="utf-8")

    client = get_gcs_client()
    if client:
        try:
            bucket = client.bucket(BUCKET_NAME)
            blob = bucket.blob(f"state/{today_str}.json")
            blob.upload_from_string(json.dumps(state_data, indent=2), content_type="application/json")
        except Exception as e:
            print(f"[*] GCS state save note: {e}", flush=True)


def upload_reports_to_gcs(today_str: str, files_to_upload: list[Path]) -> dict[str, str]:
    """Uploads individual and master CSV & Excel files to GCS and returns mapping."""
    uploaded_urls = {}
    client = get_gcs_client()

    for f in files_to_upload:
        if f.exists():
            blob_path = f"daily_exports/{today_str}/{f.name}"
            public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{blob_path}"
            if client:
                try:
                    bucket = client.bucket(BUCKET_NAME)
                    blob = bucket.blob(blob_path)
                    blob.upload_from_filename(str(f))
                    print(f"☁️ Uploaded to GCS: {public_url}", flush=True)
                except Exception as e:
                    print(f"[-] GCS upload error for {f.name}: {e}", flush=True)
            uploaded_urls[f.name] = public_url
    return uploaded_urls


# Field cleaning helpers for database safety
def clean_str(val):
    if pd.isna(val) or val is None:
        return None
    s = str(val).strip()
    return s if s and s.lower() != "nan" else None

def clean_float(val):
    if pd.isna(val) or val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace("%", "").replace("₹", "").replace(",", "").strip()
    try:
        return float(s)
    except Exception:
        return None

def clean_int(val, default=0):
    if pd.isna(val) or val is None:
        return default
    if isinstance(val, int):
        return val
    s = str(val).replace(",", "").strip()
    try:
        return int(float(s))
    except Exception:
        return default

def clean_timestamp(val):
    if pd.isna(val) or val is None:
        return None
    try:
        dt = pd.to_datetime(val)
        if pd.isna(dt):
            return None
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def ingest_df_to_postgres(df: pd.DataFrame, city: str):
    """Upserts incentives DataFrame to PostgreSQL table."""
    if not (HAS_PG and DATABASE_URL):
        return

    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        clean_df = df.copy()
        clean_df.columns = clean_df.columns.str.strip()

        required_subset = [c for c in ['Number plate', 'Start date', 'End date', 'Trip target'] if c in clean_df.columns]
        if len(required_subset) == 4:
            clean_df = clean_df.drop_duplicates(subset=required_subset, keep='last')

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
            plate = clean_str(r.get("Number plate"))
            if not plate:
                continue

            start_dt = clean_timestamp(r.get("Start date")) or clean_timestamp(datetime.date.today())
            end_dt   = clean_timestamp(r.get("End date")) or start_dt

            records.append((
                city,
                clean_str(r.get("Vehicle name")),
                plate,
                start_dt,
                end_dt,
                clean_float(r.get("Acceptance rate")),
                clean_float(r.get("Target acceptance rate")),
                clean_int(r.get("Trips completed"), 0),
                clean_int(r.get("Trip target"), 0),
                clean_float(r.get("Total payout")) or 0.0,
                clean_str(r.get("Status")),
                clean_str(r.get("Driver trip count breakdown"))
            ))

        if records:
            execute_values(cur, query, records, page_size=2000)
            conn.commit()
            print(f"🗄️ Ingested {len(records):,} records into PostgreSQL ({city})", flush=True)
        cur.close()
    except Exception as e:
        print(f"[-] Database ingestion error: {e}", flush=True)
    finally:
        if conn:
            try: conn.close()
            except Exception: pass


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
    """Inserts a run record into the uber_incentives_ingestion_log table."""
    if not (HAS_PG and DATABASE_URL):
        return

    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        query = """
        INSERT INTO uber_incentives_ingestion_log (
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
        print("🗄️ Logged execution details into uber_incentives_ingestion_log", flush=True)
    except Exception as e:
        print(f"[-] DB logging error: {e}", flush=True)
    finally:
        if conn:
            try: conn.close()
            except Exception: pass


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

    # Sync cookies from GCS before launching browser
    sync_cookies_from_gcs()

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

        if not master_files:
            raise RuntimeError(f"Automation executed but no Master Excel file was found in {OUT_DIR}")

        master_path = master_files[0]
        master_df = pd.read_excel(master_path)

        # Ingest each city to DB
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

        # Dispatch Green Success Email with direct GCS download links
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

        # Back up active session cookies to GCS
        sync_cookies_to_gcs()

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

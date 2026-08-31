"""
LETZRYD · UBER VEHICLE INCENTIVES CLOUD RUNNER (PRODUCTION v4.7)
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
import re
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

# =======================================================
# CONFIGURATION
# =======================================================
BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "letzryd-uber-reports")
STATE_BLOB_NAME = "pipeline_state.json"
COOKIES_BLOB_NAME = "session/cookies.json"
STORAGE_STATE_BLOB_NAME = "session/storage_state.json"

# ── Secrets: sourced from GCP Secret Manager via Cloud Run --set-secrets ──
# DO NOT add hardcoded fallback values here — inject via Secret Manager in deploy_gcp.sh
PG_HOST     = os.getenv("PG_HOST", "")      # Set via: --set-env-vars PG_HOST=... in deploy_gcp.sh
PG_PORT     = int(os.getenv("PG_PORT", "5432"))
PG_DATABASE = os.getenv("PG_DATABASE", "postgres")
PG_USER     = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")   # Set via: --set-secrets PG_PASSWORD=PG_PASSWORD:latest
if not PG_HOST and HAS_PG:
    print("[-] WARNING: PG_HOST not set — database operations will be skipped.")

RECIPIENTS = [r.strip() for r in os.getenv("EMAIL_RECIPIENTS", "vendor_aayush@letzryd.com").split(",") if r.strip()]

BASE_DIR = Path(__file__).parent
OUT_DIR = BASE_DIR / "uber_reports"
COOKIES_F = BASE_DIR / "cookies.json"
STATE_F = BASE_DIR / "storage_state.json"

OUT_DIR.mkdir(parents=True, exist_ok=True)


def get_gcs_client():
    if not HAS_GCS:
        return None
    try:
        return storage.Client()
    except Exception as e:
        print(f"[-] GCS client initialization note: {e}", flush=True)
        return None


def get_db_connection():
    if not HAS_PG:
        print("[-] psycopg2 is not installed. Database operations skipped.")
        return None
    try:
        conn = psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            dbname=PG_DATABASE,
            user=PG_USER,
            password=PG_PASSWORD,
            connect_timeout=15
        )
        return conn
    except Exception as e:
        print(f"[-] PostgreSQL connection error: {e}", flush=True)
        return None


def sync_cookies_from_gcs():
    client = get_gcs_client()
    if not client:
        return
    try:
        bucket = client.bucket(BUCKET_NAME)
        # Check both session/ and sessions/ paths
        for blob_path in ["session/cookies.json", "sessions/cookies.json", "cookies.json"]:
            blob = bucket.blob(blob_path)
            if blob.exists():
                blob.download_to_filename(str(COOKIES_F))
                print(f"[+] Downloaded latest cookies from gs://{BUCKET_NAME}/{blob_path}")
                break

        for blob_path in ["session/storage_state.json", "sessions/storage_state.json", "storage_state.json"]:
            blob = bucket.blob(blob_path)
            if blob.exists():
                blob.download_to_filename(str(STATE_F))
                print(f"[+] Downloaded storage_state from gs://{BUCKET_NAME}/{blob_path}")
                break
    except Exception as e:
        print(f"[-] Note syncing session from GCS: {e}")


def sync_cookies_to_gcs():
    client = get_gcs_client()
    if not client:
        return
    try:
        bucket = client.bucket(BUCKET_NAME)
        # Prevent 0-byte or corrupted session file uploads
        if COOKIES_F.exists() and COOKIES_F.stat().st_size > 50:
            bucket.blob(COOKIES_BLOB_NAME).upload_from_filename(str(COOKIES_F))
            print(f"[+] Uploaded updated cookies to gs://{BUCKET_NAME}/{COOKIES_BLOB_NAME}")
        if STATE_F.exists() and STATE_F.stat().st_size > 50:
            bucket.blob(STORAGE_STATE_BLOB_NAME).upload_from_filename(str(STATE_F))
            print(f"[+] Uploaded updated storage_state to gs://{BUCKET_NAME}/{STORAGE_STATE_BLOB_NAME}")
    except Exception as e:
        print(f"[-] Note uploading session to GCS: {e}")


def load_gcs_state(today_str: str) -> dict:
    client = get_gcs_client()
    if not client:
        return {"date": today_str, "status": "NOT_STARTED", "attempts": 0}
    try:
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(f"state/{today_str}/{STATE_BLOB_NAME}")
        if blob.exists():
            data = json.loads(blob.download_as_text())
            return data
    except Exception as e:
        print(f"[-] Note reading state from GCS: {e}")
    return {"date": today_str, "status": "NOT_STARTED", "attempts": 0}


def save_gcs_state(today_str: str, state: dict):
    client = get_gcs_client()
    if not client:
        return
    try:
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(f"state/{today_str}/{STATE_BLOB_NAME}")
        blob.upload_from_string(json.dumps(state, indent=2), content_type="application/json")
        print(f"[+] State successfully saved to GCS: gs://{BUCKET_NAME}/state/{today_str}/{STATE_BLOB_NAME}")
    except Exception as e:
        print(f"[-] Note saving state to GCS: {e}")


def upload_reports_to_gcs(today_str: str) -> dict:
    urls = {}
    client = get_gcs_client()
    if not client:
        print("[-] GCS client unavailable; skipping upload.")
        return urls

    try:
        bucket = client.bucket(BUCKET_NAME)
        for f in OUT_DIR.glob("*"):
            if f.is_file() and (f.suffix in [".csv", ".xlsx"]):
                blob_name = f"reports/{today_str}/{f.name}"
                blob = bucket.blob(blob_name)
                content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if f.suffix == ".xlsx" else "text/csv"
                blob.upload_from_filename(str(f), content_type=content_type)
                public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{blob_name}"
                urls[f.name] = public_url
                print(f"[+] Uploaded {f.name} -> {public_url}")
    except Exception as e:
        print(f"[-] Error uploading reports to GCS: {e}")

    return urls


def clean_num(val, default=0.0, max_val=None):
    if pd.isna(val) or val is None or str(val).strip() in ("", "-", "NA", "N/A", "nan", "NaN"):
        return default
    try:
        cleaned = re.sub(r"[^\d.-]", "", str(val))
        if not cleaned:
            return default
        num = float(cleaned)
        if max_val is not None:
            num = min(num, max_val)
        return num
    except Exception:
        return default



def clean_timestamp(val):
    """Parse Uber date strings (DD/MM/YYYY or YYYY-MM-DD) into ISO timestamp string for PostgreSQL."""
    if pd.isna(val) or val is None or str(val).strip() in ("", "-", "NA", "nan", "NaN"):
        return None
    try:
        s = str(val).strip()
        # Try strict date formats first (Uber India format e.g. "01/09/2026", ISO, etc.)
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d", "%d %b %Y", "%d %B %Y"):
            try:
                return datetime.datetime.strptime(s[:10], fmt).strftime("%Y-%m-%d 00:00:00")
            except ValueError:
                continue
        # Fallback to pandas parser
        ts = pd.to_datetime(s, errors="coerce")
        if pd.isna(ts):
            return None
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def upsert_master_to_postgres(master_xlsx_path: Path) -> int:
    conn = get_db_connection()
    if not conn:
        print("[-] DB connection unavailable; skipping ingestion.")
        return 0

    IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    cur = None
    try:
        df = pd.read_excel(master_xlsx_path)
        print(f"[*] Ingesting {len(df):,} total rows from {master_xlsx_path.name} into PostgreSQL...")

        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        rows_dict = {}
        now_ts = datetime.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")  # IST-aware ingested_at

        for _, row in df.iterrows():
            city = str(row.get("city", "")).strip() or "Unknown"
            vehicle_name = str(row.get("vehicle_name", "")).strip()
            number_plate = str(row.get("number_plate", "")).strip()
            start_date = clean_timestamp(row.get("start_date"))
            end_date = clean_timestamp(row.get("end_date"))

            acceptance_rate = clean_num(row.get("acceptance_rate"), default=None, max_val=100.0)
            target_acceptance_rate = clean_num(row.get("target_acceptance_rate"), default=None, max_val=100.0)
            trips_completed = int(clean_num(row.get("trips_completed"), 0))
            trip_target = int(clean_num(row.get("trip_target"), 0))
            total_payout = clean_num(row.get("total_payout"), 0.0)
            status = str(row.get("status", "")).strip()
            driver_trip_breakdown = str(row.get("driver_trip_count_breakdown", "")).strip() if pd.notna(row.get("driver_trip_count_breakdown")) else None

            if not number_plate or not start_date or not end_date:
                continue

            # Deduplicate by constraint key to prevent Postgres "ON CONFLICT DO UPDATE cannot affect row a second time" error
            key = (city, number_plate, start_date, end_date, trip_target)
            rows_dict[key] = (
                city,
                vehicle_name,
                number_plate,
                start_date,
                end_date,
                acceptance_rate,
                target_acceptance_rate,
                trips_completed,
                trip_target,
                total_payout,
                status,
                driver_trip_breakdown,
                now_ts
            )

        rows_to_insert = list(rows_dict.values())
        print(f"[*] Prepared {len(rows_to_insert):,} unique deduplicated records for PostgreSQL (filtered {len(df) - len(rows_to_insert)} duplicates from Uber CSV).")

        if not rows_to_insert:
            print("[!] No valid rows prepared for ingestion.")
            return 0

        upsert_sql = """
        INSERT INTO uber_vehicle_incentives_raw (
            city,
            vehicle_name,
            number_plate,
            start_date,
            end_date,
            acceptance_rate,
            target_acceptance_rate,
            trips_completed,
            trip_target,
            total_payout,
            status,
            driver_trip_count_breakdown,
            ingested_at
        ) VALUES %s
        ON CONFLICT (city, number_plate, start_date, end_date, trip_target)
        DO UPDATE SET
            vehicle_name = EXCLUDED.vehicle_name,
            acceptance_rate = EXCLUDED.acceptance_rate,
            target_acceptance_rate = EXCLUDED.target_acceptance_rate,
            trips_completed = EXCLUDED.trips_completed,
            total_payout = EXCLUDED.total_payout,
            status = EXCLUDED.status,
            driver_trip_count_breakdown = EXCLUDED.driver_trip_count_breakdown,
            ingested_at = EXCLUDED.ingested_at;
        """

        cur = conn.cursor()
        execute_values(cur, upsert_sql, rows_to_insert, page_size=2000)
        conn.commit()

        print(f"✅ Successfully ingested / upserted {len(rows_to_insert):,} rows into 'uber_vehicle_incentives_raw'!")
        return len(rows_to_insert)

    except Exception as e:
        print(f"[-] Error during PostgreSQL ingestion: {e}", flush=True)
        if conn:
            conn.rollback()
        raise e
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


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
    conn = get_db_connection()
    if not conn:
        return
    cur = None
    try:
        cur = conn.cursor()
        insert_sql = """
        INSERT INTO uber_incentives_ingestion_log (
            execution_date,
            attempt_number,
            status,
            date_window_start,
            date_window_end,
            blr_rows,
            mum_rows,
            hyd_rows,
            total_rows,
            blr_file_url,
            mum_file_url,
            hyd_file_url,
            master_file_url,
            execution_duration_sec,
            error_message
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """
        cur.execute(insert_sql, (
            today_str,
            attempt,
            status,
            start_dt,
            end_dt,
            blr_rows,
            mum_rows,
            hyd_rows,
            total_rows,
            blr_url,
            mum_url,
            hyd_url,
            master_url,
            float(duration_sec),
            error_msg
        ))
        conn.commit()
        print(f"[+] Execution log recorded in 'uber_incentives_ingestion_log' table.")
    except Exception as e:
        print(f"[-] Error logging to PostgreSQL: {e}")
        if conn:
            conn.rollback()
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def run_pipeline():
    now_ist = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    today_str = now_ist.strftime("%Y-%m-%d")
    today_compact = today_str.replace("-", "")

    state = load_gcs_state(today_str)
    current_attempt = state.get("attempts", 0) + 1

    print("=" * 60)
    print(f"   STARTING UBER INCENTIVES PIPELINE - ATTEMPT {current_attempt} of 4")
    print(f"   Date: {today_str} | Time: {now_ist.strftime('%H:%M:%S')} IST")
    print("=" * 60)

    if state.get("status") == "SUCCESS":
        print(f"✅ Daily report for {today_str} has ALREADY SUCCEEDED in a previous run. Skipping execution.")
        return

    start_time = time.time()
    sync_cookies_from_gcs()

    success = False
    error_reason = ""

    try:
        import uber_full_automation
        print("\n[*] Invoking Uber Full Automation Engine...")
        uber_full_automation.main()

        # Check output directory strictly for today's generated master report
        master_files = [
            f for f in OUT_DIR.glob(f"*{today_compact}*ALL_3_CITIES.xlsx")
            if f.stat().st_mtime >= (start_time - 60)
        ]

        if not master_files:
            raise RuntimeError(f"Automation executed but today's Master Excel file ({today_compact}) was not found in {OUT_DIR}")

        master_path = master_files[0]
        print(f"[+] Located generated Master Excel: {master_path.name}")

        master_df = pd.read_excel(master_path)
        blr_rows = len(master_df[master_df["City"] == "Bangalore"])
        mum_rows = len(master_df[master_df["City"] == "Mumbai"])
        hyd_rows = len(master_df[master_df["City"] == "Hyderabad"])
        total_rows = len(master_df)

        print(f"[*] City Breakdown: Bangalore={blr_rows:,}, Mumbai={mum_rows:,}, Hyderabad={hyd_rows:,} | Total={total_rows:,}")

        if total_rows == 0:
            raise RuntimeError("Generated Master Excel is empty (0 rows).")

        # ── Extract real date window from CSV data (DD/MM/YYYY Uber India format) ──
        date_window_start = today_str
        date_window_end = today_str
        try:
            start_col = next((c for c in master_df.columns if "start" in c.lower() and "date" in c.lower()), None)
            end_col   = next((c for c in master_df.columns if "end" in c.lower() and "date" in c.lower()), None)
            if start_col:
                parsed = pd.to_datetime(master_df[start_col], errors="coerce")
                if not parsed.dropna().empty:
                    date_window_start = str(parsed.min().date())
            if end_col:
                parsed = pd.to_datetime(master_df[end_col], errors="coerce")
                if not parsed.dropna().empty:
                    date_window_end = str(parsed.max().date())
            print(f"[*] Date Window: {date_window_start} → {date_window_end}")
        except Exception as e:
            print(f"[!] Date window parse note: {e} — using today_str as fallback")
        # ─────────────────────────────────────────────────────────────────────────

        # Ingest into PostgreSQL
        ingested_count = upsert_master_to_postgres(master_path)

        # Upload files to GCS Bucket
        gcs_urls = upload_reports_to_gcs(today_str)
        blr_url = gcs_urls.get(f"{today_compact}-vehicle_incentives-SAMVREEDDHI_BLR_P.xlsx", "#")
        mum_url = gcs_urls.get(f"{today_compact}-vehicle_incentives-SAMVREEDDHI_MUM_P.xlsx", "#")
        hyd_url = gcs_urls.get(f"{today_compact}-vehicle_incentives-SAMVREEDDHI_HYD_P.xlsx", "#")
        master_url = gcs_urls.get(f"{today_compact}-vehicle_incentives-SAMVREEDDHI_ALL_3_CITIES.xlsx", "#")

        duration_sec = time.time() - start_time
        mins, secs = divmod(int(duration_sec), 60)
        duration_str = f"{mins}m {secs}s"

        # Log to PostgreSQL Ingestion Log
        log_execution_to_postgres(
            today_str=today_str,
            attempt=current_attempt,
            status="SUCCESS",
            start_dt=date_window_start,   # Fix #5: real date range from CSV
            end_dt=date_window_end,
            blr_rows=blr_rows,
            mum_rows=mum_rows,
            hyd_rows=hyd_rows,
            total_rows=ingested_count,
            blr_url=blr_url,
            mum_url=mum_url,
            hyd_url=hyd_url,
            master_url=master_url,
            duration_sec=duration_sec
        )

        # Send LetzRyd Success Email
        send_success_email(
            date_window=f"{date_window_start} → {date_window_end}",
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

        state["status"] = "SUCCESS"
        state["attempts"] = current_attempt
        state["completed_at"] = now_ist.strftime("%Y-%m-%d %H:%M:%S IST")
        save_gcs_state(today_str, state)
        success = True

    except Exception as e:
        error_reason = str(e)
        print(f"[-] Execution error during attempt {current_attempt}: {e}", flush=True)

    finally:
        # ── Fix #2: Always sync cookies back to GCS ──────────────────────────
        # Even if export fails, fresh login cookies must be preserved
        # so the next retry attempt doesn't start with expired credentials.
        print("[*] Syncing any fresh session cookies back to GCS (always-run)...")
        sync_cookies_to_gcs()
        # ────────────────────────────────────────────────────────────────────

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

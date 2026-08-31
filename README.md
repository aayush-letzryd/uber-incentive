# 🚖 LetzRyd · Uber Vehicle Incentives Automation Pipeline (Production v4.2)

Automated end-to-end data ingestion engine that exports official incentive ledgers across **Bangalore**, **Mumbai**, and **Hyderabad** directly from the Uber Supplier Portal, consolidates them into master datasets, uploads them to Google Cloud Storage (GCS), ingests clean records into PostgreSQL, and delivers branded status emails.

---

## 🏛️ System Architecture

```
                                  +-----------------------------+
                                  |   Google Cloud Scheduler    |
                                  |  (07:00, 08:10, 09:10, 10:10)|
                                  +--------------+--------------+
                                                 | (HTTP Trigger)
                                                 v
                                  +-----------------------------+
                                  |     GCP Cloud Run Job       |
                                  |   (Headless Playwright)     |
                                  +--------------+--------------+
                                                 |
         +---------------------------------------+---------------------------------------+
         |                                       |                                       |
         v                                       v                                       v
+------------------+                   +--------------------+                  +------------------+
|  Uber Supplier   |                   |   Google Storage   |                  |    PostgreSQL    |
|     Portal       |                   |    Bucket (GCS)    |                  |     Database     |
| (Export Buttons) |                   |  (CSVs, .xlsx, DL) |                  | (Upsert + Logs)  |
+------------------+                   +--------------------+                  +------------------+
         |                                       |                                       |
         +---------------------------------------+---------------------------------------+
                                                 |
                                                 v
                                  +-----------------------------+
                                  |   LetzRyd Operations Mail   |
                                  |  (Green Success / Red Alert)|
                                  +-----------------------------+
```

---

## ⏰ Execution & Retry Policy

| Trigger | Time (IST) | Purpose | Action on Success | Action on Failure |
| :--- | :--- | :--- | :--- | :--- |
| **Attempt 1** | **07:00 AM** | Primary daily execution | 🟢 Sends **Success Email** + GCS + DB | Silent retry at 08:10 AM |
| **Attempt 2** | **08:10 AM** | Retry 1 (70m buffer) | 🟢 Sends **Success Email** | Silent retry at 09:10 AM |
| **Attempt 3** | **09:10 AM** | Retry 2 (60m buffer) | 🟢 Sends **Success Email** | Silent retry at 10:10 AM |
| **Attempt 4** | **10:10 AM** | **Final Attempt** | 🟢 Sends **Success Email** | 🚨 Sends **Red Alert Email** (`STATUS: ACTION REQUIRED`) |

> ⚡ **Smart Idempotency**: When Attempt 1 succeeds at 07:00 AM, state is stored at `gs://letzryd-uber-reports/state/YYYY-MM-DD.json`. Attempts 2, 3, and 4 detect the `SUCCESS` state and **terminate in 1 second with 0 extra compute cost**.

---

## 🗄️ Database Tables (PostgreSQL)

Located in `sql/001_create_incentives_table.sql`:

### 1. Data Table: `uber_vehicle_incentives_raw`
Stores granular incentive tiers per vehicle per promotion period.
```sql
CREATE TABLE IF NOT EXISTS uber_vehicle_incentives_raw (
    id                          BIGSERIAL PRIMARY KEY,
    city                        VARCHAR(50) NOT NULL,
    vehicle_name                VARCHAR(150),
    number_plate                VARCHAR(50) NOT NULL,
    start_date                  TIMESTAMP NOT NULL,
    end_date                    TIMESTAMP NOT NULL,
    acceptance_rate             NUMERIC(6,2),
    target_acceptance_rate      NUMERIC(6,2),
    trips_completed             INTEGER DEFAULT 0,
    trip_target                 INTEGER DEFAULT 0,
    total_payout                NUMERIC(12,2) DEFAULT 0.00,
    status                      VARCHAR(50),
    driver_trip_count_breakdown TEXT,
    org_name                    VARCHAR(150),
    ingested_at                 TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_vehicle_incentive_window UNIQUE (city, number_plate, start_date, end_date, trip_target)
);
```

### 2. Execution Log Table: `uber_incentives_ingestion_log`
Tracks every daily run, duration, city record counts, and direct Cloud Storage statement URLs.
```sql
CREATE TABLE IF NOT EXISTS uber_incentives_ingestion_log (
    id                          BIGSERIAL PRIMARY KEY,
    execution_date              DATE NOT NULL,
    attempt_number              INTEGER NOT NULL DEFAULT 1,
    status                      VARCHAR(50) NOT NULL, -- 'SUCCESS' or 'FAILED'
    date_window_start           TIMESTAMP,
    date_window_end             TIMESTAMP,
    blr_rows                    INTEGER DEFAULT 0,
    mum_rows                    INTEGER DEFAULT 0,
    hyd_rows                    INTEGER DEFAULT 0,
    total_rows                  INTEGER DEFAULT 0,
    blr_file_url                TEXT,
    mum_file_url                TEXT,
    hyd_file_url                TEXT,
    master_file_url             TEXT,
    execution_duration_sec      NUMERIC(10,2),
    error_message               TEXT,
    created_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 📧 Email Notifications

* **Success Email (Green Badge)**:
  * Sent on the **first successful attempt**.
  * Shows row counts for Bangalore, Mumbai, and Hyderabad.
  * Contains direct download links for **Bangalore Fleet (.xlsx)**, **Mumbai Fleet (.xlsx)**, **Hyderabad Fleet (.xlsx)**, and the **Combined Master Statement (.xlsx)**.
  * No heavy email attachments.
* **Failure Alert Email (Red Badge)**:
  * Sent **only if all 4 attempts fail** (after 10:10 AM).
  * Outlines failure reason and confirms `Database Protection: SAFE & UNTOUCHED`.

---

## 🚀 1-Click Google Cloud Deployment

From **Google Cloud Shell**:

```bash
git clone https://github.com/aayush-letzryd/uber-incentive.git && cd uber-incentive && chmod +x deploy_gcp.sh && ./deploy_gcp.sh
```

---

## 📁 Repository Structure

```
├── cloud_runner.py               # Cloud orchestrator (idempotency, GCS, DB upsert, email dispatch)
├── uber_full_automation.py       # Core Playwright engine (export button trigger & download watcher)
├── mailer.py                     # Branded HTML email dispatcher (Success / Failure templates)
├── deploy_gcp.sh                 # 1-click Linux/Cloud Shell deployment script
├── deploy_to_gcp.ps1             # 1-click PowerShell deployment script
├── Dockerfile                    # Container configuration (Playwright + Python)
├── .dockerignore                 # Excludes local artifacts from cloud builds
├── requirements.txt              # Python runtime dependencies
├── sql/
│   └── 001_create_incentives_table.sql # Database schema (raw data + execution logs)
├── cookies.json                  # Preserved Uber session authentication cookies
└── storage_state.json            # Device trust state
```

---

## 🛠️ Local Testing & Development

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Run manual local extraction
python uber_full_automation.py

# 3. Run full cloud simulation (state check + DB upsert + mailer)
python cloud_runner.py
```

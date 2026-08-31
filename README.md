# 🚖 LetzRyd · Uber Vehicle Incentives Automation Pipeline (Production v4.8)

[![Google Cloud Run](https://img.shields.io/badge/GCP-Cloud%20Run%20Job-4285F4?style=for-the-badge&logo=googlecloud&logoColor=white)](https://cloud.google.com/run)
[![Playwright](https://img.shields.io/badge/Playwright-Headless%20Browser-2EAD33?style=for-the-badge&logo=playwright&logoColor=white)](https://playwright.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Database%20Ingestion-336791?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Google Cloud Storage](https://img.shields.io/badge/GCS-Statements%20%26%20State-EA4335?style=for-the-badge&logo=googlecloud&logoColor=white)](https://cloud.google.com/storage)
[![Cloud Scheduler](https://img.shields.io/badge/Scheduler-4--Tier%20Retry%20(IST)-FF9900?style=for-the-badge&logo=googlecloud&logoColor=white)](https://cloud.google.com/scheduler)

Automated end-to-end data ingestion engine that exports official incentive ledgers across **Bangalore (BLR P)**, **Mumbai (MUM P)**, and **Hyderabad (HYD P)** directly from the Uber Supplier Portal, consolidates them into master datasets, uploads them to Google Cloud Storage (GCS), ingests clean records into PostgreSQL via batch upsert, and delivers branded status emails.

---

## 📑 Table of Contents

1. [Executive Summary & Capabilities](#-executive-summary--capabilities)
2. [End-to-End System Architecture](#-end-to-end-system-architecture)
3. [Core Engineering Highlights](#-core-engineering-highlights)
   - [3-Tier Multi-Method Authentication](#1-3-tier-multi-method-authentication-engine)
   - [City Navigation & Fast-Path Routing](#2-city-navigation--fast-path-routing)
   - [Anti-Contamination & DOM Stabilization Guards](#3-anti-contamination--dom-stabilization-guards)
   - [Smart Idempotency & State Sync](#4-smart-idempotency--state-sync)
4. [Execution Schedule & 4-Tier Retry Matrix](#-execution-schedule--4-tier-retry-matrix)
5. [Database Architecture & Data Dictionaries](#-database-architecture--data-dictionaries)
6. [Automated Email Reporting System](#-automated-email-reporting-system)
7. [Repository Structure](#-repository-structure)
8. [Configuration & Secret Reference](#-configuration--secret-reference)
9. [Local Development & Testing Runbook](#-local-development--testing-runbook)
10. [Google Cloud Deployment (GCP Cloud Shell)](#-google-cloud-deployment-gcp-cloud-shell)
11. [Monitoring, Operations & Troubleshooting](#-monitoring-operations--troubleshooting)

---

## 🌟 Executive Summary & Capabilities

* **Multi-City Fleet Consolidation**: Sequentially processes Uber Supplier Portal accounts for **Bangalore**, **Mumbai**, and **Hyderabad**, validating each city's unique identifier and file headers.
* **Resilient Headless Playwright Engine**: Custom-tuned Chromium runtime with `playwright-stealth`, persistent context management, automated download listeners, and orphan popup tab termination.
* **Zero-Touch 3-Tier Authentication**: Seamlessly handles session resumption, automated credential submission, real-time Google Sheets SMS OTP polling, and Google OAuth / Gmail 2-Step Verification fallback.
* **Enterprise Cloud Storage Integration**: Stores raw CSVs, structured Excel workbooks, daily master consolidated files, persistent session tokens, and execution states in Google Cloud Storage.
* **PostgreSQL Batch Upsert**: High-performance batch ingestion using `psycopg2.extras.execute_values` (2,000 rows/batch) with deterministic unique constraints to prevent duplicate entries while updating existing records.
* **Intelligent Daily Retries (IST)**: A 4-stage scheduler with stateful idempotency that eliminates redundant compute costs after the first daily success.
* **Executive HTML Email Dispatch**: Automated SMTP notifications with direct GCS links to city and master workbooks (no heavy email attachments) and single red alert dispatching strictly after all retries are exhausted.

---

## 🏛️ End-to-End System Architecture

```
+---------------------------------------------------------------------------------------------------+
|                                      GOOGLE CLOUD PLATFORM                                        |
|                                                                                                   |
|  +-----------------------------+                                                                  |
|  |    Cloud Scheduler (IST)    |                                                                  |
|  |  07:00 | 08:10 | 09:10 | 10:10 |                                                                  |
|  +--------------+--------------+                                                                  |
|                 | (HTTP POST Trigger via Service Account OIDC)                                    |
|                 v                                                                                 |
|  +---------------------------------------------------------------------------------------------+  |
|  | GCP Cloud Run Job: uber-incentives-job (Container: 2 vCPU, 4 GiB RAM, asia-south1)           |  |
|  |                                                                                             |  |
|  |  1. Sync state & cookies <--------> gs://letzryd-uber-reports/session/                      |  |
|  |  2. If status == 'SUCCESS' ------> Exit in 1s (0 extra compute)                             |  |
|  |  3. Launch Playwright Headless Chromium with Stealth & Download Listener                     |  |
|  |  4. Authenticate (Session Cache -> Uber + Sheet OTP -> Google OAuth)                        |  |
|  |  5. Iterate Cities (BLR P -> MUM P -> HYD P):                                               |  |
|  |     - Direct Org UUID Fast-Path / UI Switcher Fallback                                      |  |
|  |     - 1 Clean Reload + 7s DOM Stabilization                                                 |  |
|  |     - Trigger Official Export & Capture Download via context.on('download')                 |  |
|  |     - Run Number Plate Sanity Verification & seen_files Deconfliction                       |  |
|  |     - 20s Inter-City Cooldown                                                               |  |
|  |  6. Consolidate 3-City Master Excel & CSV Dataset                                           |  |
|  +--------------+---------------------------------------+--------------------------------------+  |
+-----------------|---------------------------------------|-----------------------------------------+
                  |                                       |
                  v                                       v
   +------------------------------+        +------------------------------+
   |   Google Cloud Storage       |        |   PostgreSQL Database        |
   |   (gs://letzryd-uber-reports)|        |   (Port 5432)                |
   |                              |        |                              |
   |  • /reports/YYYY-MM-DD/*.xlsx|        |  • uber_vehicle_incentives_raw|
   |  • /state/YYYY-MM-DD/*.json  |        |    (Batch Upsert 2000/batch) |
   |  • /session/*.json           |        |  • uber_incentives_ingestion_log|
   +--------------+---------------+        +--------------+---------------+
                  |                                       |
                  +-------------------+-------------------+
                                      |
                                      v
                       +------------------------------+
                       |    Automated SMTP Mailer     |
                       |    (smtp.gmail.com:465)      |
                       |                              |
                       |  🟢 Green Badge: SUCCESS     |
                       |     (With direct GCS links)  |
                       |  🚨 Red Badge: FINAL FAILURE |
                       |     (Only after Attempt 4)   |
                       +------------------------------+
```

---

## ⚙️ Core Engineering Highlights

### 1. 3-Tier Multi-Method Authentication Engine

Authentication automatically evaluates three progressive tiers to guarantee continuous headless execution even when session tokens rotate:

```
[Start Auth]
     |
     v
[Tier 1: Session Cookie Cache] ---> Valid? ---> (Proceed to City Processing)
     | (Expired / Redirected)
     v
[Tier 2: Direct Uber Login]
     ├── Enter UBER_EMAIL & UBER_PASSWORD
     └── 2FA Prompted? ---> Poll Google Sheets SMS OTP (4-digit) ---> (Proceed)
     | (Failed / Blocked)
     v
[Tier 3: Google Account OAuth Fallback]
     ├── Click "Continue with Google"
     ├── Enter Google Email & Password
     └── Google 2-Step Verification? ---> Poll Google Sheets for Google OTP ---> (Proceed)
     |
     v
[Save Fresh Cookies & Storage State to GCS in 'finally' block]
```

1. **Tier 1 (Cached Session & Device State)**:
   - Restores `cookies.json` and `storage_state.json` into Playwright's persistent context.
   - Executes pre-flight health check against `https://supplier.uber.com`. If valid, bypasses all login screens in under 4 seconds.
2. **Tier 2 (Direct Uber Auth + Sheet SMS Polling)**:
   - Navigates through Uber's dynamic login UI (`PHONE_NUMBER_OR_EMAIL_ADDRESS` -> `More options` -> `Password`).
   - If an SMS 2FA challenge is triggered, the engine polls the Google Sheets live SMS webhook endpoint (`https://docs.google.com/spreadsheets/d/1014Tpm7Gj5VAtSW1CaMTIiPn7TxmT-qzHCctW8PlY_4/export?format=csv&gid=0`) every 4 seconds (timeout: 90s), extracts the fresh 4-digit OTP code via regex (`\b(\d{4})\b`), and enters it into the tel inputs.
3. **Tier 3 (Google OAuth + Gmail 2-Step Fallback)**:
   - If direct auth encounters non-standard challenges, the engine switches to Google OAuth (`Continue with Google`).
   - Fills Google credentials and automatically handles Google 2-Step Verification (`input#idvPin`) by polling the Google Sheet feed for the Google authentication pin.
4. **Session Persistence**:
   - Every successful login saves new session cookies and storage state locally and immediately mirrors them to `gs://letzryd-uber-reports/session/` inside an unconditional `finally` block.

---

### 2. City Navigation & Fast-Path Routing

The pipeline manages three independent operating entities under the Samvreeddhi Mobility umbrella:

| City | Target Fleet Name | Code | Direct Org UUID | Max Wait |
| :--- | :--- | :--- | :--- | :--- |
| **Bangalore** | `SAMVREEDDHI MOBILITY Pvt. Ltd. BLR P` | `BLR` | `ebb10afb-c08b-463e-a4fa-33b64674adfd` | 900s (15 min) |
| **Mumbai** | `Samvreeddhi Mobility Pvt. Ltd. MUM P` | `MUM` | `44cb587c-a690-44b5-94c2-37539500c7d5` | 600s (10 min) |
| **Hyderabad** | `Samvreeddhi Mobility Pvt Ltd HYD P` | `HYD` | `f7d7968b-43fe-4c15-bfc8-30a82c8ad5b9` | 600s (10 min) |

#### Fast-Path Routing
Navigates directly to `https://supplier.uber.com/orgs/{org_uuid}/promotions`. If the target Org UUID is valid, the promotions dashboard loads immediately, cutting navigation time from 25 seconds to under 3 seconds.

#### Progressive Container-Scrolling Fallback
If an Org UUID expires or changes, the engine falls back to the UI Account Switcher:
- Locates the active scrollable container via `window.getComputedStyle(el).overflowY`.
- Resets scroll position to top to ensure high-priority accounts are visible.
- Executes strict regex matching (e.g., strictly targets `HYD P` while rejecting `HYD I`, `HYD II`, `HYD III`, `HYD IV`, `HYD V`).
- Incrementally scrolls in 100px increments until the target account is in the viewport and clicks it.
- Dynamically caches the newly discovered Org UUID to `org_uuids.json` for future runs.

---

### 3. Anti-Contamination & DOM Stabilization Guards

To ensure 100% data integrity across sequential city extractions, the pipeline enforces strict isolation barriers:

```
[Switch City]
     │
     ├── 1. Verify Active Org UUID != previous_orgs (Prevents cross-city data contamination)
     ├── 2. Clean Page Reload (main_page.reload)
     ├── 3. 7-Second DOM Hydration Wait (Ensures SPA state and event listeners are fully ready)
     ├── 4. Post-Reload Session Guard (Catches sudden auth drops and re-authenticates)
     ├── 5. Reset download_state['latest_file'] = None
     ├── 6. Trigger Official Export Button
     ├── 7. Filter Downloads against seen_files set & file creation timestamp
     ├── 8. Execute Number Plate Sanity Check (Inspects sample plate formats)
     └── 9. 20-Second Inter-City Cooldown (Allows popup tabs to close and network to settle)
```

* **Org UUID Anti-Contamination Check**: Compares the current URL org against `previous_orgs`. If the browser remains on a prior city's organization, the run is immediately aborted to prevent saving duplicate data under another city's name.
* **7-Second DOM Stabilization**: After reloading the promotions view, the engine waits 7 full seconds for React/BaseWeb event handlers to attach before dispatching click events.
* **`seen_files` Tracking**: An in-memory set prevents the current city from claiming CSV/Excel files downloaded during an earlier city's execution.
* **Plate Sanity Check**: Immediately after conversion, the engine reads the first 5 number plates (e.g., `KA...`, `MH...`, `TS...`) and logs them to the execution transcript for validation.
* **Orphan Tab Cleanup (`ensure_main_page`)**: Scans `context.pages` and forcefully terminates any auxiliary popup windows generated by Uber's export backend.

---

### 4. Smart Idempotency & State Sync

* Every daily run maintains a state file in Google Cloud Storage: `gs://letzryd-uber-reports/state/YYYY-MM-DD/pipeline_state.json`.
* **Instant Exit on Success**: When Attempt 1 succeeds at 07:00 AM, state is updated to `SUCCESS`. Subsequent scheduled attempts (08:10, 09:10, 10:10 AM) detect the success state and terminate in **under 1 second with zero extra compute cost**.
* **Automatic Attempt Counter**: Automatically increments `attempts` across scheduler triggers to manage the alert policy.

---

## ⏰ Execution Schedule & 4-Tier Retry Matrix

All schedules operate in **Indian Standard Time (Asia/Kolkata)**:

| Trigger | Time (IST) | Cron Expression | Role / Purpose | Success Action | Failure Action |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Attempt 1** | **07:00 AM** | `0 7 * * *` | Primary daily execution | 🟢 Sends **Success Email** + GCS + DB | Silent retry scheduled |
| **Attempt 2** | **08:10 AM** | `10 8 * * *` | Retry 1 (70m buffer for Uber batch) | 🟢 Sends **Success Email** | Silent retry scheduled |
| **Attempt 3** | **09:10 AM** | `10 9 * * *` | Retry 2 (60m buffer) | 🟢 Sends **Success Email** | Silent retry scheduled |
| **Attempt 4** | **10:10 AM** | `10 10 * * *` | **Final Retry Attempt** | 🟢 Sends **Success Email** | 🚨 Sends **Red Alert Email** (`STATUS: ACTION REQUIRED`) |

> 🛡️ **Alert Protection Policy**: No failure emails are sent for transient failures on Attempts 1, 2, or 3. The Red Alert email is dispatched **only if Attempt 4 fails**, preventing unnecessary alarms during normal Uber backend processing delays.

---

## 🗄️ Database Architecture & Data Dictionaries

Database migration file: `sql/001_create_incentives_table.sql`.

### 1. Data Table: `uber_vehicle_incentives_raw`

Stores granular vehicle-level incentive milestones per promotion window.

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

CREATE INDEX IF NOT EXISTS idx_uber_inc_city ON uber_vehicle_incentives_raw(city);
CREATE INDEX IF NOT EXISTS idx_uber_inc_plate ON uber_vehicle_incentives_raw(number_plate);
CREATE INDEX IF NOT EXISTS idx_uber_inc_window ON uber_vehicle_incentives_raw(start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_uber_inc_status ON uber_vehicle_incentives_raw(status);
```

#### Field Specifications

| Column Name | Data Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `id` | `BIGSERIAL` | No | Auto-incrementing primary key |
| `city` | `VARCHAR(50)` | No | Operating city (`Bangalore`, `Mumbai`, `Hyderabad`) |
| `vehicle_name` | `VARCHAR(150)` | Yes | Vehicle make/model string from portal |
| `number_plate` | `VARCHAR(50)` | No | Normalized registration number (e.g. `KA01AK1234`) |
| `start_date` | `TIMESTAMP` | No | Promotion window start timestamp |
| `end_date` | `TIMESTAMP` | No | Promotion window end timestamp |
| `acceptance_rate` | `NUMERIC(6,2)` | Yes | Actual driver acceptance rate percentage |
| `target_acceptance_rate` | `NUMERIC(6,2)` | Yes | Target required acceptance rate percentage |
| `trips_completed` | `INTEGER` | No | Number of eligible trips completed in window |
| `trip_target` | `INTEGER` | No | Target trip count for the incentive tier |
| `total_payout` | `NUMERIC(12,2)` | No | Monetary incentive payout earned (INR) |
| `status` | `VARCHAR(50)` | Yes | Incentive qualification status (`Achieved`, etc.) |
| `driver_trip_count_breakdown` | `TEXT` | Yes | Granular driver-level contribution breakdown |
| `org_name` | `VARCHAR(150)` | Yes | Supplier organization entity name |
| `ingested_at` | `TIMESTAMP` | No | Ingestion timestamp |

---

### 2. Ingestion Log Table: `uber_incentives_ingestion_log`

Maintains an audit trail of every pipeline run with record counts and direct cloud links.

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

CREATE INDEX IF NOT EXISTS idx_uber_logs_date ON uber_incentives_ingestion_log(execution_date);
CREATE INDEX IF NOT EXISTS idx_uber_logs_status ON uber_incentives_ingestion_log(status);
```

---

## 📧 Automated Email Reporting System

The pipeline includes an executive HTML email dispatcher implemented in `mailer.py`.

### 1. Success Email Template (Green Theme)
* **Trigger**: Dispatched upon the first successful extraction of all 3 cities.
* **Highlights**:
  * Clean status card with target date window and city breakdown (**Bangalore**, **Mumbai**, **Hyderabad**, and **Total Master Rows**).
  * Direct GCS download buttons for:
    * `Bangalore Fleet (.xlsx)`
    * `Mumbai Fleet (.xlsx)`
    * `Hyderabad Fleet (.xlsx)`
    * `Combined Master Statement (.xlsx)`
  * Zero heavy attachments — bypasses email size limits and corporate spam filters.

### 2. Failure Alert Email Template (Red Theme)
* **Trigger**: Dispatched **only after Attempt 4 (10:10 AM IST) fails**.
* **Highlights**:
  * Status indicator: `STATUS: ACTION REQUIRED`.
  * Detailed diagnostic error message.
  * Confirmation that database integrity remains `SAFE & UNTOUCHED`.
  * Details self-healing recovery actions for the next scheduled cycle.

---

## 📁 Repository Structure

```
letzryd-uber-incentives/
├── .dockerignore                 # Excludes local artifacts, virtualenvs & caches from Docker builds
├── .gitignore                    # Git ignore rules for profiles, logs, and temp reports
├── Dockerfile                    # Production Playwright Python image (Jammy base)
├── README.md                     # Comprehensive architecture & operations documentation
├── requirements.txt              # Production Python package dependencies
│
├── cloud_runner.py               # Main Cloud Orchestrator (Idempotency, GCS Sync, DB Upsert, Mailer)
├── uber_full_automation.py       # Core Playwright Engine (Fast-path navigation, export trigger & watcher)
├── mailer.py                     # Branded HTML email dispatcher (Success & Failure templates)
├── org_uuids.json                # Cached Org UUID mappings for BLR, MUM, and HYD
├── cookies.json                  # Initial preserved Uber session cookies
├── storage_state.json            # Initial Playwright browser storage state
│
├── deploy_gcp.sh                 # Production bash deployment script for Google Cloud Shell
├── deploy_to_gcp.ps1             # Production PowerShell deployment script for Windows
├── apply_db_migration.py         # Database migration runner utility
│
├── sql/
│   └── 001_create_incentives_table.sql  # DDL for raw data and pipeline log tables
│
├── uber_reports/                 # Output directory for downloaded CSVs and generated Excel workbooks
├── screenshots/                  # Debug screenshots captured during automated runs
└── uber_chrome_profile/          # Local persistent Chromium browser profile directory
```

---

## 🔐 Configuration & Secret Reference

### Environment Variables

| Variable Name | Required | Default Value | Description |
| :--- | :--- | :--- | :--- |
| `GCS_BUCKET_NAME` | No | `letzryd-uber-reports` | Google Cloud Storage bucket name for statements and state |
| `PG_HOST` | Yes | `35.200.196.113` | PostgreSQL host IP address |
| `PG_PORT` | No | `5432` | PostgreSQL port |
| `PG_DATABASE` | No | `postgres` | Target database name |
| `PG_USER` | No | `postgres` | Database username |
| `EMAIL_RECIPIENTS` | No | `vendor_aayush@letzryd.com` | Comma-separated list of report recipient email addresses |
| `HEADLESS` | No | `true` (in Docker) | Toggle headless browser mode (`true` or `false`) |
| `PYTHONIOENCODING` | No | `utf-8` | Ensures UTF-8 encoding across console and logs |

### Secret Manager Secrets

| Secret Name | Purpose | Injected Via |
| :--- | :--- | :--- |
| `PG_PASSWORD` | PostgreSQL user password | GCP Secret Manager (`--set-secrets PG_PASSWORD=PG_PASSWORD:latest`) |
| `UBER_PASSWORD` | Uber Supplier Portal password | GCP Secret Manager (`--set-secrets UBER_PASSWORD=UBER_PASSWORD:latest`) |

---

## 🛠️ Local Development & Testing Runbook

### 1. Environment Setup

```bash
# Clone repository
git clone https://github.com/aayush-letzryd/uber-incentive.git
cd uber-incentive

# Create and activate Python virtual environment
python -m venv venv
# On Linux/macOS:
source venv/bin/activate
# On Windows PowerShell:
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Install Playwright Chromium browser binaries and system dependencies
playwright install chromium
playwright install-deps chromium
```

### 2. Database Initialization

Execute the migration script against your target PostgreSQL database:

```bash
python apply_db_migration.py
```

Or execute directly via `psql`:

```bash
psql -h 35.200.196.113 -U postgres -d postgres -f sql/001_create_incentives_table.sql
```

### 3. Running Extraction & Full Pipeline Locally

```bash
# Option A: Run core browser automation only (downloads CSVs and builds Excel)
python uber_full_automation.py

# Option B: Run complete cloud orchestrator (state check + browser + GCS upload + DB upsert + email dispatch)
python cloud_runner.py
```

---

## 🚀 Google Cloud Deployment (GCP Cloud Shell)

Deploy the entire infrastructure (APIs, Service Accounts, IAM, Storage Bucket, Secrets, Artifact Registry, Cloud Build, Cloud Run Job, and Cloud Schedulers) in **one command**:

### Automated 1-Click Deployment via `deploy_gcp.sh`

Open **[Google Cloud Shell](https://shell.cloud.google.com/)** and execute:

```bash
git clone https://github.com/aayush-letzryd/uber-incentive.git && cd uber-incentive && chmod +x deploy_gcp.sh && ./deploy_gcp.sh
```

### Step-by-Step CLI Walkthrough

If executing deployment steps manually:

```bash
# 1. Set active project and region
export PROJECT_ID=$(gcloud config get-value project)
export REGION="asia-south1"
export JOB_NAME="uber-incentives-job"
export REPO_NAME="letzryd-docker"
export BUCKET_NAME="letzryd-uber-reports"

# 2. Enable required GCP APIs
gcloud services enable \
    run.googleapis.com \
    cloudscheduler.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    storage.googleapis.com \
    iam.googleapis.com \
    secretmanager.googleapis.com

# 3. Grant IAM permissions to Compute Service Account
export PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
export SA_EMAIL="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA_EMAIL" --role="roles/run.invoker"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA_EMAIL" --role="roles/storage.objectAdmin"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA_EMAIL" --role="roles/secretmanager.secretAccessor"

# 4. Create GCS Bucket & sync session cookies
gsutil mb -p "$PROJECT_ID" -l "$REGION" -b on "gs://$BUCKET_NAME" || true
gsutil cp cookies.json "gs://$BUCKET_NAME/session/cookies.json"
gsutil cp storage_state.json "gs://$BUCKET_NAME/session/storage_state.json"

# 5. Store Secrets in GCP Secret Manager
echo -n "YOUR_PG_PASSWORD" | gcloud secrets create PG_PASSWORD --data-file=- --replication-policy="automatic" || true
echo -n "YOUR_UBER_PASSWORD" | gcloud secrets create UBER_PASSWORD --data-file=- --replication-policy="automatic" || true

# 6. Build and push container image using Artifact Registry
gcloud artifacts repositories create "$REPO_NAME" --repository-format=docker --location="$REGION" || true
export IMAGE_TAG="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$JOB_NAME:latest"
gcloud builds submit --tag "$IMAGE_TAG"

# 7. Deploy Cloud Run Job
gcloud run jobs deploy "$JOB_NAME" \
    --image "$IMAGE_TAG" \
    --region "$REGION" \
    --memory 4Gi \
    --cpu 2 \
    --task-timeout 3600s \
    --max-retries 0 \
    --set-env-vars="GCS_BUCKET_NAME=$BUCKET_NAME,PYTHONIOENCODING=utf-8,EMAIL_RECIPIENTS=vendor_aayush@letzryd.com,HEADLESS=true,PG_HOST=35.200.196.113,PG_PORT=5432,PG_DATABASE=postgres,PG_USER=postgres" \
    --set-secrets="PG_PASSWORD=PG_PASSWORD:latest,UBER_PASSWORD=UBER_PASSWORD:latest"

# 8. Create 4-Tier Cloud Schedulers (IST)
gcloud scheduler jobs create http uber-incentives-07-00am \
    --schedule="0 7 * * *" --time-zone="Asia/Kolkata" --location="$REGION" \
    --uri="https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/$JOB_NAME:run" \
    --http-method="POST" --oauth-service-account-email="$SA_EMAIL"

gcloud scheduler jobs create http uber-incentives-08-10am \
    --schedule="10 8 * * *" --time-zone="Asia/Kolkata" --location="$REGION" \
    --uri="https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/$JOB_NAME:run" \
    --http-method="POST" --oauth-service-account-email="$SA_EMAIL"

gcloud scheduler jobs create http uber-incentives-09-10am \
    --schedule="10 9 * * *" --time-zone="Asia/Kolkata" --location="$REGION" \
    --uri="https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/$JOB_NAME:run" \
    --http-method="POST" --oauth-service-account-email="$SA_EMAIL"

gcloud scheduler jobs create http uber-incentives-10-10am \
    --schedule="10 10 * * *" --time-zone="Asia/Kolkata" --location="$REGION" \
    --uri="https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/$JOB_NAME:run" \
    --http-method="POST" --oauth-service-account-email="$SA_EMAIL"
```

---

## 📊 Monitoring, Operations & Troubleshooting

### Trigger Manual Execution in GCP

```bash
# Execute Cloud Run Job on-demand
gcloud run jobs execute uber-incentives-job --region asia-south1 --wait
```

### Inspecting Live Cloud Run Job Logs

```bash
# Stream latest execution logs
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=uber-incentives-job" \
    --limit 50 \
    --format="value(textPayload)"
```

### Common Troubleshooting Scenarios

#### 1. "Session cookies expired or invalid / Redirected to auth.uber.com"
* **Behavior**: Pre-flight check detects expired session and attempts automated login.
* **Remedy**: Ensure `UBER_PASSWORD` in Secret Manager is up to date and the Google Sheet SMS feed is receiving current OTP codes. To manually refresh cookies, run `uber_full_automation.py` locally and upload the resulting `cookies.json` and `storage_state.json` to `gs://letzryd-uber-reports/session/`.

#### 2. "Export button not visible on Promotions page"
* **Behavior**: Navigation landed on a page without active incentives.
* **Remedy**: The engine automatically captures a debug screenshot to `screenshots/missing_export_{city}.png`. Verify if the Org UUID for the city in `org_uuids.json` is still active on the Uber portal.

#### 3. "Generated Master Excel is empty (0 rows)"
* **Behavior**: Ingestion fails with an error and schedules a retry.
* **Remedy**: Verify if Uber has generated the promotion ledger for the day or if the promotion window has closed. The pipeline will automatically retry on the next scheduled interval.

#### 4. PostgreSQL Connection Timeout
* **Behavior**: `psycopg2.connect` fails to reach `PG_HOST`.
* **Remedy**: Confirm that the PostgreSQL instance allows inbound connections from GCP Cloud Run egress IP ranges and that `PG_PASSWORD` secret in Secret Manager is valid.

---

## 📄 License & Confidentiality

Copyright © 2026 **LetzRyd Mobility Private Limited**. All rights reserved.  
This software and documentation contain proprietary intellectual property for LetzRyd financial and fleet operations.

#!/bin/bash
# ==============================================================================
# LETZRYD · UBER INCENTIVES GCP CLOUD SHELL DEPLOYMENT SCRIPT (PRODUCTION v4.4)
# Uses modern GCP Artifact Registry (asia-south1-docker.pkg.dev)
# Secrets (passwords) injected via GCP Secret Manager — NOT hardcoded here
# ==============================================================================

set -e

PROJECT_ID=$(gcloud config get-value project)
REGION="asia-south1"
JOB_NAME="uber-incentives-job"
REPO_NAME="letzryd-docker"
BUCKET_NAME="letzryd-uber-reports"

if [ -z "$PROJECT_ID" ]; then
    echo "❌ Error: No active GCP project configured in gcloud."
    echo "Run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

echo "=========================================================="
echo "🚀 DEPLOYING UBER INCENTIVES PIPELINE TO GOOGLE CLOUD"
echo "Project ID: $PROJECT_ID | Region: $REGION"
echo "=========================================================="

# 1. Enable Required GCP APIs
echo -e "\n[*] 1. Enabling GCP Services..."
gcloud services enable \
    run.googleapis.com \
    cloudscheduler.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    storage.googleapis.com \
    iam.googleapis.com \
    secretmanager.googleapis.com \
    --project "$PROJECT_ID"

# 2. Configure Service Account Permissions
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
SA_EMAIL="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"

echo -e "\n[*] 2. Granting IAM Roles to Compute Service Account ($SA_EMAIL)..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/run.invoker" \
    --condition=None >/dev/null 2>&1 || true

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/storage.objectAdmin" \
    --condition=None >/dev/null 2>&1 || true

# ── Fix #7/#9: Grant Secret Manager access to the SA ─────────────────────────
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/secretmanager.secretAccessor" \
    --condition=None >/dev/null 2>&1 || true
echo "✅ Secret Manager accessor role granted to $SA_EMAIL"
# ─────────────────────────────────────────────────────────────────────────────

# 3. Create Cloud Storage Bucket
echo -e "\n[*] 3. Ensuring Cloud Storage Bucket exists: gs://$BUCKET_NAME..."
if ! gsutil ls -b "gs://$BUCKET_NAME" >/dev/null 2>&1; then
    gsutil mb -p "$PROJECT_ID" -l "$REGION" -b on "gs://$BUCKET_NAME"
    echo "✅ Bucket created: gs://$BUCKET_NAME"
else
    echo "✅ Bucket already exists: gs://$BUCKET_NAME"
fi

# 4. Upload initial auth cookies to bucket if available
if [ -f "cookies.json" ]; then
    gsutil cp cookies.json "gs://$BUCKET_NAME/session/cookies.json" >/dev/null 2>&1 || true
    gsutil cp cookies.json "gs://$BUCKET_NAME/sessions/cookies.json" >/dev/null 2>&1 || true
    echo "🔑 Synced cookies.json to gs://$BUCKET_NAME/session/ and sessions/"
fi
if [ -f "storage_state.json" ]; then
    gsutil cp storage_state.json "gs://$BUCKET_NAME/session/storage_state.json" >/dev/null 2>&1 || true
    gsutil cp storage_state.json "gs://$BUCKET_NAME/sessions/storage_state.json" >/dev/null 2>&1 || true
    echo "🔑 Synced storage_state.json to gs://$BUCKET_NAME/session/ and sessions/"
fi

# ── Fix #7/#9: Create Secrets in GCP Secret Manager ─────────────────────────
echo -e "\n[*] 4a. Setting up GCP Secrets (PG_PASSWORD, UBER_PASSWORD)..."

create_or_update_secret() {
    local SECRET_NAME="$1"
    local SECRET_VALUE="$2"
    if gcloud secrets describe "$SECRET_NAME" --project="$PROJECT_ID" >/dev/null 2>&1; then
        echo "   -> Updating secret: $SECRET_NAME"
        echo -n "$SECRET_VALUE" | gcloud secrets versions add "$SECRET_NAME" --data-file=- --project="$PROJECT_ID"
    else
        echo "   -> Creating secret: $SECRET_NAME"
        echo -n "$SECRET_VALUE" | gcloud secrets create "$SECRET_NAME" --data-file=- --replication-policy="automatic" --project="$PROJECT_ID"
    fi
}

create_or_update_secret "PG_PASSWORD"    "8S5]U3@L^Xz)\FH}"
create_or_update_secret "UBER_PASSWORD"  "Letzuberp123"
echo "✅ Secrets stored in GCP Secret Manager (removed from source code)"
# ─────────────────────────────────────────────────────────────────────────────

# 5. Create Artifact Registry Docker Repository if not exists
echo -e "\n[*] 5. Ensuring Artifact Registry Repository exists: $REPO_NAME in $REGION..."
if ! gcloud artifacts repositories describe "$REPO_NAME" --location="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
    gcloud artifacts repositories create "$REPO_NAME" \
        --repository-format=docker \
        --location="$REGION" \
        --description="Docker repository for LetzRyd automated services" \
        --project="$PROJECT_ID"
    echo "✅ Artifact Registry repository created: $REPO_NAME"
else
    echo "✅ Artifact Registry repository exists: $REPO_NAME"
fi

# 6. Build Docker Image with Cloud Build using Artifact Registry
IMAGE_TAG="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$JOB_NAME:latest"
echo -e "\n[*] 6. Building Container Image with Cloud Build: $IMAGE_TAG..."
gcloud builds submit --tag "$IMAGE_TAG" --project "$PROJECT_ID"

# 7. Deploy Cloud Run Job (secrets injected via Secret Manager, NOT env vars)
echo -e "\n[*] 7. Deploying Cloud Run Job: $JOB_NAME..."
gcloud run jobs deploy "$JOB_NAME" \
    --image "$IMAGE_TAG" \
    --region "$REGION" \
    --project "$PROJECT_ID" \
    --memory 4Gi \
    --cpu 2 \
    --task-timeout 3600s \
    --max-retries 0 \
    --set-env-vars="GCS_BUCKET_NAME=$BUCKET_NAME,PYTHONIOENCODING=utf-8,EMAIL_RECIPIENTS=vendor_aayush@letzryd.com,HEADLESS=true,PG_HOST=35.200.196.113,PG_PORT=5432,PG_DATABASE=postgres,PG_USER=postgres" \
    --set-secrets="PG_PASSWORD=PG_PASSWORD:latest,UBER_PASSWORD=UBER_PASSWORD:latest"

# 8. Create / Update 4 Cloud Schedulers (IST Timezone)
echo -e "\n[*] 8. Configuring 4-Tier Cloud Schedulers (7:00, 8:10, 9:10, 10:10 AM IST)..."

declare -A SCHEDULES=(
    ["uber-incentives-07-00am"]="0 7 * * *"
    ["uber-incentives-08-10am"]="10 8 * * *"
    ["uber-incentives-09-10am"]="10 9 * * *"
    ["uber-incentives-10-10am"]="10 10 * * *"
)

for NAME in "${!SCHEDULES[@]}"; do
    CRON="${SCHEDULES[$NAME]}"
    echo "   -> Setting up $NAME ($CRON IST)..."
    
    if gcloud scheduler jobs describe "$NAME" --location="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
        gcloud scheduler jobs update http "$NAME" \
            --schedule="$CRON" \
            --time-zone="Asia/Kolkata" \
            --location="$REGION" \
            --project="$PROJECT_ID"
    else
        gcloud scheduler jobs create http "$NAME" \
            --schedule="$CRON" \
            --time-zone="Asia/Kolkata" \
            --uri="https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/$JOB_NAME:run" \
            --http-method="POST" \
            --oauth-service-account-email="$SA_EMAIL" \
            --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
            --location="$REGION" \
            --project="$PROJECT_ID"
    fi
done

echo -e "\n=========================================================="
echo "🎉 ALL DONE! DEPLOYMENT COMPLETED SUCCESSFULLY!"
echo "Cloud Run Job: $JOB_NAME"
echo "Artifact Registry: $IMAGE_TAG"
echo "Cloud Storage: gs://$BUCKET_NAME"
echo "Schedule: 07:00 AM, 08:10 AM, 09:10 AM, 10:10 AM IST"
echo "=========================================================="

#!/bin/bash
# ==============================================================================
# LETZRYD · UBER INCENTIVES GCP CLOUD SHELL DEPLOYMENT SCRIPT (PRODUCTION v4.2)
# Sets up: GCS Bucket, IAM Roles, Cloud Run Job (Headless Playwright), and Cloud Schedulers
# ==============================================================================

set -e

PROJECT_ID=$(gcloud config get-value project)
REGION="asia-south1"
JOB_NAME="uber-incentives-job"
BUCKET_NAME="letzryd-uber-reports"
DB_URL="postgresql://postgres:8S5%5DU3%40L%5EXz%29%5CFH%7D@35.200.196.113:5432/postgres"

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
    gsutil cp cookies.json "gs://$BUCKET_NAME/sessions/cookies.json" >/dev/null 2>&1 || true
    echo "🔑 Synced cookies.json to gs://$BUCKET_NAME/sessions/"
fi
if [ -f "storage_state.json" ]; then
    gsutil cp storage_state.json "gs://$BUCKET_NAME/sessions/storage_state.json" >/dev/null 2>&1 || true
    echo "🔑 Synced storage_state.json to gs://$BUCKET_NAME/sessions/"
fi

# 5. Build Docker Image with Cloud Build
IMAGE_TAG="gcr.io/$PROJECT_ID/$JOB_NAME:latest"
echo -e "\n[*] 5. Building Container Image with Cloud Build: $IMAGE_TAG..."
gcloud builds submit --tag "$IMAGE_TAG" --project "$PROJECT_ID"

# 6. Deploy Cloud Run Job
echo -e "\n[*] 6. Deploying Cloud Run Job: $JOB_NAME..."
gcloud run jobs deploy "$JOB_NAME" \
    --image "$IMAGE_TAG" \
    --region "$REGION" \
    --project "$PROJECT_ID" \
    --memory 4Gi \
    --cpu 2 \
    --task-timeout 3600s \
    --max-retries 0 \
    --set-env-vars="GCS_BUCKET_NAME=$BUCKET_NAME,DATABASE_URL=$DB_URL,PYTHONIOENCODING=utf-8,EMAIL_RECIPIENTS=vendor_aayush@letzryd.com,HEADLESS=true"

# 7. Create / Update 4 Cloud Schedulers (IST Timezone)
# 07:00 AM IST -> 0 7 * * *
# 08:10 AM IST -> 10 8 * * *
# 09:10 AM IST -> 10 9 * * *
# 10:10 AM IST -> 10 10 * * *
echo -e "\n[*] 7. Configuring 4-Tier Cloud Schedulers (7:00, 8:10, 9:10, 10:10 AM IST)..."

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
echo "Cloud Storage: gs://$BUCKET_NAME"
echo "Schedule: 07:00 AM, 08:10 AM, 09:10 AM, 10:10 AM IST"
echo "=========================================================="

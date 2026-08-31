#!/bin/bash
# ==============================================================================
# LETZRYD · UBER INCENTIVES GCP CLOUD SHELL DEPLOYMENT SCRIPT
# Sets up: GCS Bucket, Cloud Run Job (with Playwright), and 4-tier Cloud Schedulers
# ==============================================================================

set -e

PROJECT_ID=$(gcloud config get-value project)
REGION="asia-south1"
JOB_NAME="uber-incentives-job"
BUCKET_NAME="letzryd-uber-reports"
DB_URL="postgresql://postgres:8S5%5DU3%40L%5EXz%29%5CFH%7D@35.200.196.113:5432/postgres"

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
    --project "$PROJECT_ID"

# 2. Create Cloud Storage Bucket
echo -e "\n[*] 2. Creating Cloud Storage Bucket: gs://$BUCKET_NAME..."
if ! gsutil ls -b "gs://$BUCKET_NAME" >/dev/null 2>&1; then
    gsutil mb -p "$PROJECT_ID" -l "$REGION" -b on "gs://$BUCKET_NAME"
    echo "✅ Bucket created: gs://$BUCKET_NAME"
else
    echo "✅ Bucket already exists: gs://$BUCKET_NAME"
fi

# 3. Build Docker Image with Cloud Build
IMAGE_TAG="gcr.io/$PROJECT_ID/$JOB_NAME:latest"
echo -e "\n[*] 3. Building Container Image with Cloud Build: $IMAGE_TAG..."
gcloud builds submit --tag "$IMAGE_TAG" --project "$PROJECT_ID"

# 4. Deploy Cloud Run Job
echo -e "\n[*] 4. Deploying Cloud Run Job: $JOB_NAME..."
gcloud run jobs deploy "$JOB_NAME" \
    --image "$IMAGE_TAG" \
    --region "$REGION" \
    --project "$PROJECT_ID" \
    --memory 4Gi \
    --cpu 2 \
    --task-timeout 3600s \
    --max-retries 0 \
    --set-env-vars="GCS_BUCKET_NAME=$BUCKET_NAME,DATABASE_URL=$DB_URL,PYTHONIOENCODING=utf-8,EMAIL_RECIPIENTS=vendor_aayush@letzryd.com"

# 5. Create / Update Cloud Schedulers
# 07:00 AM IST = 01:30 UTC | 08:10 AM IST = 02:40 UTC | 09:10 AM IST = 03:40 UTC | 10:10 AM IST = 04:40 UTC
echo -e "\n[*] 5. Configuring 4-Tier Cloud Schedulers (7:00, 8:10, 9:10, 10:10 AM IST)..."

declare -A SCHEDULES=(
    ["uber-incentives-07-00am"]="30 1 * * *"
    ["uber-incentives-08-10am"]="40 2 * * *"
    ["uber-incentives-09-10am"]="40 3 * * *"
    ["uber-incentives-10-10am"]="40 4 * * *"
)

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
SA_EMAIL="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"

for NAME in "${!SCHEDULES[@]}"; do
    CRON="${SCHEDULES[$NAME]}"
    echo "   -> Setting up $NAME ($CRON)..."
    
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

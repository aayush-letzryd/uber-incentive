# ==============================================================================
# Google Cloud Platform Deployment Script
# Deploys Uber Incentive Automation to Cloud Run Job + Cloud Scheduler
# ==============================================================================

param(
    [string]$ProjectID = "letzryd-prod",
    [string]$Region = "asia-south1",
    [string]$JobName = "uber-incentive-automation-job",
    [string]$SchedulerName = "uber-incentive-daily-trigger",
    [string]$ScheduleCron = "0 6 * * *", # Daily at 06:00 AM IST
    [string]$BucketName = "letzryd-uber-reports"
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   Deploying Uber Incentive Automation to Google Cloud    " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Ensure GCS Bucket exists for cookies and output storage
Write-Host "1. Checking GCS Bucket ($BucketName)..." -ForegroundColor Yellow
gsutil ls -b "gs://$BucketName" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Creating GCS Bucket gs://$BucketName in $Region..." -ForegroundColor Green
    gsutil mb -p $ProjectID -c standard -l $Region "gs://$BucketName"
}

# 2. Upload initial session state if available locally
if (Test-Path "storage_state.json") {
    Write-Host "2. Uploading local session cookies to gs://$BucketName/secrets/uber_storage_state.json..." -ForegroundColor Green
    gsutil cp "storage_state.json" "gs://$BucketName/secrets/uber_storage_state.json"
}

# 3. Build & Submit Docker Container Image to Google Artifact Registry / Cloud Build
$ImageUri = "$Region-docker.pkg.dev/$ProjectID/uber-automation/$JobName`:latest"
Write-Host "3. Building Docker Image ($ImageUri)..." -ForegroundColor Yellow
gcloud builds submit --tag $ImageUri .

# 4. Deploy or Update Cloud Run Job
Write-Host "4. Deploying Cloud Run Job ($JobName)..." -ForegroundColor Yellow
gcloud run jobs deploy $JobName `
    --image $ImageUri `
    --region $Region `
    --memory 2Gi `
    --cpu 2 `
    --task-timeout 15m `
    --set-env-vars GCS_BUCKET_NAME=$BucketName

# 5. Create / Update Cloud Scheduler Trigger
Write-Host "5. Setting up Cloud Scheduler ($SchedulerName: '$ScheduleCron' Asia/Kolkata)..." -ForegroundColor Yellow
gcloud scheduler jobs create http $SchedulerName `
    --schedule="$ScheduleCron" `
    --time-zone="Asia/Kolkata" `
    --uri="https://$Region-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$ProjectID/jobs/$JobName:run" `
    --http-method=POST `
    --oauth-service-account-email="$ProjectID@appspot.gserviceaccount.com" `
    --location=$Region 2>$null

if ($LASTEXITCODE -ne 0) {
    gcloud scheduler jobs update http $SchedulerName `
        --schedule="$ScheduleCron" `
        --time-zone="Asia/Kolkata" `
        --location=$Region
}

Write-Host "==========================================================" -ForegroundColor Green
Write-Host " DEPLOYMENT COMPLETE! " -ForegroundColor Green
Write-Host " Cloud Run Job: $JobName" -ForegroundColor Green
Write-Host " Cloud Scheduler: Every day at 06:00 AM IST ($ScheduleCron)" -ForegroundColor Green
Write-Host " Output Reports Destination: gs://$BucketName/vehicle_incentives/YYYYMMDD/" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green

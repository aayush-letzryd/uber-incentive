<#
.SYNOPSIS
    Deploys LetzRyd Uber Incentives Automation Pipeline to Google Cloud (GCP)
    - Cloud Run Job (Headless Playwright Container)
    - GCS Cloud Storage Bucket
    - Cloud Scheduler (Hourly Retry Schedule: 7 AM, 8 AM, 9 AM, 10 AM IST)
#>

param(
    [string]$ProjectId = "letzryd-prod",
    [string]$Region = "asia-south1",
    [string]$JobName = "uber-incentives-job",
    [string]$BucketName = "letzryd-uber-reports"
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   DEPLOYING LETZRYD UBER INCENTIVES TO GOOGLE CLOUD" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Enable Required GCP APIs
Write-Host "`n[*] Enabling GCP Services..." -ForegroundColor Yellow
gcloud services enable run.googleapis.com `
                       cloudscheduler.googleapis.com `
                       artifactregistry.googleapis.com `
                       storage.googleapis.com `
                       --project $ProjectId

# 2. Create Cloud Storage Bucket if not exists
Write-Host "`n[*] Ensuring GCS Bucket exists: gs://$BucketName..." -ForegroundColor Yellow
gsutil ls -b gs://$BucketName 2>$null
if ($LASTEXITCODE -ne 0) {
    gsutil mb -p $ProjectId -l $Region -b on gs://$BucketName
    Write-Host "[+] Bucket created: gs://$BucketName" -ForegroundColor Green
}

# 3. Build & Push Docker Image via Cloud Build
$ImageTag = "gcr.io/$ProjectId/$JobName:latest"
Write-Host "`n[*] Building Container Image: $ImageTag..." -ForegroundColor Yellow
gcloud builds submit --tag $ImageTag --project $ProjectId

# 4. Deploy or Update Cloud Run Job
Write-Host "`n[*] Deploying Cloud Run Job: $JobName..." -ForegroundColor Yellow
gcloud run jobs deploy $JobName `
    --image $ImageTag `
    --region $Region `
    --project $ProjectId `
    --memory 4Gi `
    --cpu 2 `
    --task-timeout 1800s `
    --max-retries 1 `
    --set-env-vars="GCS_BUCKET_NAME=$BucketName,PYTHONIOENCODING=utf-8,EMAIL_RECIPIENTS=vendor_aayush@letzryd.com"

# 5. Create Cloud Scheduler (4 Attempt Triggers: 7:00, 8:00, 9:00, 10:00 AM IST)
# Cron in UTC:
# 07:00 AM IST = 01:30 AM UTC
# 08:00 AM IST = 02:30 AM UTC
# 09:00 AM IST = 03:30 AM UTC
# 10:00 AM IST = 04:30 AM UTC
$Schedules = @(
    @{ Name = "uber-incentives-07am"; Cron = "30 1 * * *"; Time = "07:00 AM IST (Attempt 1)" },
    @{ Name = "uber-incentives-08am"; Cron = "30 2 * * *"; Time = "08:00 AM IST (Attempt 2 - Retry)" },
    @{ Name = "uber-incentives-09am"; Cron = "30 3 * * *"; Time = "09:00 AM IST (Attempt 3 - Retry)" },
    @{ Name = "uber-incentives-10am"; Cron = "30 4 * * *"; Time = "10:00 AM IST (Attempt 4 - Final)" }
)

foreach ($sched in $Schedules) {
    Write-Host "`n[*] Configuring Cloud Scheduler: $($sched.Name) -> $($sched.Time)..." -ForegroundColor Yellow
    gcloud scheduler jobs create http $sched.Name `
        --schedule $sched.Cron `
        --time-zone "Asia/Kolkata" `
        --uri "https://$Region-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$ProjectId/jobs/$JobName:run" `
        --http-method POST `
        --oauth-service-account-email "$ProjectId-compute@developer.gserviceaccount.com" `
        --location $Region `
        --project $ProjectId `
        2>$null

    if ($LASTEXITCODE -ne 0) {
        gcloud scheduler jobs update http $sched.Name `
            --schedule $sched.Cron `
            --time-zone "Asia/Kolkata" `
            --location $Region `
            --project $ProjectId
    }
}

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "🎉 DEPLOYMENT COMPLETE!" -ForegroundColor Green
Write-Host "Cloud Run Job: $JobName (Region: $Region)" -ForegroundColor Green
Write-Host "GCS Bucket: gs://$BucketName" -ForegroundColor Green
Write-Host "Schedule: 07:00, 08:00, 09:00, 10:00 AM IST daily" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green

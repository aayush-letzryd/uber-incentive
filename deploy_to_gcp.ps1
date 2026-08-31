<#
.SYNOPSIS
    Deploys LetzRyd Uber Incentives Automation Pipeline to Google Cloud (GCP)
    - Cloud Run Job (Headless Playwright Container)
    - GCS Cloud Storage Bucket
    - IAM Role Bindings (run.invoker, storage.objectAdmin)
    - Cloud Scheduler (Hourly Retry Schedule: 7:00, 8:10, 9:10, 10:10 AM IST)
#>

param(
    [string]$ProjectId = "letzryd-dev-test",
    [string]$Region = "asia-south1",
    [string]$JobName = "uber-incentives-job",
    [string]$BucketName = "letzryd-uber-reports",
    [string]$DbUrl = "postgresql://postgres:8S5%5DU3%40L%5EXz%29%5CFH%7D@35.200.196.113:5432/postgres"
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   DEPLOYING LETZRYD UBER INCENTIVES TO GOOGLE CLOUD" -ForegroundColor Cyan
Write-Host "   Project: $ProjectId | Region: $Region" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Enable Required GCP APIs
Write-Host "`n[*] 1. Enabling GCP Services..." -ForegroundColor Yellow
gcloud services enable run.googleapis.com `
                       cloudscheduler.googleapis.com `
                       artifactregistry.googleapis.com `
                       cloudbuild.googleapis.com `
                       storage.googleapis.com `
                       iam.googleapis.com `
                       --project $ProjectId

# 2. Grant IAM Roles to Default Compute Service Account
$ProjectNumber = (gcloud projects describe $ProjectId --format="value(projectNumber)").Trim()
$SaEmail = "$ProjectNumber-compute@developer.gserviceaccount.com"

Write-Host "`n[*] 2. Granting IAM Roles to $SaEmail..." -ForegroundColor Yellow
gcloud projects add-iam-policy-binding $ProjectId `
    --member="serviceAccount:$SaEmail" `
    --role="roles/run.invoker" `
    --condition=None 2>$null

gcloud projects add-iam-policy-binding $ProjectId `
    --member="serviceAccount:$SaEmail" `
    --role="roles/storage.objectAdmin" `
    --condition=None 2>$null

# 3. Create Cloud Storage Bucket if not exists
Write-Host "`n[*] 3. Ensuring GCS Bucket exists: gs://$BucketName..." -ForegroundColor Yellow
gsutil ls -b "gs://$BucketName" 2>$null
if ($LASTEXITCODE -ne 0) {
    gsutil mb -p $ProjectId -l $Region -b on "gs://$BucketName"
    Write-Host "[+] Bucket created: gs://$BucketName" -ForegroundColor Green
}

# 4. Sync Initial Cookies to GCS
if (Test-Path "cookies.json") {
    gsutil cp cookies.json "gs://$BucketName/sessions/cookies.json" 2>$null
}
if (Test-Path "storage_state.json") {
    gsutil cp storage_state.json "gs://$BucketName/sessions/storage_state.json" 2>$null
}

# 5. Build & Push Docker Image via Cloud Build
$ImageTag = "gcr.io/$ProjectId/$JobName:latest"
Write-Host "`n[*] 5. Building Container Image: $ImageTag..." -ForegroundColor Yellow
gcloud builds submit --tag $ImageTag --project $ProjectId

# 6. Deploy or Update Cloud Run Job
Write-Host "`n[*] 6. Deploying Cloud Run Job: $JobName..." -ForegroundColor Yellow
gcloud run jobs deploy $JobName `
    --image $ImageTag `
    --region $Region `
    --project $ProjectId `
    --memory 4Gi `
    --cpu 2 `
    --task-timeout 3600s `
    --max-retries 0 `
    --set-env-vars="GCS_BUCKET_NAME=$BucketName,DATABASE_URL=$DbUrl,PYTHONIOENCODING=utf-8,EMAIL_RECIPIENTS=vendor_aayush@letzryd.com,HEADLESS=true"

# 7. Create Cloud Scheduler (4 Attempt Triggers in IST)
# 07:00 AM IST -> 0 7 * * *
# 08:10 AM IST -> 10 8 * * *
# 09:10 AM IST -> 10 9 * * *
# 10:10 AM IST -> 10 10 * * *
$Schedules = @(
    @{ Name = "uber-incentives-07-00am"; Cron = "0 7 * * *"; Time = "07:00 AM IST (Attempt 1)" },
    @{ Name = "uber-incentives-08-10am"; Cron = "10 8 * * *"; Time = "08:10 AM IST (Attempt 2 - Retry)" },
    @{ Name = "uber-incentives-09-10am"; Cron = "10 9 * * *"; Time = "09:10 AM IST (Attempt 3 - Retry)" },
    @{ Name = "uber-incentives-10-10am"; Cron = "10 10 * * *"; Time = "10:10 AM IST (Attempt 4 - Final)" }
)

foreach ($sched in $Schedules) {
    Write-Host "`n[*] Configuring Cloud Scheduler: $($sched.Name) -> $($sched.Time)..." -ForegroundColor Yellow
    gcloud scheduler jobs create http $sched.Name `
        --schedule $sched.Cron `
        --time-zone "Asia/Kolkata" `
        --uri "https://$Region-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$ProjectId/jobs/$JobName:run" `
        --http-method POST `
        --oauth-service-account-email $SaEmail `
        --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform" `
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
Write-Host "Schedule: 07:00, 08:10, 09:10, 10:10 AM IST daily" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green

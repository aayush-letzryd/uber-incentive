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
    [string]$RepoName = "letzryd-docker",
    [string]$BucketName = "letzryd-uber-reports"
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
                       secretmanager.googleapis.com `
                       --project $ProjectId

# 2. Grant IAM Roles to Default Compute Service Account
$ProjectNumber = (gcloud projects describe $ProjectId --format="value(projectNumber)").Trim()
$SaEmail = "$ProjectNumber-compute@developer.gserviceaccount.com"

Write-Host "`n[*] 2. Granting IAM Roles to $SaEmail..." -ForegroundColor Yellow
gcloud projects add-iam-policy-binding $ProjectId `
    --member="serviceAccount:$SaEmail" `
    --role="roles/run.developer" `
    --condition=None 2>$null

gcloud projects add-iam-policy-binding $ProjectId `
    --member="serviceAccount:$SaEmail" `
    --role="roles/run.invoker" `
    --condition=None 2>$null

gcloud projects add-iam-policy-binding $ProjectId `
    --member="serviceAccount:$SaEmail" `
    --role="roles/storage.objectAdmin" `
    --condition=None 2>$null

gcloud projects add-iam-policy-binding $ProjectId `
    --member="serviceAccount:$SaEmail" `
    --role="roles/secretmanager.secretAccessor" `
    --condition=None 2>$null

# 3. Create Cloud Storage Bucket if not exists
Write-Host "`n[*] 3. Ensuring GCS Bucket exists: gs://$BucketName..." -ForegroundColor Yellow
gsutil ls -b "gs://$BucketName" 2>$null
if ($LASTEXITCODE -ne 0) {
    gsutil mb -p $ProjectId -l $Region -b on "gs://$BucketName"
    Write-Host "[+] Bucket created: gs://$BucketName" -ForegroundColor Green
}
gcloud storage buckets add-iam-policy-binding "gs://$BucketName" `
    --member="allUsers" `
    --role="roles/storage.objectViewer" 2>$null

# 4. Sync Initial Cookies to GCS
if (Test-Path "cookies.json") {
    gsutil cp cookies.json "gs://$BucketName/session/cookies.json" 2>$null
    gsutil cp cookies.json "gs://$BucketName/sessions/cookies.json" 2>$null
}
if (Test-Path "storage_state.json") {
    gsutil cp storage_state.json "gs://$BucketName/session/storage_state.json" 2>$null
    gsutil cp storage_state.json "gs://$BucketName/sessions/storage_state.json" 2>$null
}

# 4a. Setup Secrets in Secret Manager
Write-Host "`n[*] 4a. Ensuring Secrets in Secret Manager..." -ForegroundColor Yellow

# Load from .env.secrets if present
$PgPass = $env:PG_PASSWORD
$UberPass = $env:UBER_PASSWORD
$SmtpPass = $env:SMTP_PASSWORD

if (Test-Path ".env.secrets") {
    Get-Content ".env.secrets" | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line.Split("=", 2)
            $k = $parts[0].Trim()
            $v = $parts[1].Trim()
            if ($k -eq "PG_PASSWORD" -and -not $PgPass) { $PgPass = $v }
            if ($k -eq "UBER_PASSWORD" -and -not $UberPass) { $UberPass = $v }
            if ($k -eq "SMTP_PASSWORD" -and -not $SmtpPass) { $SmtpPass = $v }
        }
    }
}

# Check if secrets already exist in GCP Secret Manager
$AllSecretsExist = $true
foreach ($sec in @("PG_PASSWORD", "UBER_PASSWORD", "SMTP_PASSWORD")) {
    gcloud secrets describe $sec --project $ProjectId 2>$null
    if ($LASTEXITCODE -ne 0) {
        $AllSecretsExist = $false
        break
    }
}

if ($AllSecretsExist -and -not $PgPass -and -not $UberPass -and -not $SmtpPass) {
    Write-Host "   -> [i] Verified existing secrets (PG_PASSWORD, UBER_PASSWORD, SMTP_PASSWORD) in Secret Manager." -ForegroundColor Green
} else {
    if (-not $PgPass -or -not $UberPass -or -not $SmtpPass) {
        Write-Host "`n[!] Missing credentials for Secret Manager." -ForegroundColor Yellow
        if (-not $PgPass) { $PgPass = Read-Host -Prompt "Enter PG_PASSWORD" -AsSecureString | ForEach-Object { [System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($_)) } }
        if (-not $UberPass) { $UberPass = Read-Host -Prompt "Enter UBER_PASSWORD" -AsSecureString | ForEach-Object { [System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($_)) } }
        if (-not $SmtpPass) { $SmtpPass = Read-Host -Prompt "Enter SMTP_PASSWORD" -AsSecureString | ForEach-Object { [System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($_)) } }
    }

    function Set-GcpSecret($name, $val) {
        gcloud secrets describe $name --project $ProjectId 2>$null
        if ($LASTEXITCODE -eq 0) {
            $val | gcloud secrets versions add $name --data-file=- --project $ProjectId
        } else {
            $val | gcloud secrets create $name --data-file=- --replication-policy="automatic" --project $ProjectId
        }
    }
    if ($PgPass) { Set-GcpSecret "PG_PASSWORD" $PgPass }
    if ($UberPass) { Set-GcpSecret "UBER_PASSWORD" $UberPass }
    if ($SmtpPass) { Set-GcpSecret "SMTP_PASSWORD" $SmtpPass }
}

# 5. Ensure Artifact Registry Repository exists
Write-Host "`n[*] 5. Ensuring Artifact Registry: $RepoName..." -ForegroundColor Yellow
gcloud artifacts repositories describe $RepoName --location $Region --project $ProjectId 2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud artifacts repositories create $RepoName `
        --repository-format=docker `
        --location=$Region `
        --description="Docker repo for LetzRyd" `
        --project $ProjectId
}

# 6. Build & Push Docker Image via Cloud Build
$ImageTag = "$Region-docker.pkg.dev/$ProjectId/$RepoName/${JobName}:latest"
Write-Host "`n[*] 6. Building Container Image: $ImageTag..." -ForegroundColor Yellow
gcloud builds submit --tag $ImageTag --project $ProjectId

# 7. Deploy Cloud Run Job
Write-Host "`n[*] 7. Deploying Cloud Run Job: $JobName..." -ForegroundColor Yellow
gcloud run jobs deploy $JobName `
    --image $ImageTag `
    --region $Region `
    --project $ProjectId `
    --memory 4Gi `
    --cpu 2 `
    --task-timeout 3600s `
    --max-retries 0 `
    --set-env-vars="GCS_BUCKET_NAME=$BucketName,PYTHONIOENCODING=utf-8,EMAIL_RECIPIENTS=vendor_aayush@letzryd.com,HEADLESS=true,PG_HOST=35.200.196.113,PG_PORT=5432,PG_DATABASE=postgres,PG_USER=postgres,UBER_EMAIL=uber.india@letzryd.com,SHEET_ID=$($env:SHEET_ID)" `
    --set-secrets="PG_PASSWORD=PG_PASSWORD:latest,UBER_PASSWORD=UBER_PASSWORD:latest,SMTP_PASSWORD=SMTP_PASSWORD:latest"

# 8. Create / Update Cloud Scheduler
$Schedules = @(
    @{ Name = "uber-incentives-07-00am"; Cron = "0 7 * * *"; Time = "07:00 AM IST (Attempt 1)" },
    @{ Name = "uber-incentives-08-10am"; Cron = "10 8 * * *"; Time = "08:10 AM IST (Attempt 2 - Retry)" },
    @{ Name = "uber-incentives-09-10am"; Cron = "10 9 * * *"; Time = "09:10 AM IST (Attempt 3 - Retry)" },
    @{ Name = "uber-incentives-10-10am"; Cron = "10 10 * * *"; Time = "10:10 AM IST (Attempt 4 - Final)" }
)

$SchedulerUri = "https://$Region-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$ProjectId/jobs/${JobName}:run"

foreach ($sched in $Schedules) {
    Write-Host "`n[*] Configuring Cloud Scheduler: $($sched.Name) -> $($sched.Time)..." -ForegroundColor Yellow
    gcloud scheduler jobs describe $sched.Name --location $Region --project $ProjectId 2>$null
    if ($LASTEXITCODE -eq 0) {
        gcloud scheduler jobs update http $sched.Name `
            --schedule $sched.Cron `
            --time-zone "Asia/Kolkata" `
            --uri $SchedulerUri `
            --http-method POST `
            --oauth-service-account-email $SaEmail `
            --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform" `
            --location $Region `
            --project $ProjectId
    } else {
        gcloud scheduler jobs create http $sched.Name `
            --schedule $sched.Cron `
            --time-zone "Asia/Kolkata" `
            --uri $SchedulerUri `
            --http-method POST `
            --oauth-service-account-email $SaEmail `
            --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform" `
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

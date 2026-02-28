# TheWatcher Canary Check — verify cloud API connectivity from this machine
# Run this to debug when watcher reports API failures
# Usage: powershell aws/test_watcher_canary.ps1

$env:Path += ';C:\Program Files\Amazon\AWSCLIV2;C:\google-cloud-sdk\bin'

# Load cloud config
$ProjectDir = 'c:\libraries\PrismataAI'
$CloudConfigFile = Join-Path $ProjectDir 'cloud-config.env'
if (Test-Path $CloudConfigFile) {
    Get-Content $CloudConfigFile | ForEach-Object {
        if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.+)$' -and $_ -notmatch '^\s*#') {
            Set-Variable -Name $Matches[1] -Value $Matches[2].Trim()
        }
    }
}
$AwsRegion = if ($AWS_REGION) { $AWS_REGION } else { 'eu-north-1' }
$Bucket = if ($CLOUD_BUCKET) { $CLOUD_BUCKET } else { 'prismata-selfplay-data' }

Write-Host "=== Cloud API Canary Check ==="
Write-Host ""

# AWS EC2
Write-Host "--- AWS EC2 ---"
try {
    $awsResult = aws ec2 describe-instances --filters 'Name=tag:Name,Values=PrismataSelfPlay-*' --query 'Reservations[].Instances[].[InstanceId,State.Name]' --output table --region $AwsRegion 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[PASS] AWS EC2 API reachable"
        Write-Host $awsResult
    } else {
        Write-Host "[FAIL] AWS EC2 API returned exit code $LASTEXITCODE"
        Write-Host $awsResult
    }
} catch {
    Write-Host "[FAIL] AWS EC2 API exception: $($_.Exception.Message)"
}

Write-Host ""

# AWS Quotas
Write-Host "--- AWS Quotas ---"
try {
    $quota = aws service-quotas get-service-quota --service-code ec2 --quota-code L-1216C47A --region $AwsRegion --query 'Quota.Value' --output text 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[PASS] AWS Quotas API reachable (on-demand vCPUs: $quota)"
    } else {
        Write-Host "[FAIL] AWS Quotas API returned exit code $LASTEXITCODE"
    }
} catch {
    Write-Host "[FAIL] AWS Quotas API exception: $($_.Exception.Message)"
}

Write-Host ""

# GCP
Write-Host "--- GCP Compute Engine ---"
try {
    $gcpResult = gcloud.cmd compute instances list --project=prismata-selfplay --filter="name~'^prismata-selfplay-'" --format="table(name,zone,machineType,status)" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[PASS] GCP API reachable"
        Write-Host $gcpResult
    } else {
        Write-Host "[FAIL] GCP API returned exit code $LASTEXITCODE"
        Write-Host $gcpResult
    }
} catch {
    Write-Host "[FAIL] GCP API exception: $($_.Exception.Message)"
}

Write-Host ""

# S3
Write-Host "--- S3 Bucket ---"
try {
    $s3Count = aws s3api list-objects-v2 --bucket $Bucket --prefix results/ --query 'KeyCount' --output text --region $AwsRegion 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[PASS] S3 reachable (objects in results/: $s3Count)"
    } else {
        Write-Host "[FAIL] S3 returned exit code $LASTEXITCODE"
    }
} catch {
    Write-Host "[FAIL] S3 exception: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "=== Canary Check Complete ==="

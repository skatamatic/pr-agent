# ---------------------------------------------------------------------------
# setup-cicd-gcp.ps1  --  One-run script to provision GCP infrastructure and
# set up a Cloud Build CI/CD pipeline for the PR-Agent Dashboard.
#
# What it does:
#   1. Provisions all GCP infra via Terraform (Cloud SQL, VPC, Artifact
#      Registry, Secret Manager, Cloud Run, Scheduler).
#   2. Builds and deploys the dashboard backend + frontend for the first time.
#   3. Creates a Cloud Build trigger connected to your GitHub repo so that
#      subsequent pushes to the appropriate branch automatically build and
#      deploy.
#
# Prerequisites: gcloud, terraform, docker, gh (GitHub CLI)
#
# Usage:
#   .\scripts\setup-cicd-gcp.ps1 -Env dev -Project my-gcp-project
#   .\scripts\setup-cicd-gcp.ps1 -Env prod -Project my-gcp-project -Region us-east1
#   .\scripts\setup-cicd-gcp.ps1 -Env stage -Project my-gcp-project -AutoApprove
#   .\scripts\setup-cicd-gcp.ps1 -Env all -Project my-gcp-project -AutoApprove
# ---------------------------------------------------------------------------

param(
    [Parameter(Mandatory)][ValidateSet('dev','stage','prod','all')][string]$Env,
    [Parameter(Mandatory)][string]$Project,
    [string]$Region = "us-central1",
    [switch]$AutoApprove,
    [switch]$SkipDeploy
)

$ErrorActionPreference = "Stop"

$RepoRoot   = (Get-Item $PSScriptRoot).Parent.FullName
$ScriptPath = $PSCommandPath

# ========================== "all" mode handler =============================

if ($Env -eq 'all') {
    Write-Host "============================================================"
    Write-Host "  PR-Agent Dashboard CI/CD Setup -- ALL ENVIRONMENTS"
    Write-Host "============================================================"
    Write-Host "  Project : $Project"
    Write-Host "  Region  : $Region"
    Write-Host "============================================================"
    Write-Host ""

    # --- Detect GitHub repo ---
    $GitHubRepo = ""
    try { $GitHubRepo = gh repo view --json nameWithOwner -q '.nameWithOwner' 2>$null } catch {}
    if (-not $GitHubRepo) {
        $RemoteUrl = git remote get-url origin 2>$null
        if ($RemoteUrl -match 'github\.com[:/]([^/]+/[^/.]+)') {
            $GitHubRepo = $Matches[1]
        }
    }
    if (-not $GitHubRepo) { throw "Could not detect GitHub repo." }
    Write-Host "  Repository: $GitHubRepo"
    Write-Host ""

    # --- Ensure required branches exist ---
    Write-Host "=== Ensuring required branches exist ==="
    $MainRef = git ls-remote --heads origin main 2>$null
    if (-not $MainRef) { throw "'main' branch not found on remote. Push your main branch first." }
    $MainSha = ($MainRef -split '\s+')[0]
    Write-Host "  main   : $($MainSha.Substring(0,8)) (exists)"

    foreach ($ReqBranch in @('develop','staging')) {
        $BranchRef = git ls-remote --heads origin $ReqBranch 2>$null
        if ($BranchRef) {
            $BranchSha = ($BranchRef -split '\s+')[0]
            Write-Host "  ${ReqBranch} : $($BranchSha.Substring(0,8)) (exists)"
        } else {
            Write-Host "  ${ReqBranch} : missing -- creating from main ..."
            gh api "repos/$GitHubRepo/git/refs" -f "ref=refs/heads/$ReqBranch" -f "sha=$MainSha" --silent
            git fetch origin $ReqBranch 2>$null
            Write-Host "    Created '$ReqBranch'"
        }
    }
    Write-Host ""

    # --- Recurse for each environment ---
    $ExtraArgs = @()
    if ($AutoApprove) { $ExtraArgs += '-AutoApprove' }
    if ($SkipDeploy)  { $ExtraArgs += '-SkipDeploy' }

    foreach ($DeployEnv in @('dev','stage','prod')) {
        Write-Host ""
        Write-Host "########################################################################"
        Write-Host "##  Deploying environment: $DeployEnv"
        Write-Host "########################################################################"
        Write-Host ""
        & $ScriptPath -Env $DeployEnv -Project $Project -Region $Region @ExtraArgs
        if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
            throw "Deployment of '$DeployEnv' failed with exit code $LASTEXITCODE"
        }
    }

    Write-Host ""
    Write-Host "============================================================"
    Write-Host "  All environments deployed successfully!"
    Write-Host "============================================================"
    Write-Host "  Environments: dev, stage, prod"
    Write-Host "  Project:      $Project"
    Write-Host "  Region:       $Region"
    Write-Host ""
    Write-Host "  Push to 'develop' -> deploys dev"
    Write-Host "  Push to 'staging' -> deploys stage"
    Write-Host "  Push to 'main'    -> deploys prod"
    Write-Host ""
    Write-Host "  Monitor builds:"
    Write-Host "    https://console.cloud.google.com/cloud-build/builds?project=$Project"
    Write-Host "============================================================"
    exit 0
}

# ========================== Environment mapping ============================

switch ($Env) {
    'dev'   { $Branch = "develop";  $Prefix = "pr-agent-dash-dev" }
    'stage' { $Branch = "staging";  $Prefix = "pr-agent-dash-stage" }
    'prod'  { $Branch = "main";     $Prefix = "pr-agent-dash" }
}

$RepoId        = "$Prefix-repo"
$StatePrefix   = "pr-agent-dash/$Env/state"
$TfStateBucket = "$Project-tfstate"
$Registry      = "$Region-docker.pkg.dev"
$ImageBase     = "$Registry/$Project/$RepoId"
$BackendImage  = "$ImageBase/backend:latest"
$FrontendImage = "$ImageBase/frontend:latest"
$ConnName      = "$Prefix-github"
$TriggerName   = "$Prefix-deploy"

$TfDir = Join-Path $RepoRoot "terraform\gcp"

Write-Host "============================================================"
Write-Host "  PR-Agent Dashboard CI/CD Setup"
Write-Host "============================================================"
Write-Host "  Environment : $Env"
Write-Host "  Branch      : $Branch"
Write-Host "  Project     : $Project"
Write-Host "  Region      : $Region"
Write-Host "  Prefix      : $Prefix"
Write-Host "  Repo ID     : $RepoId"
Write-Host "  TF state    : gs://$TfStateBucket/$StatePrefix"
Write-Host "============================================================"
Write-Host ""

# ========================== Prerequisites ==================================

Write-Host "=== Checking prerequisites ==="

foreach ($cmd in @('gcloud','terraform','docker','gh')) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        throw "'$cmd' is required but not found in PATH."
    }
}
Write-Host "  All tools found: gcloud, terraform, docker, gh"

gcloud config set project $Project --quiet
$Account = gcloud config get-value account 2>$null
if (-not $Account) {
    throw "gcloud is not authenticated. Run 'gcloud auth login' first."
}
Write-Host "  gcloud authenticated as: $Account"

# ========================== Detect GitHub repo =============================

Write-Host ""
Write-Host "=== Detecting GitHub repository ==="

$GitHubRepo = ""
try {
    $GitHubRepo = gh repo view --json nameWithOwner -q '.nameWithOwner' 2>$null
} catch {}

if (-not $GitHubRepo) {
    $RemoteUrl = git remote get-url origin 2>$null
    if ($RemoteUrl -match 'github\.com[:/]([^/]+/[^/.]+)') {
        $GitHubRepo = $Matches[1]
    }
}

if (-not $GitHubRepo) {
    throw "Could not detect GitHub repo. Ensure 'gh' is authenticated or 'git remote origin' points to a GitHub repo."
}

$GitHubOwner    = $GitHubRepo.Split('/')[0]
$GitHubRepoName = $GitHubRepo.Split('/')[1]
$GitHubRemoteUri = "https://github.com/$GitHubRepo.git"

Write-Host "  Repository: $GitHubRepo"
Write-Host "  Owner:      $GitHubOwner"
Write-Host "  Remote URI: $GitHubRemoteUri"

# ========================== Enable GCP APIs ================================

Write-Host ""
Write-Host "=== Enabling GCP APIs ==="

$Apis = @(
    "cloudbuild.googleapis.com",
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "compute.googleapis.com",
    "servicenetworking.googleapis.com",
    "vpcaccess.googleapis.com",
    "storage.googleapis.com",
    "cloudscheduler.googleapis.com",
    "iam.googleapis.com"
)

foreach ($api in $Apis) {
    Write-Host "  Enabling $api ..."
    gcloud services enable $api --quiet 2>$null
}
Write-Host "  All APIs enabled."

# ========================== Terraform state bucket =========================

Write-Host ""
Write-Host "=== Setting up Terraform state bucket ==="

$BucketExists = $false
$bucketCheck = gcloud storage buckets describe "gs://$TfStateBucket" --format="value(name)" 2>$null
if ($LASTEXITCODE -eq 0 -and $bucketCheck) {
    $BucketExists = $true
}

if ($BucketExists) {
    Write-Host "  Bucket gs://$TfStateBucket already exists."
} else {
    Write-Host "  Creating gs://$TfStateBucket ..."
    gcloud storage buckets create "gs://$TfStateBucket" --location=$Region --project=$Project --uniform-bucket-level-access
    if ($LASTEXITCODE -ne 0) { throw "Failed to create state bucket" }
    gcloud storage buckets update "gs://$TfStateBucket" --versioning
    Write-Host "  Bucket created with versioning enabled."
}

# ========================== Generate Terraform files =======================

Write-Host ""
Write-Host "=== Generating Terraform configuration ==="

@"
terraform {
  backend "gcs" {
    bucket = "$TfStateBucket"
    prefix = "$StatePrefix"
  }
}
"@ | Set-Content -Path (Join-Path $TfDir "backend.tf") -Encoding UTF8
Write-Host "  Generated backend.tf (state: gs://$TfStateBucket/$StatePrefix)"

@"
# Generated by setup-cicd-gcp.ps1 (env=$Env) -- do not commit secrets.
project_id = "$Project"
region     = "$Region"
prefix     = "$Prefix"
"@ | Set-Content -Path (Join-Path $TfDir "terraform.tfvars") -Encoding UTF8
Write-Host "  Generated terraform.tfvars (prefix=$Prefix)"

# ========================== Terraform init + apply (infra) =================

Write-Host ""
Write-Host "=== Terraform init ==="
Push-Location $TfDir
try {
    terraform init -input=false -reconfigure
    if ($LASTEXITCODE -ne 0) { throw "terraform init failed" }

    Write-Host ""
    Write-Host "=== Terraform apply (infrastructure; no images yet) ==="
    $tfApplyArgs = @("-input=false")
    if ($AutoApprove) { $tfApplyArgs += "-auto-approve" }
    terraform apply @tfApplyArgs
    if ($LASTEXITCODE -ne 0) { throw "terraform apply failed" }

    # ========================== Initial build + deploy =========================

    if ($SkipDeploy) {
        Write-Host ""
        Write-Host "=== Skipping initial Docker build/deploy (-SkipDeploy) ==="
    } else {
        Write-Host ""
        Write-Host "=== Configuring Docker for Artifact Registry ==="
        gcloud auth configure-docker $Registry --quiet

        Write-Host ""
        Write-Host "=== Building and pushing backend ==="
        Push-Location $RepoRoot
        try {
            docker build -f dashboard/backend/Dockerfile -t $BackendImage .
            if ($LASTEXITCODE -ne 0) { throw "docker build backend failed" }
            docker push $BackendImage
            if ($LASTEXITCODE -ne 0) { throw "docker push backend failed" }
        } finally { Pop-Location }

        Write-Host ""
        Write-Host "=== Deploying backend via Terraform ==="
        $tfApplyArgs = @("-input=false", "-var=backend_image=$BackendImage")
        if ($AutoApprove) { $tfApplyArgs += "-auto-approve" }
        terraform apply @tfApplyArgs
        if ($LASTEXITCODE -ne 0) { throw "terraform apply (backend) failed" }

        $BackendUrl = terraform output -raw backend_url 2>$null
        if (-not $BackendUrl -or $BackendUrl -eq "null") {
            throw "backend_url output missing after deploy."
        }
        $WsUrl = ($BackendUrl -replace '^https', 'wss' -replace '/$', '') + "/ws"

        Write-Host ""
        Write-Host "=== Building and pushing frontend (API_URL=$BackendUrl) ==="
        Push-Location $RepoRoot
        try {
            docker build -f dashboard/frontend/Dockerfile `
                --build-arg "REACT_APP_API_URL=$BackendUrl" `
                --build-arg "REACT_APP_WS_URL=$WsUrl" `
                -t $FrontendImage .
            if ($LASTEXITCODE -ne 0) { throw "docker build frontend failed" }
            docker push $FrontendImage
            if ($LASTEXITCODE -ne 0) { throw "docker push frontend failed" }
        } finally { Pop-Location }

        Write-Host ""
        Write-Host "=== Deploying frontend + setting CORS URLs ==="
        $tfApplyArgs = @(
            "-input=false",
            "-var=backend_image=$BackendImage",
            "-var=frontend_image=$FrontendImage",
            "-var=backend_base_url=$BackendUrl",
            "-var=frontend_base_url="
        )
        if ($AutoApprove) { $tfApplyArgs += "-auto-approve" }
        terraform apply @tfApplyArgs
        if ($LASTEXITCODE -ne 0) { throw "terraform apply (frontend) failed" }

        $FrontendUrl = terraform output -raw frontend_url 2>$null
        if ($FrontendUrl -and $FrontendUrl -ne "null") {
            Write-Host "=== Second Terraform apply (frontend_base_url for CORS) ==="
            $tfApplyArgs = @(
                "-input=false",
                "-var=backend_image=$BackendImage",
                "-var=frontend_image=$FrontendImage",
                "-var=backend_base_url=$BackendUrl",
                "-var=frontend_base_url=$FrontendUrl"
            )
            if ($AutoApprove) { $tfApplyArgs += "-auto-approve" }
            terraform apply @tfApplyArgs
            if ($LASTEXITCODE -ne 0) { throw "terraform apply (CORS) failed" }
        }

        Write-Host ""
        Write-Host "=== Waiting for backend health (up to 120s) ==="
        $healthy = $false
        for ($i = 1; $i -le 24; $i++) {
            try {
                $r = Invoke-WebRequest -Uri "$BackendUrl/api/health" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
                if ($r.StatusCode -eq 200) { Write-Host "  Backend healthy."; $healthy = $true; break }
            } catch {}
            Write-Host "  Attempt $i/24 ..."
            Start-Sleep -Seconds 5
        }
        if (-not $healthy) { Write-Host "  Warning: health check did not succeed; deployment may still be rolling out." }
    }

    # ========================== Cloud Build SA permissions ======================

    Write-Host ""
    Write-Host "=== Granting Cloud Build service account permissions ==="

    $ProjectNumber = gcloud projects describe $Project --format='value(projectNumber)'
    $CbSa = "$ProjectNumber@cloudbuild.gserviceaccount.com"

    $CbRoles = @(
        "roles/run.admin",
        "roles/iam.serviceAccountUser",
        "roles/artifactregistry.writer",
        "roles/secretmanager.secretAccessor",
        "roles/storage.objectViewer"
    )

    foreach ($role in $CbRoles) {
        Write-Host "  Granting $role to Cloud Build SA ..."
        gcloud projects add-iam-policy-binding $Project `
            --member="serviceAccount:$CbSa" `
            --role=$role `
            --condition=None `
            --quiet 2>$null | Out-Null
    }
    Write-Host "  Cloud Build SA permissions configured."

    # ========================== Cloud Build GitHub connection ===================

    Write-Host ""
    Write-Host "=== Setting up Cloud Build GitHub connection ==="
    Write-Host "  (This may open a browser for one-time GitHub OAuth authorization.)"
    Write-Host ""

    $ExistingConn = ""
    try {
        $ExistingConn = gcloud builds connections describe $ConnName `
            --region=$Region --format='value(name)' 2>$null
    } catch {}

    if ($ExistingConn) {
        Write-Host "  Connection '$ConnName' already exists."
    } else {
        Write-Host "  Creating connection '$ConnName' ..."
        gcloud builds connections create github $ConnName --region=$Region
        Write-Host "  Connection created."
    }

    Write-Host "  Verifying connection installation state ..."
    Write-Host "  If prompted, authorize the Cloud Build GitHub App in your browser."
    $ConnReady = $false
    for ($i = 1; $i -le 18; $i++) {
        $State = ""
        try {
            $State = gcloud builds connections describe $ConnName `
                --region=$Region --format='value(installationState.stage)' 2>$null
        } catch {}
        if ($State -eq "COMPLETE") {
            Write-Host "  Connection installation: COMPLETE"
            $ConnReady = $true
            break
        }
        if ($State -eq "PENDING_INSTALL_APP") {
            try {
                $AuthUrl = gcloud builds connections describe $ConnName `
                    --region=$Region --format='value(installationState.actionUri)' 2>$null
                if ($AuthUrl) {
                    Write-Host "  Action required: authorize Cloud Build at:"
                    Write-Host "    $AuthUrl"
                }
            } catch {}
        }
        $StateDisplay = if ($State) { $State } else { 'pending' }
        Write-Host "  Installation state: $StateDisplay (attempt $i/18, waiting 10s) ..."
        Start-Sleep -Seconds 10
    }

    if (-not $ConnReady) {
        Write-Host ""
        throw "GitHub connection did not reach COMPLETE state within 3 minutes. Authorize the Cloud Build GitHub App, then re-run this script. (The script is idempotent -- it will skip already-completed steps.)"
    }

    # ========================== Link GitHub repository =========================

    Write-Host ""
    Write-Host "=== Linking GitHub repository ==="

    $CbRepoName = "$GitHubRepoName-$Env"
    $ExistingRepo = ""
    try {
        $ExistingRepo = gcloud builds repositories describe $CbRepoName `
            --connection=$ConnName --region=$Region --format='value(name)' 2>$null
    } catch {}

    if ($ExistingRepo) {
        Write-Host "  Repository link '$CbRepoName' already exists."
    } else {
        Write-Host "  Linking $GitHubRemoteUri as '$CbRepoName' ..."
        gcloud builds repositories create $CbRepoName `
            --connection=$ConnName `
            --region=$Region `
            --remote-uri=$GitHubRemoteUri
        Write-Host "  Repository linked."
    }

    $RepoResource = "projects/$Project/locations/$Region/connections/$ConnName/repositories/$CbRepoName"

    # ========================== Create Cloud Build trigger =====================

    Write-Host ""
    Write-Host "=== Creating Cloud Build trigger ==="

    $ExistingTrigger = ""
    try {
        $ExistingTrigger = gcloud builds triggers describe $TriggerName `
            --region=$Region --format='value(name)' 2>$null
    } catch {}

    if ($ExistingTrigger) {
        Write-Host "  Trigger '$TriggerName' already exists. Replacing ..."
        gcloud builds triggers delete $TriggerName --region=$Region --quiet 2>$null
    }

    gcloud builds triggers create github `
        --name=$TriggerName `
        --region=$Region `
        --repository=$RepoResource `
        --branch-pattern="^$Branch$" `
        --build-config="cloudbuild-deploy.yaml" `
        --included-files="dashboard/**,terraform/gcp/**,cloudbuild-deploy.yaml" `
        --substitutions="_REGION=$Region,_REPO_ID=$RepoId,_PREFIX=$Prefix"

    Write-Host "  Trigger '$TriggerName' created."
    Write-Host "  Branch filter: ^$Branch$"
    Write-Host "  Watched paths: dashboard/**, terraform/gcp/**, cloudbuild-deploy.yaml"

    # ========================== Summary ========================================

    Write-Host ""
    Write-Host "============================================================"
    Write-Host "  CI/CD Setup Complete!"
    Write-Host "============================================================"
    Write-Host ""
    Write-Host "  Environment : $Env"
    Write-Host "  Project     : $Project"
    Write-Host "  Region      : $Region"
    Write-Host ""

    if (-not $SkipDeploy) {
        $BackendUrl  = terraform output -raw backend_url 2>$null
        $FrontendUrl = terraform output -raw frontend_url 2>$null
        $ApiKey      = terraform output -raw dashboard_api_key 2>$null
        $ConfigBucket = terraform output -raw config_bucket 2>$null

        $BuDisplay = if ($BackendUrl)  { $BackendUrl }  else { 'n/a' }
        $FuDisplay = if ($FrontendUrl) { $FrontendUrl } else { 'n/a' }
        Write-Host "  Backend URL : $BuDisplay"
        Write-Host "  Frontend URL: $FuDisplay"
        Write-Host ""
        if ($ApiKey -and $ApiKey -ne "null") {
            Write-Host "  DASHBOARD_API_KEY: $ApiKey"
            Write-Host "  (Set this in PR-Agent env or pipeline secrets.)"
            Write-Host ""
        }
        if ($ConfigBucket -and $ConfigBucket -ne "null") {
            Write-Host "  Config bucket: PR_AGENT_CONFIG_GCS_BUCKET=$ConfigBucket"
            Write-Host ""
        }
    }

    Write-Host "  Cloud Build trigger: $TriggerName"
    Write-Host "  Watches branch:      $Branch"
    Write-Host ""
    Write-Host "  Push to '$Branch' to trigger an automatic build + deploy."
    Write-Host "  Monitor builds: https://console.cloud.google.com/cloud-build/builds?project=$Project"
    Write-Host ""
    Write-Host "  To re-run infra changes manually:"
    Write-Host "    cd terraform/gcp; terraform apply"
    Write-Host "============================================================"

} finally {
    Pop-Location
}

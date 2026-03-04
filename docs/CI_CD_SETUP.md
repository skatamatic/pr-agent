# CI/CD Setup Guide for PR-Agent Dashboard on GCP

This guide covers the automated CI/CD pipeline for the PR-Agent Dashboard, including initial infrastructure provisioning, continuous deployment via Cloud Build, environment isolation, and self-hosted runner VM management.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Environment Configuration](#environment-configuration)
- [What the Setup Script Does](#what-the-setup-script-does)
- [The `all` Mode](#the-all-mode)
- [How CI/CD Works After Setup](#how-cicd-works-after-setup)
- [Environment Isolation](#environment-isolation)
- [Self-Hosted Runner VMs](#self-hosted-runner-vms)
- [Scripts Reference](#scripts-reference)
- [Terraform Variables](#terraform-variables)
- [Cloud Build Configuration](#cloud-build-configuration)
- [Day-2 Operations](#day-2-operations)
- [Troubleshooting](#troubleshooting)

---

## Overview

The CI/CD system uses a **two-phase approach**:

1. **Initial setup** (one-time, scripted): A single script provisions all GCP infrastructure via Terraform and configures Cloud Build triggers connected to your GitHub repository.
2. **Continuous deployment** (automatic): Every push to the designated branch triggers Cloud Build, which builds new Docker images and updates the running Cloud Run services without touching infrastructure configuration.

This separation keeps CI/CD fast (image swap only) while infrastructure changes remain intentional and reviewable via Terraform.

## Architecture

```
GitHub Repository
    │
    ├── develop  ──→  Cloud Build Trigger (dev)  ──→  Cloud Run (dev)
    ├── staging  ──→  Cloud Build Trigger (stage) ──→  Cloud Run (stage)
    └── main     ──→  Cloud Build Trigger (prod)  ──→  Cloud Run (prod)
```

Each environment gets its own fully isolated set of GCP resources:

| Component              | Naming Pattern                          |
|------------------------|-----------------------------------------|
| VPC network            | `{prefix}-vpc`                          |
| Cloud SQL instance     | `{prefix}-sql`                          |
| Artifact Registry repo | `{prefix}-repo`                         |
| Secret Manager secrets | `{prefix}-database-url`, etc.           |
| GCS config bucket      | `{project}-{prefix}-config`             |
| Cloud Run backend      | `{prefix}-backend`                      |
| Cloud Run frontend     | `{prefix}-frontend`                     |
| Cloud Scheduler job    | `{prefix}-run-job-timeout`              |
| Cloud Build trigger    | `{prefix}-deploy`                       |
| Cloud Build connection | `{prefix}-github`                       |
| Runner VMs             | `{prefix}-runner-{id}`                  |
| Terraform state        | `gs://{project}-tfstate/pr-agent-dash/{env}/state` |

## Prerequisites

| Tool        | Version   | Purpose                              |
|-------------|-----------|--------------------------------------|
| `gcloud`    | Latest    | GCP SDK; must be authenticated       |
| `terraform` | >= 1.0    | Infrastructure provisioning          |
| `docker`    | Latest    | Building container images            |
| `gh`        | Latest    | GitHub CLI; must be authenticated    |

**GCP permissions**: The authenticated `gcloud` account needs **Owner** or **Editor** role on the target project (to enable APIs, create resources, and manage IAM).

**Authenticate before running**:

```bash
gcloud auth login
gcloud auth application-default login   # for Terraform
gh auth login                           # for GitHub branch creation in 'all' mode
```

## Quick Start

### Single environment

```bash
# Bash (Linux / macOS / WSL / Git Bash)
./scripts/setup-cicd-gcp.sh --env dev --project my-gcp-project

# PowerShell (Windows)
.\scripts\setup-cicd-gcp.ps1 -Env dev -Project my-gcp-project
```

### All environments at once

```bash
# Bash
./scripts/setup-cicd-gcp.sh --env all --project my-gcp-project --auto-approve

# PowerShell
.\scripts\setup-cicd-gcp.ps1 -Env all -Project my-gcp-project -AutoApprove
```

The `all` mode deploys **dev**, **stage**, and **prod** sequentially. It creates any missing GitHub branches (`develop`, `staging`) from `main` before starting.

## Environment Configuration

### Environment-to-Branch Mapping

| Environment | Git Branch | Terraform Prefix          |
|-------------|------------|---------------------------|
| `dev`       | `develop`  | `pr-agent-dash-dev`       |
| `stage`     | `staging`  | `pr-agent-dash-stage`     |
| `prod`      | `main`     | `pr-agent-dash`           |
| `all`       | (all above)| (all above, sequentially) |

### Terraform State Isolation

Each environment stores its state independently:

```
gs://{project}-tfstate/
  └── pr-agent-dash/
      ├── dev/state/
      ├── stage/state/
      └── prod/state/
```

A single GCS bucket with versioning holds all state files. The `prefix` key in the Terraform backend configuration ensures complete isolation.

## What the Setup Script Does

The script is **idempotent** -- you can safely re-run it if something fails partway through. Each step checks whether the resource already exists before creating it.

### Step-by-step breakdown

| Step | Action | Details |
|------|--------|---------|
| 1 | **Validate prerequisites** | Checks `gcloud`, `terraform`, `docker`, `gh` are in PATH |
| 2 | **Detect GitHub repo** | Uses `gh repo view` or parses `git remote origin` |
| 3 | **Enable GCP APIs** | Cloud Build, Cloud Run, Cloud SQL, Secret Manager, Artifact Registry, Compute, VPC Access, Storage, Scheduler, IAM |
| 4 | **Create Terraform state bucket** | `{project}-tfstate` in GCS with versioning |
| 5 | **Generate Terraform config** | Writes `backend.tf` (state location) and `terraform.tfvars` (project, region, prefix) |
| 6 | **Terraform init + apply (infra only)** | Provisions VPC, Cloud SQL, Artifact Registry, Secret Manager, GCS config bucket, VPC connector |
| 7 | **Build + push backend image** | `docker build` from repo root, push to Artifact Registry |
| 8 | **Deploy backend via Terraform** | Passes `backend_image` var; creates Cloud Run backend service |
| 9 | **Build + push frontend image** | Builds with `REACT_APP_API_URL` and `REACT_APP_WS_URL` from backend URL |
| 10 | **Deploy frontend + CORS** | Two-pass Terraform: first deploys frontend, then re-applies with `frontend_base_url` for CORS |
| 11 | **Health check** | Polls `GET /api/health` for up to 120 seconds |
| 12 | **Grant Cloud Build SA permissions** | `roles/run.admin`, `roles/iam.serviceAccountUser`, `roles/artifactregistry.writer`, `roles/secretmanager.secretAccessor`, `roles/storage.objectViewer` |
| 13 | **Create GitHub connection** | Cloud Build 2nd-gen GitHub connection (one-time browser OAuth) |
| 14 | **Link repository** | Registers the GitHub repo with the Cloud Build connection |
| 15 | **Create trigger** | Branch pattern, path filters, substitutions for the environment |

### Secrets auto-generation

The following secrets are automatically generated if not provided:

| Secret | Variable | Generated Length |
|--------|----------|-----------------|
| Database password | `db_user_password` | 24 chars, alphanumeric |
| Cron secret | `cron_secret` | 32 chars, alphanumeric |
| Dashboard API key | `dashboard_api_key` | 32 chars, alphanumeric |

All secrets are stored in **Secret Manager** and injected into Cloud Run at runtime. The deploy script prints the `DASHBOARD_API_KEY` at the end so you can configure it in your PR-Agent pipelines.

## The `all` Mode

When you pass `--env all`, the script:

1. **Detects the GitHub repository** from `gh` or `git remote origin`.
2. **Verifies the `main` branch exists** on the remote.
3. **Creates missing branches**: Checks if `develop` and `staging` exist on the remote. If either is missing, it creates the branch from `main`'s current HEAD using the GitHub API (`gh api repos/.../git/refs`).
4. **Runs setup sequentially** for `dev`, `stage`, and `prod`, invoking itself with each environment. All flags (`--auto-approve`, `--skip-deploy`, `--region`) are forwarded.

This gives you a full three-environment pipeline from a single command. The GitHub connection OAuth is typically required only during the first environment's setup; subsequent environments reuse the installed GitHub App.

## How CI/CD Works After Setup

### Trigger configuration

Each environment's Cloud Build trigger watches:

- **Branch**: `^develop$` (dev), `^staging$` (stage), `^main$` (prod)
- **Paths**: `dashboard/**`, `terraform/gcp/**`, `cloudbuild-deploy.yaml`

Only pushes that modify files in these paths trigger a build.

### Build pipeline (`cloudbuild-deploy.yaml`)

```
 ┌─────────────────────┐
 │ get-backend-url      │  Resolve current backend URL for frontend build
 └─────────┬───────────┘
           │
 ┌─────────┴───────────┐    ┌──────────────────┐
 │ build-backend        │    │ build-frontend    │  (parallel, needs URL)
 └─────────┬───────────┘    └────────┬─────────┘
           │                          │
 ┌─────────┴───────────┐    ┌────────┴─────────┐
 │ push-backend         │    │ push-frontend     │  (SHORT_SHA + latest tags)
 └─────────┬───────────┘    └────────┬─────────┘
           │                          │
 ┌─────────┴───────────┐    ┌────────┴─────────┐
 │ deploy-backend       │    │ deploy-frontend   │  (gcloud run services update)
 └─────────────────────┘    └──────────────────┘
```

The deployment uses `gcloud run services update --image`, which:

- Swaps the container image to the new version
- **Preserves** all existing env vars, secrets, VPC connector, scaling settings, and IAM
- Creates a new Cloud Run revision with zero downtime
- Does **not** run Terraform (no state locking, no infrastructure changes)

### Image tagging

Each build tags images with both `SHORT_SHA` (the commit hash) and `latest`:

- `{region}-docker.pkg.dev/{project}/{repo}/backend:{SHORT_SHA}`
- `{region}-docker.pkg.dev/{project}/{repo}/backend:latest`

Cloud Run deploys the `SHORT_SHA` tag for traceability. The `latest` tag is available for manual pulls or runner VMs.

## Environment Isolation

All environments deployed within the same GCP project are fully isolated by the Terraform `prefix` variable. Here is the complete isolation matrix:

| Resource Type | Dev | Stage | Prod |
|---------------|-----|-------|------|
| **Terraform state** | `pr-agent-dash/dev/state/` | `pr-agent-dash/stage/state/` | `pr-agent-dash/prod/state/` |
| **VPC** | `pr-agent-dash-dev-vpc` | `pr-agent-dash-stage-vpc` | `pr-agent-dash-vpc` |
| **VPC connector** | `pr-agent-dash-dev-connector` | `pr-agent-dash-stage-connector` | `pr-agent-dash-connector` |
| **Cloud SQL** | `pr-agent-dash-dev-sql` | `pr-agent-dash-stage-sql` | `pr-agent-dash-sql` |
| **Secret: DB URL** | `pr-agent-dash-dev-database-url` | `pr-agent-dash-stage-database-url` | `pr-agent-dash-database-url` |
| **Secret: Cron** | `pr-agent-dash-dev-cron-secret` | `pr-agent-dash-stage-cron-secret` | `pr-agent-dash-cron-secret` |
| **Secret: API key** | `pr-agent-dash-dev-api-key` | `pr-agent-dash-stage-api-key` | `pr-agent-dash-api-key` |
| **Artifact Registry** | `pr-agent-dash-dev-repo` | `pr-agent-dash-stage-repo` | `pr-agent-dash-repo` |
| **GCS config** | `{project}-pr-agent-dash-dev-config` | `{project}-pr-agent-dash-stage-config` | `{project}-pr-agent-dash-config` |
| **Cloud Run backend** | `pr-agent-dash-dev-backend` | `pr-agent-dash-stage-backend` | `pr-agent-dash-backend` |
| **Cloud Run frontend** | `pr-agent-dash-dev-frontend` | `pr-agent-dash-stage-frontend` | `pr-agent-dash-frontend` |
| **Cloud Scheduler** | `pr-agent-dash-dev-run-job-timeout` | `pr-agent-dash-stage-run-job-timeout` | `pr-agent-dash-run-job-timeout` |
| **Cloud Build trigger** | `pr-agent-dash-dev-deploy` | `pr-agent-dash-stage-deploy` | `pr-agent-dash-deploy` |
| **Runner VM prefix** | `pr-agent-dash-dev-runner` | `pr-agent-dash-stage-runner` | `pr-agent-dash-runner` |

### Shared resources (project-level)

The following are shared across all environments because they are project-level and idempotent:

- **Enabled GCP APIs**: Enabling the same API multiple times is a no-op.
- **Terraform state bucket**: `{project}-tfstate` (each env uses a separate prefix within it).
- **Cloud Build SA IAM roles**: Project-level bindings; applied once, cover all environments.

## Self-Hosted Runner VMs

The dashboard can provision **on-demand self-hosted runner VMs** for GitHub Actions or Azure DevOps pipelines. These VMs run inside the environment's VPC and have access to the GCS config bucket.

### How it works

1. A user clicks **"Provision runner VM"** in the dashboard UI for a repository connection.
2. The backend calls the **GCP Compute API** to create a VM in the configured zone.
3. The VM's **startup script** (generated at creation time) installs Docker, authenticates with Artifact Registry, and configures the runner agent (GitHub Actions or Azure DevOps).
4. The runner pulls the **PR-Agent Docker image** from Artifact Registry and the **config files** from GCS.
5. When analysis is complete, the VM can be deprovisioned from the dashboard.

### Environment-specific runner configuration

The Cloud Run backend receives these environment variables from Terraform, ensuring runners are scoped to their environment:

| Variable | Value | Purpose |
|----------|-------|---------|
| `GCP_RUNNER_PROJECT_ID` | `{project_id}` | Which GCP project to create VMs in |
| `GCP_RUNNER_REGION` | `{region}` | Region for the VM |
| `GCP_RUNNER_ZONE` | `{region}-a` (default) | Zone for the VM |
| `GCP_RUNNER_MACHINE_TYPE` | `e2-medium` (default) | VM size |
| `GCP_RUNNER_PREFIX` | `{prefix}-runner` | VM name prefix (ensures no collisions across envs) |
| `GCP_RUNNER_PR_AGENT_IMAGE` | (optional) | Pre-pull this Docker image on the VM |

### IAM for runner VMs

Terraform grants the Cloud Run default service account:

- `roles/compute.instanceAdmin.v1` -- create and delete VMs
- `roles/artifactregistry.reader` on the environment's registry -- so runner VMs can pull images

Runner VMs use the default Compute Engine service account with `cloud-platform` scope, giving them access to GCS (for config) and Artifact Registry (for images).

## Scripts Reference

### `scripts/setup-cicd-gcp.sh` / `setup-cicd-gcp.ps1`

Full infrastructure provisioning and CI/CD trigger setup.

| Flag | PowerShell | Description |
|------|------------|-------------|
| `--env <dev\|stage\|prod\|all>` | `-Env` | Target environment(s) |
| `--project <id>` | `-Project` | GCP project ID |
| `--region <region>` | `-Region` | GCP region (default: `us-central1`) |
| `--auto-approve` | `-AutoApprove` | Skip Terraform confirmation prompts |
| `--skip-deploy` | `-SkipDeploy` | Infra + trigger only; no Docker build |

### `scripts/redeploy-gcp.sh` / `redeploy-gcp.ps1`

Rebuild and redeploy all images (backend, frontend, optionally PR-Agent) without re-provisioning infrastructure.

| Variable | Description |
|----------|-------------|
| `PROJECT_ID` | GCP project (auto-detected from tfvars if not set) |
| `REGION` | GCP region (default: `us-central1`) |
| `IMAGE_TAG` | Docker tag (default: `deploy-{timestamp}`) |
| `SKIP_PR_AGENT_IMAGE` | Set to `1` to skip building the PR-Agent image |

### `scripts/teardown-gcp.sh` / `teardown-gcp.ps1`

Destroy all Terraform-managed resources. Prompts for confirmation unless `-auto-approve` is passed.

### `scripts/build-push-gcp.sh` / `build-push-gcp.ps1`

Build and push Docker images to Artifact Registry without deploying.

## Terraform Variables

Key variables in `terraform/gcp/variables.tf`:

| Variable | Default | Description |
|----------|---------|-------------|
| `project_id` | (required) | GCP project ID |
| `region` | `us-central1` | GCP region |
| `prefix` | `pr-agent-dash` | Resource name prefix |
| `db_tier` | `db-f1-micro` | Cloud SQL machine type |
| `backend_image` | `""` | Backend Docker image URL |
| `frontend_image` | `""` | Frontend Docker image URL |
| `backend_max_instances` | `1` | Max Cloud Run instances (1 for WebSocket broadcast) |
| `backend_timeout_seconds` | `3600` | Request timeout (3600 for WebSocket) |
| `allow_unauthenticated` | `true` | Public access to Cloud Run |
| `enable_runner_vm` | `false` | Create a static runner VM via Terraform |
| `runner_machine_type` | `e2-medium` | Runner VM size |
| `config_bucket_name` | `""` | Custom GCS bucket name (auto-generated if empty) |
| `db_user_password` | `""` | Custom DB password (auto-generated if empty) |
| `cron_secret` | `""` | Custom cron secret (auto-generated if empty) |
| `dashboard_api_key` | `""` | Custom API key (auto-generated if empty) |

## Cloud Build Configuration

The file `cloudbuild-deploy.yaml` in the repository root defines the CI/CD build steps. It receives three substitution variables from the trigger:

| Substitution | Example | Purpose |
|--------------|---------|---------|
| `_REGION` | `us-central1` | Registry and Cloud Run region |
| `_REPO_ID` | `pr-agent-dash-dev-repo` | Artifact Registry repository ID |
| `_PREFIX` | `pr-agent-dash-dev` | Cloud Run service name prefix |

These are set automatically by the setup script when creating the trigger. You should not need to modify `cloudbuild-deploy.yaml` unless you want to change the build pipeline itself.

### Build log settings

The Cloud Build config uses `logging: CLOUD_LOGGING_ONLY` to store logs in Cloud Logging instead of a separate GCS bucket, reducing storage costs.

## Day-2 Operations

### Deploying code changes

After initial setup, just push to the appropriate branch:

```bash
git push origin develop    # triggers dev deployment
git push origin staging    # triggers stage deployment
git push origin main       # triggers prod deployment
```

### Infrastructure changes

For database tier changes, new secrets, VPC modifications, etc.:

```bash
cd terraform/gcp
terraform plan    # review changes
terraform apply   # apply changes
```

The setup script generates `backend.tf` and `terraform.tfvars` for you. If switching environments, re-run the script or manually update these files.

### Manual redeploy (without pushing to Git)

```bash
./scripts/redeploy-gcp.sh
# or
.\scripts\redeploy-gcp.ps1
```

This rebuilds all images with a unique timestamp tag and updates Cloud Run.

### Tearing down an environment

```bash
./scripts/teardown-gcp.sh              # interactive
./scripts/teardown-gcp.sh -auto-approve # non-interactive
```

This runs `terraform destroy` to remove all resources. The Terraform state bucket and enabled APIs are preserved.

### Updating PR-Agent for runner VMs

Runner VMs pull the PR-Agent Docker image specified in `GCP_RUNNER_PR_AGENT_IMAGE`. To update:

1. Build and push a new PR-Agent image to Artifact Registry.
2. Update `pr_agent_runner_image` in `terraform.tfvars`.
3. Run `terraform apply` to update the Cloud Run backend's config.
4. Newly provisioned VMs will pull the updated image. Existing VMs need to be reprovisioned from the dashboard.

Alternatively, use `scripts/redeploy-gcp.sh` which handles the PR-Agent image build automatically.

## Troubleshooting

### Setup script fails partway through

The script is idempotent. Fix the underlying issue and re-run it -- completed steps will be skipped.

### GitHub connection stuck at `PENDING_INSTALL_APP`

The script prints the authorization URL. Open it in your browser to authorize the Cloud Build GitHub App. If the 3-minute timeout expires, re-run the script after authorizing.

### Cloud Build trigger not firing

Verify:
- The push was to the correct branch (`develop`, `staging`, or `main`)
- The commit modified files in `dashboard/**`, `terraform/gcp/**`, or `cloudbuild-deploy.yaml`
- The trigger exists: `gcloud builds triggers list --region=REGION`

### Cloud Build fails with permission denied

Ensure the Cloud Build SA has the required roles:

```bash
PROJECT_NUMBER=$(gcloud projects describe PROJECT_ID --format='value(projectNumber)')
gcloud projects get-iam-policy PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"
```

Required roles: `roles/run.admin`, `roles/iam.serviceAccountUser`, `roles/artifactregistry.writer`, `roles/secretmanager.secretAccessor`, `roles/storage.objectViewer`.

### CORS errors after deployment

The setup script runs a two-pass Terraform apply to inject `DASHBOARD_CORS_ORIGINS`. If you see CORS errors:

1. Check the Cloud Run backend's env vars: `gcloud run services describe {prefix}-backend --region=REGION`
2. Ensure `DASHBOARD_CORS_ORIGINS` includes the frontend's URL
3. Re-run: `terraform apply -var="frontend_base_url=https://your-frontend-url.run.app"`

### Frontend shows old version after CI/CD deploy

Cloud Build uses `gcloud run services update --image` which creates a new revision. If the frontend appears unchanged:
- Check the Cloud Build history for errors
- Verify the trigger's substitutions match the correct prefix and repo ID
- Check if the frontend image was actually pushed: `gcloud artifacts docker images list REGION-docker.pkg.dev/PROJECT/REPO`

### Runner VM cannot pull Docker images

Ensure:
- The Artifact Registry IAM binding exists: `roles/artifactregistry.reader` for the compute SA
- The VM has `cloud-platform` scope (set by Terraform)
- `gcloud auth configure-docker` was run on the VM (the startup script handles this)

### Monitoring builds

Console: `https://console.cloud.google.com/cloud-build/builds?project=PROJECT_ID`

CLI:

```bash
gcloud builds list --region=REGION --limit=5
gcloud builds log BUILD_ID --region=REGION
```

# PR-Agent Dashboard on GCP – Terraform

This directory provisions GCP resources for the **PR-Agent Dashboard** (and optionally PR-Agent) as described in the repo root’s **deployment.md** and **docs/GCP_DEPLOYMENT.md**.

## What gets created

- **APIs**: Cloud Run, Cloud SQL Admin, Secret Manager, Cloud Scheduler, Artifact Registry, Storage, Compute, Service Networking, Serverless VPC Access, Storage
- **GCS config bucket**: Bucket for shared PR-Agent config; seed files `configuration.toml` and `secrets.toml` uploaded; dashboard backend gets `PR_AGENT_CONFIG_GCS_BUCKET` and `PR_AGENT_CONFIG_GCS_PREFIX` so dashboard and PR-Agent share the same config (edit in dashboard, next PR-Agent run uses it)
- **VPC**: Custom network with **explicit subnets** (connector subnet for Serverless VPC Access; optional runner subnet when `enable_runner_vm = true`), Private Service Access (peering) for Cloud SQL, Serverless VPC Access connector
- **Cloud SQL**: PostgreSQL 15 instance with **private IP only** (no public IP), database, user; password and `DATABASE_URL` in Secret Manager
- **Secret Manager**: `DATABASE_URL`, `DASHBOARD_CRON_SECRET`, `DASHBOARD_API_KEY` (all set or **auto-generated** by Terraform when not provided; dashboard API key is printed by deploy script for use in PR-Agent)
- **Artifact Registry**: Docker repository for dashboard and PR-Agent images
- **Cloud Run**: Dashboard backend (with VPC connector for private Cloud SQL) and frontend (only when `backend_image` / `frontend_image` are set)
- **Cloud Scheduler**: HTTP job that calls `/api/cron/run-job-timeout` with `X-Cron-Secret`
- **Runner VMs**: **On-demand (recommended)**: Backend receives `GCP_RUNNER_PROJECT_ID`, `GCP_RUNNER_REGION`, `GCP_RUNNER_ZONE` from Terraform and has IAM to create/delete instances. In the dashboard, when adding a repo with a self-hosted runner connection, use **Provision runner VM** to create a GCE VM per connection; startup installs Docker and PR-Agent clone; install the ADO/GitHub agent on the VM via the shown SSH command and provider docs. **Legacy**: Set `enable_runner_vm = true` in tfvars to create a single runner VM via Terraform (same VPC; install agent and pipeline vars manually). See **docs/RUNNER_VM_AND_PR_AGENT_FLOW.md** for how the VM runs PR-Agent (Docker vs Python-from-clone).

## Prerequisites

- [Terraform](https://www.terraform.io/downloads) >= 1.0
- [gcloud](https://cloud.google.com/sdk/docs/install) authenticated with a project that has billing enabled
- Docker (for building and pushing images)

**Running from Windows:** Use the **PowerShell scripts** (`.ps1`) natively: `scripts\deploy-gcp.ps1`, `scripts\build-push-gcp.ps1`, and `terraform\gcp\validate.ps1`. Optionally, **WSL** (with a distro that includes `bash`, e.g. Ubuntu) lets you run the `.sh` scripts from Windows (e.g. `wsl bash scripts/deploy-gcp.sh`). Docker Desktop on Windows is sufficient for building images.

## Remote state (recommended for production)

To use GCS for Terraform state (shared/team use):

1. Create a bucket: `gsutil mb -p YOUR_PROJECT_ID -l us-central1 gs://YOUR_PROJECT_ID-tfstate` and enable versioning: `gsutil versioning set on gs://YOUR_PROJECT_ID-tfstate`
2. Copy `backend.tf.example` to `backend.tf` and set `bucket` (and optional `prefix`).
3. Run `terraform init -reconfigure` (or `terraform init -migrate-state` to move existing local state into GCS).

## Deployment order (what runs when)

After a full run, everything is wired as follows:

1. **Virtual network** – VPC with connector subnet (and optional runner subnet when `enable_runner_vm = true`; prefer on-demand runner VMs from the dashboard).
2. **DB** – Cloud SQL (PostgreSQL) with private IP; `DATABASE_URL` in Secret Manager; backend uses it via Cloud SQL socket.
3. **GCS** – Config bucket created and seeded; backend gets `PR_AGENT_CONFIG_GCS_BUCKET` and `PR_AGENT_CONFIG_GCS_PREFIX`.
4. **Dashboard** – Backend and frontend on Cloud Run (when images are set); second apply injects `backend_base_url` / `frontend_base_url` for CORS and links.
5. **Runner VM** (optional) – Same VPC; startup script installs PR-Agent and writes env file; you install ADO/GitHub agent and set pipeline vars (`DASHBOARD_URL`, `OPENAI_KEY`, GCS vars).
6. **Env wiring** – Backend: `DATABASE_URL`, GCS, cron secret from Secret Manager. PR-Agent (pipeline/VM): set `DASHBOARD_URL` and `PR_AGENT_CONFIG_GCS_*` (and `OPENAI_KEY` in pipeline) so runs report to the dashboard and use shared config.

## Quick start

**One-shot from repo root (recommended for first deploy):** set `project_id` in `terraform.tfvars` (or `PROJECT_ID` env), then run:

```bash
./scripts/full-deploy-gcp.sh -auto-approve
```

This does: init → apply (infra) → build+push backend → deploy backend → build+push frontend → deploy frontend → optional health wait, and prints API key and URLs. See **docs/CI_CD_DEPLOYMENT.md** for details and CI/CD options.

**Manual steps (alternative):**

1. **Copy and edit variables**

   ```bash
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars: set project_id (and optionally region, prefix)
   ```

2. **Provision infra (no Cloud Run yet)**

   ```bash
   terraform init
   terraform plan
   terraform apply
   ```

   This creates VPC, private Cloud SQL, Secret Manager, Artifact Registry, and enables APIs. Cloud Run and Scheduler are skipped until `backend_image` and `frontend_image` are set.

3. **Build and push images**

   From the **repository root** (see deployment.md):

   - Configure Docker for Artifact Registry:
     ```bash
     gcloud auth configure-docker REGION-docker.pkg.dev
     ```
   - Backend:
     ```bash
     docker build -f dashboard/backend/Dockerfile -t REGION-docker.pkg.dev/PROJECT_ID/REPO_ID/backend:latest .
     docker push REGION-docker.pkg.dev/PROJECT_ID/REPO_ID/backend:latest
     ```
   - Frontend (use the **backend** URL for API/WS; you can use a placeholder for first build, then rebuild after backend is deployed):
     ```bash
     docker build -f dashboard/frontend/Dockerfile \
       --build-arg REACT_APP_API_URL=https://YOUR-BACKEND-URL.run.app \
       --build-arg REACT_APP_WS_URL=wss://YOUR-BACKEND-URL.run.app/ws \
       -t REGION-docker.pkg.dev/PROJECT_ID/REPO_ID/frontend:latest .
     docker push REGION-docker.pkg.dev/PROJECT_ID/REPO_ID/frontend:latest
     ```

   Or use the script from the repo root: `scripts/build-push-gcp.ps1` (Windows) / `scripts/build-push-gcp.sh` (Bash) after setting the same variables.

4. **Set image variables and deploy Cloud Run**

   In `terraform.tfvars` set (use the Artifact Registry output from step 2):

   ```hcl
   backend_image  = "us-central1-docker.pkg.dev/YOUR_PROJECT/pr-agent-dash-repo/backend:latest"
   frontend_image  = "us-central1-docker.pkg.dev/YOUR_PROJECT/pr-agent-dash-repo/frontend:latest"
   ```

   Then run **one** of:

   - **Deploy script (recommended)** – applies once, then re-applies with backend/frontend URLs from outputs so CORS and base URLs are set automatically:
     ```bash
     # From repo root
     ./scripts/deploy-gcp.ps1          # Windows
     ./scripts/deploy-gcp.sh           # Linux/macOS
     ./scripts/deploy-gcp.ps1 -AutoApprove
     ```
   - **Manual**: `terraform apply`, then set `backend_base_url` and `frontend_base_url` in `terraform.tfvars` from `terraform output backend_url` / `frontend_url`, then `terraform apply` again.

## Variables

| Variable | Description | Default |
|----------|-------------|--------|
| `project_id` | GCP project ID | (required) |
| `region` | GCP region | `us-central1` |
| `prefix` | Prefix for resource names | `pr-agent-dash` |
| `db_tier` | Cloud SQL tier | `db-f1-micro` |
| `db_name` | Database name | `dashboard_db` |
| `db_user_name` | DB user name | `dashboard_user` |
| `db_user_password` | DB password (empty = generate) | `""` |
| `backend_image` | Backend container image URL | `""` (skip Cloud Run if empty) |
| `frontend_image` | Frontend container image URL | `""` |
| `cron_secret` | DASHBOARD_CRON_SECRET (empty = generate) | `""` |
| `dashboard_api_key` | DASHBOARD_API_KEY for PR-Agent Bearer auth (leave empty to **auto-generate**; deploy script prints it) | `""` |
| `backend_max_instances` | Backend max instances (1 for WebSocket) | `1` |
| `backend_timeout_seconds` | Backend request timeout | `3600` |
| `job_timeout_schedule` | Cron schedule for job timeout | `*/10 * * * *` |
| `allow_unauthenticated` | Allow unauthenticated Cloud Run | `true` |
| `vpc_connector_cidr` | CIDR for VPC connector (/28) | `10.8.0.0/28` |
| `vpc_peering_cidr_prefix` | Prefix length for Private Service Access | `16` |
| `backend_base_url` | Backend URL (deploy script sets from output) | `""` |
| `frontend_base_url` | Frontend URL (deploy script sets from output) | `""` |
| `enable_runner_vm` | Create optional self-hosted runner VM (same VPC; install ADO/GitHub agent after) | `false` |
| `runner_machine_type` | Runner VM machine type | `e2-medium` |
| `runner_zone` | Runner VM zone (default: region + `-a`) | `""` |
| `runner_subnet_cidr` | CIDR for runner subnet (do not overlap connector/peering) | `10.0.1.0/24` |
| `pr_agent_repo_url` | Git URL to clone PR-Agent on runner VM | `https://github.com/Codium-ai/pr-agent.git` |

## Outputs

- `backend_url` – Dashboard backend URL (for frontend build and for PR-Agent `DASHBOARD_URL`)
- `frontend_url` – Dashboard frontend URL
- `cloud_sql_connection_name` – For reference
- `artifact_registry_repository` – Full repo path for `docker push`
- `cron_secret_for_scheduler` – Generated cron secret (sensitive)
- `config_bucket` / `config_prefix` – GCS config; set `PR_AGENT_CONFIG_GCS_BUCKET` and `PR_AGENT_CONFIG_GCS_PREFIX` on PR-Agent (pipeline or VM)
- `dashboard_api_key` – Auto-generated DASHBOARD_API_KEY (sensitive); set as env in PR-Agent so it can post jobs/logs
- `runner_instance_name`, `runner_zone`, `runner_env_path` – When `enable_runner_vm = true`; env file at `runner_env_path` has DASHBOARD_URL and GCS vars

## Optional: PR-Agent on Cloud Run

To add the PR-Agent GitHub App or ADO webhook server, build and push those images (see deployment.md), then add new Terraform `google_cloud_run_v2_service` resources and point them at the same Artifact Registry repo or a separate one. This Terraform module focuses on the dashboard only.

## Testing (no GCP required)

From this directory or from repo root:

```powershell
# Windows (recommended)
.\terraform\gcp\validate.ps1
```

```bash
# Linux/macOS or WSL (with bash)
./terraform/gcp/validate.sh
```

This runs `terraform init -backend=false`, `terraform validate` (with a dummy `project_id`), and `terraform fmt -check`. From repo root you can also run `pytest scripts/tests/test_gcp_scripts.py -v` (on Windows, PowerShell script tests always run; bash tests run via WSL when available and skip if bash is not in WSL).

## Cleanup (teardown – clean slate)

To remove **all** resources created by this deployment and leave the project clean (so you can deploy again):

**From repo root (recommended):**

```powershell
# Windows – prompts for confirmation
.\scripts\teardown-gcp.ps1

# No prompt (e.g. CI)
.\scripts\teardown-gcp.ps1 -Force
```

```bash
# Linux/macOS – prompts for confirmation
./scripts/teardown-gcp.sh

# No prompt
./scripts/teardown-gcp.sh -auto-approve
```

**Or from this directory:**

```bash
terraform init
terraform destroy    # add -auto-approve to skip confirmation
```

**What gets destroyed:** VPC (network, subnets, connector, peering), Cloud SQL instance and DB, Secret Manager secrets, GCS config bucket and objects, Artifact Registry repo, Cloud Run backend and frontend, Cloud Scheduler job, runner VM (if created). Enabled APIs remain enabled (no cost by themselves).

**Note:** Cloud SQL has `deletion_protection = false` by default so it can be destroyed. Set it to `true` in `main.tf` for production. The config GCS bucket has `force_destroy = true` so the bucket and its contents are removed on destroy.

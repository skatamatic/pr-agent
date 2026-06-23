# Terraform and deploy scripts

## Infrastructure as code

Primary Terraform lives in `terraform/gcp/`:

- `main.tf`: VPC, Cloud SQL, GCS, Cloud Run, Scheduler, optional legacy runner VM
- `variables.tf`: prefix (default `pr-agent-dash`), region, runner/ADO settings
- `outputs.tf`: URLs, secrets, bucket, registry, runner paths
- `terraform/gcp/runner-startup.sh.tpl`: legacy Terraform VM bootstrap (keep in sync with `dashboard/backend/services/gcp_runner_service.py`)
- `config-seed/`: initial config uploaded to GCS on first deploy

### Terraform outputs (use these post-deploy)

| Output | Maps to |
|--------|---------|
| `backend_url` | `DASHBOARD_URL`, `REACT_APP_API_URL`, `DASHBOARD_BACKEND_BASE_URL` |
| `frontend_url` | User URL, `DASHBOARD_CORS_ORIGINS`, `DASHBOARD_FRONTEND_BASE_URL` |
| `dashboard_api_key` (sensitive) | `DASHBOARD_API_KEY` in pipeline + runner env |
| `config_bucket` | `PR_AGENT_CONFIG_GCS_BUCKET` (bucket name: `{project}-{prefix}-config`) |
| `config_prefix` | `PR_AGENT_CONFIG_GCS_PREFIX` (default `pr-agent-config/`) |
| `artifact_registry_repository` | Image push target |
| `cron_secret_for_scheduler` (sensitive) | Cloud Scheduler auth header |
| `pr_agent_runner_image` | Pre-built image URL for redeploy without rebuild |
| `runner_env_path` | `/opt/pr-agent-runner/env` on provisioned VMs |

GCS **prefix** (`pr-agent-config/`) is not the bucket name. Objects look like `gs://my-project-pr-agent-dash-config/pr-agent-config/configuration.toml`.

## Deploy scripts: choose the right one

| Script | When to use | What it does |
|--------|-------------|--------------|
| **`scripts/full-deploy-gcp.sh`** | **First-time deploy (Linux/WSL/macOS)** | `terraform init` + apply → build PR-Agent image → build backend → build frontend → second apply for CORS/URLs → health wait |
| **`scripts/full-deploy-gcp.ps1`** | **Images only on Windows** | Builds/pushes images + updates Cloud Run: **requires Terraform already applied** |
| **`scripts/redeploy-gcp.sh`** | After code changes | Rebuild all images; `SKIP_PR_AGENT_IMAGE=1` to skip PR-Agent rebuild |
| **`scripts/setup-cicd-gcp.sh`** | Enable Cloud Build triggers | Branches: `develop`, `staging`, `main` |

## Container images

| Image | Build source | Notes |
|-------|--------------|-------|
| Dashboard backend | `dashboard/backend/Dockerfile` | Includes `pr_agent/` package |
| Dashboard frontend | `dashboard/frontend/Dockerfile` | Bakes `REACT_APP_API_URL`, `REACT_APP_WS_URL` at build time |
| PR-Agent runner | **`Dockerfile.github_action`** (manual deploy scripts) | Legacy filename; image runs `azuredevops_pipeline_runner` |
| PR-Agent runner | **`docker/Dockerfile.github_action_runner`** (Cloud Build) | Used by `cloudbuild-pr-agent.yaml` |

ADO pipeline overrides entrypoint to run `python3 -m pr_agent.servers.azuredevops_pipeline_runner`.

### Cloud Build files

| File | Builds | Deploys |
|------|--------|---------|
| `cloudbuild.yaml` | Dashboard FE/BE | No |
| `cloudbuild-deploy.yaml` | Dashboard FE/BE | Yes: `gcloud run services update` + CORS |
| `cloudbuild-pr-agent.yaml` | PR-Agent image | Updates backend env `GCP_RUNNER_PR_AGENT_IMAGE` |

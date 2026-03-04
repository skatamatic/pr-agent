# Self-Hosted Runner VM and PR-Agent Execution Flow

This document describes how the dashboard-provisioned GCP runner VM fits together with PR-Agent so that workflow/pipeline jobs are serviced reliably.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Dashboard (Cloud Run or on-prem)                                                 │
│  - User clicks "Provision runner VM" for an action runner connection              │
│  - Backend calls GCP Compute API → creates GCE VM with startup script             │
└───────────────────────────────────────────┬─────────────────────────────────────┘
                                             │
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  GCE Runner VM (Ubuntu 22.04)                                                     │
│  1. Startup script runs once at first boot:                                      │
│     - Installs Docker CE, Python 3, git                                          │
│     - Clones PR-Agent to /opt/pr-agent, pip installs requirements                 │
│     - Writes /opt/pr-agent-runner/env (DASHBOARD_URL, GCS config)                 │
│     - Optionally pre-pulls PR-Agent Docker image                                  │
│  2. User SSHs in and installs GitHub Actions runner or Azure DevOps agent         │
│  3. Runner/agent registers with GitHub or ADO                                     │
└───────────────────────────────────────────┬─────────────────────────────────────┘
                                             │
     When a workflow/pipeline job runs on this runner:
                                             │
     ┌──────────────────────────────────────┴──────────────────────────────────────┐
     │  Option A: Run PR-Agent in Docker (recommended for GitHub Actions)           │
     │  - Workflow step: uses: docker://codiumai/pr-agent:VERSION-github_action      │
     │  - Runner has Docker; pulls/runs container; container runs                    │
     │    pr_agent/servers/github_action_runner.py                                   │
     │  - Pass env: OPENAI_KEY, DASHBOARD_URL, DASHBOARD_API_KEY, GITHUB_TOKEN, etc. │
     └──────────────────────────────────────┬──────────────────────────────────────┘
     ┌──────────────────────────────────────┴──────────────────────────────────────┐
     │  Option B: Run PR-Agent from clone (typical for Azure Pipelines)             │
     │  - Pipeline step: source /opt/pr-agent-runner/env && python3 \                │
     │    /opt/pr-agent/pr_agent/servers/azuredevops_pipeline_runner.py              │
     │  - Same env file provides DASHBOARD_URL, GCS config; pipeline vars provide    │
     │    OPENAI_KEY, DASHBOARD_API_KEY, AZURE_DEVOPS_PAT, etc.                      │
     └──────────────────────────────────────┬──────────────────────────────────────┘
                                             │
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  PR-Agent (inside container or process)                                          │
│  - Reads PR/event context from env (GITHUB_EVENT_PATH, ADO vars, etc.)            │
│  - Calls OpenAI/Anthropic; posts results back to GitHub/ADO                      │
│  - Reports job/operations/logs to Dashboard (DASHBOARD_URL + DASHBOARD_API_KEY)  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Flow in Detail

### 1. Dashboard provisions the VM

- **Who**: User in dashboard, or automation when a repo is connected with a runner connection.
- **What**: Backend uses `GCPRunnerService` (or Terraform) to create a GCE instance with:
  - Image: Ubuntu 22.04 LTS
  - Machine type: e2-medium (configurable)
  - **Startup script** (see below): installs Docker, Python, git, PR-Agent clone, env file.
- **Result**: VM boots; startup script runs once; VM is ready for runner/agent install and then for jobs.

### 2. VM startup script (best practices)

- **Idempotent**: Safe to re-run; checks for existing installs (e.g. `[ -d /opt/pr-agent ]`).
- **Logging**: Writes to stdout/stderr so logs appear in GCP Console (Serial port output / startup script logs).
- **Order**: Install system packages (Docker, Python, git) → create env file → clone PR-Agent → pip install → optional `docker pull` for PR-Agent image.
- **No secrets in script**: DASHBOARD_URL and GCS bucket/prefix are injected by Terraform/dashboard; API keys and tokens are provided at **job** time via pipeline variables or workflow env, not baked into the image.

### 3. User installs the runner/agent

- **GitHub**: Settings → Actions → Runners → New self-hosted runner → copy install commands → SSH to VM → run them.
- **Azure DevOps**: Project settings → Agent pools → Add agent → Linux → copy registration script → SSH to VM → run it.
- Runner/agent runs as a service and waits for jobs.

### 4. How jobs run PR-Agent (two supported modes)

| Mode | When to use | How |
|------|-------------|-----|
| **Docker** | GitHub Actions workflows that use `uses: docker://codiumai/pr-agent:...` | Runner must have Docker (startup script installs it). Workflow passes env (OPENAI_KEY, DASHBOARD_URL, DASHBOARD_API_KEY, GITHUB_TOKEN, etc.). Each job runs a fresh container. |
| **Python from clone** | Azure Pipelines or custom steps that run PR-Agent from the repo | Step sources `/opt/pr-agent-runner/env` then runs `python3 /opt/pr-agent/pr_agent/servers/azuredevops_pipeline_runner.py` (or github_action_runner.py). Pipeline variables supply OPENAI_KEY, DASHBOARD_API_KEY, etc. |

Both modes report to the dashboard when `DASHBOARD_URL` and `DASHBOARD_API_KEY` are set.

### 5. GCS config access (same bucket as dashboard)

The VM’s startup script writes `/opt/pr-agent-runner/env` with `PR_AGENT_CONFIG_GCS_BUCKET` and `PR_AGENT_CONFIG_GCS_PREFIX`. The dashboard and PR-Agent both read config (e.g. `configuration.toml`, `secrets.toml`) from this bucket so behaviour stays in sync.

- **VM identity**: Runner VMs use the project’s default compute service account with `cloud-platform` scope. Terraform grants that account `roles/storage.objectAdmin` on the config bucket when the backend is deployed, so the VM can read/write the same objects the dashboard uses.
- **Python from clone (e.g. Azure Pipelines)**: The pipeline step sources `/opt/pr-agent-runner/env`, so `PR_AGENT_CONFIG_GCS_*` are set and PR-Agent’s config loader uses Application Default Credentials (ADC) on the VM to access GCS.
- **Docker (e.g. GitHub Actions)**: The workflow must pass the same env into the container, e.g. `PR_AGENT_CONFIG_GCS_BUCKET`, `PR_AGENT_CONFIG_GCS_PREFIX`. The container uses ADC; on GCE, that uses the metadata server (`169.254.169.254`). From a container on the VM, the metadata server is usually reachable. If the container cannot access it (e.g. strict network isolation), run the container with `--network=host` so it uses the VM’s network and ADC works, or mount/inject credentials per your security requirements.

Using the image built by `scripts/redeploy-gcp.ps1` / `scripts/redeploy-gcp.sh` (e.g. `REGION-docker.pkg.dev/PROJECT/pr-agent-dash-repo/pr-agent:latest`) ensures the runner runs the same PR-Agent version as the one you deploy; the startup script can pre-pull that image when `GCP_RUNNER_PR_AGENT_IMAGE` is set.

### 6. Reliability and best practices

- **Startup script**: Use `set -e`; retry apt/docker install if needed; log clearly so failures are visible in GCP.
- **Docker**: Install Docker CE from the official repo; add default user to `docker` group if jobs run as non-root.
- **PR-Agent image**: Pin a version tag (e.g. `0.23-github_action`) in workflows instead of `latest`. Optionally pre-pull in startup to avoid first-job latency.
- **Secrets**: Never put OPENAI_KEY or DASHBOARD_API_KEY in the startup script or VM image; use pipeline variables / GitHub secrets and pass them into the container or process.
- **Health**: Dashboard uses existing runner health (GitHub Actions API / ADO pool API) to show runner status; no separate “VM health” is required unless you want to show GCE instance status.

## Files and ownership

- **Startup script (Terraform)**: `terraform/gcp/runner-startup.sh.tpl` — used when `enable_runner_vm = true`.
- **Startup script (Dashboard-provisioned VMs)**: Built in `dashboard/backend/services/gcp_runner_service.py` in `_get_startup_script()`; **must stay in sync** with the Terraform template (same sections: Docker install, env file, PR-Agent clone, optional `pr_agent_image` pre-pull). When you change one, update the other.
- **Runner install instructions**: Shown in dashboard after “Provision runner VM”; link to GitHub/ADO docs and mention both Docker and Python-from-clone, plus passing `PR_AGENT_CONFIG_GCS_*` into Docker so the container loads config from the same GCS bucket as the dashboard.

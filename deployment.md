# PR-Agent & Dashboard: Deployment to Google Cloud

This document describes how to deploy **PR-Agent** and the **PR-Agent Dashboard** on **Google Cloud Platform (GCP)**, including the **Azure DevOps (ADO) compatible self-hosted action runner** that monitors PRs and invokes PR-Agent. It covers services, networks, secrets, config, databases, environment variables, containers, and VMs.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [GCP Services and Resources](#2-gcp-services-and-resources)
3. [Networking](#3-networking)
4. [Secrets and Configuration](#4-secrets-and-configuration)
5. [Database (Cloud SQL)](#5-database-cloud-sql)
6. [Dashboard Deployment](#6-dashboard-deployment)
7. [PR-Agent Deployment Options](#7-pr-agent-deployment-options)
8. [Azure DevOps: Webhook Server vs Self-Hosted Pipeline Runner](#8-azure-devops-webhook-server-vs-self-hosted-pipeline-runner)
9. [ADO Self-Hosted Runner on GCP (VM)](#9-ado-self-hosted-runner-on-gcp-vm)
10. [Scheduled Jobs (Cloud Scheduler)](#10-scheduled-jobs-cloud-scheduler)
11. [Environment Variables Reference](#11-environment-variables-reference)
12. [Deployment Order and Checklist](#12-deployment-order-and-checklist)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              Google Cloud Project                                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌──────────────────┐     ┌──────────────────┐     ┌─────────────────────────┐  │
│  │  Cloud Run       │     │  Cloud Run       │     │  Cloud SQL (PostgreSQL)  │  │
│  │  Dashboard       │────►│  Dashboard       │────►│  - dashboard_db          │  │
│  │  Frontend        │     │  Backend (API)   │     │  - Unix socket / private │  │
│  │  (nginx/static)  │     │  (FastAPI)       │     └─────────────────────────┘  │
│  └────────┬─────────┘     └────────┬─────────┘              ▲                   │
│           │                        │                         │                   │
│           │  REACT_APP_API_URL     │  /api/*, /ws            │ DATABASE_URL      │
│           │  REACT_APP_WS_URL      │  Health: /api/health    │                   │
│           │                        │                         │                   │
│  ┌────────┴─────────┐     ┌───────┴─────────┐     ┌─────────┴───────────────┐   │
│  │  Cloud Run       │     │  Cloud Run      │     │  Secret Manager         │   │
│  │  (optional)      │     │  (optional)     │     │  - DATABASE_URL          │   │
│  │  PR-Agent        │     │  PR-Agent       │     │  - DASHBOARD_CRON_SECRET │   │
│  │  GitHub App      │     │  ADO Webhook    │     │  - OPENAI_KEY, PAT, etc. │   │
│  └──────────────────┘     └────────┬────────┘     └─────────────────────────┘   │
│           │                        │                                               │
│           │  DASHBOARD_URL         │  Service Hooks (HTTPS)                        │
│           │  (report jobs/logs)    │  from Azure DevOps                            │
│           ▼                        ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │  Dashboard Backend (receives: POST /api/jobs/create, /api/operations/...,   │ │
│  │  POST /logs/batch from PR-Agent)                                             │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │  Compute Engine VM (optional): ADO self-hosted agent                         │ │
│  │  - Runs Azure Pipeline when PR is created                                    │ │
│  │  - Pipeline step runs: python -m pr_agent.servers.azuredevops_pipeline_runner │ │
│  │  - PR-Agent uses OPENAI_KEY, AZURE_DEVOPS_PAT, DASHBOARD_URL                 │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                   │
│  ┌──────────────────┐                                                            │
│  │  Cloud Scheduler  │  POST /api/cron/run-job-timeout (with X-Cron-Secret)       │
│  │                  │  POST /api/cron/run-cleanup (SQLite only; optional)         │
│  └──────────────────┘                                                            │
└─────────────────────────────────────────────────────────────────────────────────┘

External:
- Users → Dashboard Frontend (HTTPS)
- GitHub / Azure DevOps → PR-Agent (webhooks or pipeline on self-hosted agent)
- PR-Agent → Dashboard Backend (jobs, operations, logs)
- PR-Agent → OpenAI / Anthropic / other LLM APIs
```

**Data flow (summary)**

- **Dashboard**: Frontend (React) talks to Backend (FastAPI). Backend uses Cloud SQL. PR-Agent **calls into** the dashboard (creates jobs/operations, posts logs); the dashboard does **not** trigger PR-Agent.
- **PR-Agent** is triggered by:
  - **GitHub**: GitHub App (webhook) or GitHub Actions (workflow).
  - **Azure DevOps**: (A) **Webhook server** (Cloud Run) receiving Service Hooks, or (B) **Azure Pipeline** on a **self-hosted agent** (VM or on-prem) that runs `azuredevops_pipeline_runner.py`.

---

## 2. GCP Services and Resources

| Service / Resource | Purpose |
|--------------------|---------|
| **Google Cloud Project** | Container for all resources; enable billing and APIs. |
| **Cloud Run** | Run dashboard frontend, dashboard backend, and (optionally) PR-Agent GitHub App and ADO webhook server. |
| **Cloud SQL for PostgreSQL** | Production database for the dashboard (recommended). SQLite is for local/dev only. |
| **Secret Manager** | Store `DATABASE_URL`, `DASHBOARD_CRON_SECRET`, `OPENAI_KEY`, GitHub/ADO tokens, webhook auth, etc. |
| **Cloud Scheduler** | HTTP jobs that call dashboard cron endpoints (job timeout, optional cleanup). |
| **Artifact Registry** (or Container Registry) | Store Docker images for Cloud Run. |
| **Compute Engine VM** (optional) | Host the **Azure DevOps self-hosted agent** that runs the pipeline which invokes PR-Agent. |
| **VPC** (optional) | Default VPC is enough for Cloud Run + Cloud SQL. Use custom VPC if you need private IP or stricter network isolation. |

**APIs to enable**

- Cloud Run API  
- Cloud SQL Admin API  
- Secret Manager API  
- Cloud Scheduler API  
- Artifact Registry API (or Container Registry API)  
- Compute Engine API (only if using a VM for the self-hosted agent)

---

## 3. Networking

- **Cloud Run**: Services get a default public URL. No custom VPC required unless you want the backend to use a VPC connector (e.g. to reach private resources).
- **Cloud SQL**: Use the **Cloud SQL Auth Proxy** or **private IP**. For Cloud Run, the standard approach is **Unix socket connection** with the instance attached to the Cloud Run service (connection name `PROJECT_ID:REGION:INSTANCE_NAME`).
- **Firewall**: Cloud Run and Cloud SQL are managed; ensure the VM (if used) has:
  - Outbound HTTPS (443) for Azure DevOps, GitHub, OpenAI, and the dashboard backend URL.
  - Inbound only as required for ADO agent communication (ADO initiates to the agent).

No separate “virtual network” section is required for a minimal deployment; the sections below assume the default Cloud Run + Cloud SQL attachment.

---

## 4. Secrets and Configuration

### 4.1 What to put in Secret Manager

Store these as secrets (do not put them in env as plain text in YAML or config):

| Secret name (example) | Used by | Description |
|-----------------------|---------|-------------|
| `DATABASE_URL` | Dashboard backend | Full PostgreSQL URL including password. For Cloud Run: `postgresql://USER:PASSWORD@/DB?host=/cloudsql/PROJECT:REGION:INSTANCE`. |
| `DASHBOARD_CRON_SECRET` | Dashboard backend | Random string for `X-Cron-Secret` / `Authorization: Bearer` for cron endpoints. |
| `OPENAI_KEY` | PR-Agent (all modes) | OpenAI API key. |
| `DASHBOARD_API_KEY` | PR-Agent (optional) | If you enable API key auth for dashboard callbacks. |
| GitHub token or App private key | PR-Agent GitHub App | Per GitHub App setup. |
| `AZURE_DEVOPS_PAT` | PR-Agent (ADO) | Azure DevOps PAT for API access (or use `SYSTEM_ACCESSTOKEN` in pipeline). |
| ADO webhook Basic auth | PR-Agent ADO webhook | `webhook_username` / `webhook_password` for Service Hooks (store as two secrets or one JSON). |

Create secrets:

```bash
# Example: store database URL (replace with your values)
echo -n "postgresql://dashboard_user:SECRET@/dashboard_db?host=/cloudsql/my-project:us-central1:my-instance" | \
  gcloud secrets create DATABASE_URL --data-file=-

# Cron secret
echo -n "$(openssl rand -hex 32)" | gcloud secrets create DASHBOARD_CRON_SECRET --data-file=-
```

In Cloud Run, reference secrets as environment variables or volume mounts (see [Cloud Run docs](https://cloud.google.com/run/docs/configuring/services/secrets)).

### 4.2 Config files (not in Secret Manager)

- **Dashboard**: `dashboard/backend/config.py` reads from `settings.toml` and env (prefix `DASHBOARD_`). For GCP, you can rely on env vars and omit most of `settings.toml` in the image.
- **PR-Agent**: `pr_agent/settings/configuration.toml` and `pr_agent/settings/secrets.toml` (or `.secrets.toml`). In containers, you can mount a volume or bake a minimal config and inject secrets via env (e.g. `DASHBOARD_URL`, `OPENAI_KEY`).

**Shared config (dashboard + PR-Agent):** Either (1) **GCS:** set **`PR_AGENT_CONFIG_GCS_BUCKET`** (and optionally **`PR_AGENT_CONFIG_GCS_PREFIX`**) on both dashboard and PR-Agent so they use the same bucket—dashboard writes here, PR-Agent downloads at startup. **Terraform** (`terraform/gcp`) creates the bucket, seeds initial config, and sets these env vars on the dashboard backend automatically. Or (2) **Local:** set **`PR_AGENT_CONFIG_PATH`** to a directory containing the config files and use the same path for both. See `docs/CONFIG_STORAGE_DESIGN.md`.

---

## 5. Database (Cloud SQL)

1. **Create instance**: Cloud SQL for PostgreSQL (e.g. via Console or `gcloud sql instances create`).
2. **Create database and user**:
   ```bash
   gcloud sql databases create dashboard_db --instance=INSTANCE_NAME
   gcloud sql users create dashboard_user --instance=INSTANCE_NAME --password=...
   ```
3. **Connection name**: `PROJECT_ID:REGION:INSTANCE_NAME`. Use it when attaching the instance to Cloud Run and in `DATABASE_URL`.
4. **Connection string for Cloud Run** (Unix socket):
   ```
   postgresql://dashboard_user:PASSWORD@/dashboard_db?host=/cloudsql/PROJECT_ID:REGION:INSTANCE_NAME
   ```
   Store this in Secret Manager as `DATABASE_URL`.
5. **Migrations**: The dashboard backend runs `migrate_database()` on startup and creates/updates tables. Ensure the DB user has permission to create tables (or run migrations separately once).

**Backup**: Use Cloud SQL automated backups and point-in-time recovery. The in-app file backup/restore in the dashboard is for SQLite only; it is disabled when using PostgreSQL.

---

## 6. Dashboard Deployment

### 6.1 Backend (Cloud Run)

- **Image**: Build from repo root:
  ```bash
  docker build -f dashboard/backend/Dockerfile -t gcr.io/PROJECT_ID/pr-agent-dashboard-backend .
  docker push gcr.io/PROJECT_ID/pr-agent-dashboard-backend
  ```
- **Run**: Cloud Run service that:
  - Uses the **Cloud SQL connection** (add the instance connection name in the Cloud Run service).
  - Sets **PORT** (Cloud Run sets this automatically).
  - Gets **DATABASE_URL** from Secret Manager.
  - Sets **DASHBOARD_BACKEND_BASE_URL** and **DASHBOARD_FRONTEND_BASE_URL** to your deployed URLs.
  - Sets **DASHBOARD_CORS_ORIGINS** to the frontend origin (e.g. `https://dashboard-xxx.run.app`).
  - Optionally sets **DASHBOARD_CRON_SECRET** from Secret Manager.
  - Sets **DASHBOARD_DEVELOPER_MODE=false** in production.
- **Health**: Use `GET /api/health` for liveness/readiness.
- **WebSockets**: Use request timeout **60 minutes** (3600s). Prefer **max instances = 1** so all clients share the same in-memory broadcast. Do not enable HTTP/2 end-to-end for the service.

### 6.2 Frontend (Cloud Run)

- **Image**: Build with API and WebSocket URLs set at **build time**:
  ```bash
  docker build -f dashboard/frontend/Dockerfile \
    --build-arg REACT_APP_API_URL=https://YOUR-BACKEND-URL.run.app \
    --build-arg REACT_APP_WS_URL=wss://YOUR-BACKEND-URL.run.app/ws \
    -t gcr.io/PROJECT_ID/pr-agent-dashboard-frontend .
  docker push gcr.io/PROJECT_ID/pr-agent-dashboard-frontend
  ```
- **Run**: Deploy the image to Cloud Run. The app serves static files (port 80 in the container). No database or secrets required for the frontend.

### 6.3 Dashboard env summary

See [Section 11](#11-environment-variables-reference) for the full table. Critical for GCP:

- `DATABASE_URL` (from Secret Manager)  
- `DASHBOARD_BACKEND_BASE_URL`, `DASHBOARD_FRONTEND_BASE_URL`  
- `DASHBOARD_CORS_ORIGINS` (frontend origin)  
- `DASHBOARD_CRON_SECRET` (from Secret Manager, for cron)  
- `DASHBOARD_DEVELOPER_MODE=false`  
- `PORT` (set by Cloud Run)

---

## 7. PR-Agent Deployment Options

| Option | Where it runs | Trigger | Use case |
|--------|----------------|---------|----------|
| **GitHub App** | Cloud Run | GitHub webhook | GitHub repos. |
| **ADO Webhook server** | Cloud Run | Azure Service Hooks (Pull request created, etc.) | ADO repos; event-driven. |
| **ADO Pipeline on self-hosted agent** | GCP VM (or on-prem) | Pipeline runs on PR | ADO repos; agent has code and runs PR-Agent. |

PR-Agent **always** reports to the dashboard (if `DASHBOARD_URL` is set) by calling:

- `POST /api/jobs/create`, `POST /api/jobs/{id}/status`  
- `POST /api/operations/create`, `POST /api/operations/{id}/status`, `POST /api/operations/{id}/step`, `POST /api/operations/{id}/ai-metrics`, `PUT /api/operations/{id}/insights`  
- `POST /logs/immediate`, `POST /logs/batch`  

No webhook or trigger from the dashboard to PR-Agent is required.

### 7.1 PR-Agent as GitHub App (Cloud Run)

```bash
docker build -f docker/Dockerfile --target github_app -t gcr.io/PROJECT_ID/pr-agent-github-app .
docker push gcr.io/PROJECT_ID/pr-agent-github-app
```

Configure env (or config): `DASHBOARD_URL`, `DASHBOARD_API_KEY` (optional), and GitHub App credentials (from Secret Manager). Expose the service on HTTPS and set the GitHub App webhook URL to this service.

### 7.2 PR-Agent as ADO Webhook server (Cloud Run)

```bash
docker build -f docker/Dockerfile --target azure_devops_webhook -t gcr.io/PROJECT_ID/pr-agent-ado-webhook .
docker push gcr.io/PROJECT_ID/pr-agent-ado-webhook
```

- Expose via HTTPS. In Azure DevOps: **Project Settings → Service hooks → New subscription → Web Hook**.
- Event: e.g. **Pull request created**. URL: `https://your-ado-webhook.run.app/`.
- If you set `webhook_username` and `webhook_password` in PR-Agent config, use the same as Basic auth in the Service Hook.
- Configure PR-Agent: `azure_devops_server.pr_commands` (e.g. `["/describe", "/review", "/improve"]`), `azure_devops.org`, `azure_devops.pat` (or env), and `DASHBOARD_URL` (and optional `DASHBOARD_API_KEY`).

---

## 8. Azure DevOps: Webhook Server vs Self-Hosted Pipeline Runner

| | ADO Webhook server | ADO Self-hosted pipeline runner |
|--|---------------------|----------------------------------|
| **Runs** | Cloud Run container | Azure DevOps self-hosted agent (VM or on-prem) |
| **Trigger** | Service Hooks → HTTP POST to your endpoint | Pipeline runs when PR triggers the pipeline |
| **PR-Agent code** | Inside the webhook container | Installed on the agent (e.g. `pip install`, run `python -m pr_agent.servers.azuredevops_pipeline_runner`) |
| **Best for** | Fully serverless; no VM | Need agent for other steps, or prefer pipeline YAML control |
| **Secrets** | In Secret Manager / Cloud Run env | Pipeline variables (e.g. `OPENAI_KEY`, `AZURE_DEVOPS_PAT`) and/or VM env |

You can use **both**: webhook for “on PR created” automation and a pipeline on a self-hosted agent for additional control or other pipeline steps.

---

## 9. ADO Self-Hosted Runner on GCP (VM)

This section describes running an **Azure DevOps self-hosted agent** on a **GCP Compute Engine VM** so that a pipeline can run PR-Agent when a PR is created (or on other triggers). The agent does not “monitor” in a polling sense; Azure DevOps pushes jobs to the agent when the pipeline is triggered.

### 9.1 Create the VM

- **Machine type**: e2-medium or larger (PR-Agent and Python deps need some memory).
- **OS**: Windows Server or a Linux distro (e.g. Ubuntu). The repo’s `azure-pipelines-pr-agent.yml` example uses Windows (`agent.os -equals Windows_NT`).
- **Network**: Default or custom VPC; allow outbound HTTPS (443) to Azure DevOps, OpenAI, and the dashboard backend.
- **Disk**: Sufficient for OS + Python + repo clone (e.g. 50 GB).

### 9.2 Install Azure DevOps self-hosted agent

1. In Azure DevOps: **Project settings → Agent pools → Add pool** (or use default). Add an **agent** and follow the “Download the agent” / “Configure the agent” steps for your OS.
2. On the VM, download the agent, extract, run `config.cmd` (Windows) or `./config.sh` (Linux), and enter the Azure DevOps URL and PAT. Install as a Windows service or systemd unit so it runs after reboot.
3. Verify the agent appears in the pool and is “Online”.

### 9.3 Install PR-Agent on the VM

- **Option A – Git clone**: Clone the pr-agent repo on the VM (e.g. `C:\pr_agent\pr-agent`). Install dependencies:
  ```bash
  pip install -r requirements.txt
  ```
- **Option B – Docker**: Run a container that includes PR-Agent and run the pipeline runner inside the container (pipeline would call `docker run ...`); more complex and not covered in detail here.

The pipeline YAML will reference the path to the repo on the agent (e.g. `C:/pr_agent/pr-agent`).

### 9.4 Pipeline YAML (ADO)

Use a pipeline that runs on your self-hosted pool and triggers on PRs. Example (conceptually; see `azure-pipelines-pr-agent.yml` in the repo):

```yaml
trigger: none
pr:
  branches:
    include: ['*']

pool:
  name: 'YOUR_SELF_HOSTED_POOL'
  demands:
    - agent.os -equals Windows_NT   # or Linux

variables:
  - name: PYTHONUTF8
    value: 1

stages:
  - stage: pr_agent
    jobs:
      - job: run_agent
        steps:
          - checkout: self
            persistCredentials: true

          - script: |
              pip install -r "C:/pr_agent/pr-agent/requirements.txt"
              python -m pr_agent.servers.azuredevops_pipeline_runner
            displayName: 'Run PR-Agent'
            env:
              BUILD_REASON: $(Build.Reason)
              SYSTEM_PULLREQUEST_PULLREQUESTID: $(System.PullRequest.PullRequestId)
              SYSTEM_TEAMPROJECT: $(System.TeamProject)
              BUILD_REPOSITORY_NAME: $(Build.Repository.Name)
              SYSTEM_COLLECTIONURI: $(System.CollectionUri)
              AZURE_DEVOPS_PAT: $(System.AccessToken)
              SYSTEM_ACCESSTOKEN: $(System.AccessToken)
              OPENAI_KEY: $(OPENAI_KEY)
              DASHBOARD_URL: $(DASHBOARD_URL)
              # Optional: DASHBOARD_API_KEY
```

- **Pipeline variables / variable group**: Define `OPENAI_KEY`, `DASHBOARD_URL` (your dashboard backend URL), and optionally `DASHBOARD_API_KEY` as secret or non-secret variables and grant the pipeline access.
- The runner reads `BUILD_REASON`, `SYSTEM_PULLREQUEST_*`, etc.; when `BUILD_REASON=PullRequest` it runs PR-Agent and reports to the dashboard.

### 9.5 Env vars on the self-hosted agent (summary)

| Variable | Source | Purpose |
|----------|--------|---------|
| `BUILD_REASON`, `SYSTEM_PULLREQUEST_PULLREQUESTID`, `SYSTEM_TEAMPROJECT`, `BUILD_REPOSITORY_NAME`, `SYSTEM_COLLECTIONURI` | Azure DevOps (pipeline env) | Identify the PR. |
| `AZURE_DEVOPS_PAT` or `SYSTEM_ACCESSTOKEN` | Pipeline (e.g. `$(System.AccessToken)`) | ADO API access. |
| `OPENAI_KEY` | Pipeline variable (secret) | LLM API. |
| `DASHBOARD_URL` | Pipeline variable | Dashboard backend base URL for jobs/logs. |
| `DASHBOARD_API_KEY` | Pipeline variable (optional) | If dashboard requires it. |

No Cloud Run or Secret Manager on the VM; secrets are in Azure DevOps variable groups or pipeline secrets.

---

## 10. Scheduled Jobs (Cloud Scheduler)

The dashboard exposes cron endpoints that **must** be called with a secret header when `DASHBOARD_CRON_SECRET` is set:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/cron/run-job-timeout` | POST | Mark stale running jobs as failed. |
| `/api/cron/run-cleanup` | POST | Retention cleanup (**SQLite only**; returns “skipped” for Cloud SQL). |

**Auth**: Header `X-Cron-Secret: <secret>` or `Authorization: Bearer <secret>`.

**Cloud Scheduler**:

1. Create a job with type **HTTP**.
2. URL: `https://YOUR-DASHBOARD-BACKEND.run.app/api/cron/run-job-timeout`.
3. Method: POST.
4. Auth header: add `X-Cron-Secret` with the value from Secret Manager (`DASHBOARD_CRON_SECRET`).
5. Schedule: e.g. every 10 minutes for job timeout.

Repeat for `run-cleanup` if you use SQLite (not needed for Cloud SQL; use GCP backup/retention instead).

---

## 11. Environment Variables Reference

### Dashboard backend

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `DATABASE_URL` or `DASHBOARD_DATABASE_URL` | Yes (prod) | PostgreSQL URL (Cloud SQL: Unix socket) | `postgresql://user:pass@/db?host=/cloudsql/PROJECT:REGION:INSTANCE` |
| `PORT` | Set by Cloud Run | HTTP port | `8080` |
| `DASHBOARD_API_PORT` | No | Override if not using `PORT` | `8000` |
| `DASHBOARD_BACKEND_BASE_URL` | Yes (prod) | Backend public URL | `https://dashboard-api-xxx.run.app` |
| `DASHBOARD_FRONTEND_BASE_URL` | Yes (prod) | Frontend public URL | `https://dashboard-xxx.run.app` |
| `DASHBOARD_CORS_ORIGINS` | Yes (prod) | Comma-separated CORS origins | `https://dashboard-xxx.run.app` |
| `DASHBOARD_CRON_SECRET` | For cron | Secret for cron endpoints | (Secret Manager) |
| `DASHBOARD_DEVELOPER_MODE` | No | Set `false` in production | `false` |

### Dashboard frontend (build-time)

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `REACT_APP_API_URL` | Yes | Backend API base URL | `https://dashboard-api-xxx.run.app` |
| `REACT_APP_WS_URL` | No | WebSocket URL (default: derived from API URL) | `wss://dashboard-api-xxx.run.app/ws` |

### PR-Agent (dashboard integration)

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `DASHBOARD_URL` | If using dashboard | Dashboard backend base URL | `https://dashboard-api-xxx.run.app` |
| `DASHBOARD_API_KEY` | No | Optional dashboard API key | (Secret Manager) |

### PR-Agent (ADO webhook server)

| Variable / config | Description |
|-------------------|-------------|
| `PORT` | Set by Cloud Run (e.g. 8080). |
| `azure_devops_server.webhook_username` / `webhook_password` | Basic auth for Service Hooks (match Azure DevOps webhook config). |
| `azure_devops.org` / `azure_devops.pat` | ADO org URL and PAT (or env). |
| `DASHBOARD_URL` | As above. |

### PR-Agent (ADO pipeline runner on self-hosted agent)

| Variable | Source | Description |
|----------|--------|-------------|
| `BUILD_REASON` | Azure DevOps | e.g. `PullRequest`. |
| `SYSTEM_PULLREQUEST_PULLREQUESTID` | Azure DevOps | PR ID. |
| `SYSTEM_TEAMPROJECT`, `BUILD_REPOSITORY_NAME`, `SYSTEM_COLLECTIONURI` | Azure DevOps | Repo and org. |
| `AZURE_DEVOPS_PAT` or `SYSTEM_ACCESSTOKEN` | Pipeline | ADO auth. |
| `OPENAI_KEY` | Pipeline variable | LLM key. |
| `DASHBOARD_URL` | Pipeline variable | Dashboard backend URL. |

---

## 12. Deployment Order and Checklist

**Automation**: Terraform provisions **VPC (with subnets), private Cloud SQL**, GCS config bucket, Secret Manager, Artifact Registry, Cloud Run, Scheduler, and optionally a **runner VM**. For a single run that “just works” from the repo root: **`scripts/full-deploy-gcp.sh`** – set `project_id` in tfvars or `PROJECT_ID`; it runs init, apply (infra), build+push backend/frontend, deploy, and optional health wait. Alternatively use **`scripts/deploy-gcp.ps1`** / **`scripts/deploy-gcp.sh`** when images are already in tfvars (apply + re-apply with URLs). Build images with **`scripts/build-push-gcp.ps1`** / **`scripts/build-push-gcp.sh`** (optional flags: `-BackendOnly`, `-FrontendOnly`; Bash: `BACKEND_URL` can be read from `terraform output backend_url`). **On Windows**, run the **`.ps1`** scripts natively (Docker Desktop + Terraform + gcloud); WSL is optional for the `.sh` scripts.

**CI/CD (automated builds on push)**: Use **`scripts/setup-cicd-gcp.sh`** (bash) or **`scripts/setup-cicd-gcp.ps1`** (PowerShell) for a **one-run setup** that provisions all infrastructure via Terraform **and** creates a Cloud Build trigger connected to your GitHub repo. After setup, pushes to the designated branch (dev → `develop`, stage → `staging`, prod → `main`) automatically build and deploy via `cloudbuild-deploy.yaml`. Use **`--env all`** to provision all three environments at once (the script creates missing branches automatically). Each environment is fully isolated (separate Cloud SQL, Cloud Run, Artifact Registry, secrets, config buckets, runner VMs) via Terraform prefix. See **[docs/CI_CD_SETUP.md](docs/CI_CD_SETUP.md)** for the comprehensive CI/CD guide.

**Suggested order (matches Terraform + full-deploy)**
1. Virtual network: VPC and subnets (connector + optional runner) – Terraform.
2. DB: Cloud SQL (PostgreSQL), database, user; `DATABASE_URL` in Secret Manager – Terraform.
3. GCS: Config bucket and seed files; backend and PR-Agent use `PR_AGENT_CONFIG_GCS_BUCKET` / `PR_AGENT_CONFIG_GCS_PREFIX` – Terraform.
4. Dashboard: Build and push backend/frontend; deploy to Cloud Run; inject CORS/base URLs – full-deploy script or deploy script + build-push.
5. Cloud Scheduler for `/api/cron/run-job-timeout` – Terraform.
6. (Optional) Runner VM: set `enable_runner_vm = true` in tfvars; VM gets PR-Agent and env file; install ADO/GitHub agent and pipeline variables (`DASHBOARD_URL`, `OPENAI_KEY`, GCS vars).
7. (Optional) PR-Agent GitHub App or ADO webhook on Cloud Run; configure webhooks and secrets.

**Checklist**

- [ ] Cloud SQL created; `DATABASE_URL` in Secret Manager; backend can connect.
- [ ] Dashboard backend deployed; `DASHBOARD_CORS_ORIGINS` set to frontend URL; health check uses `/api/health`.
- [ ] Dashboard frontend built with correct `REACT_APP_API_URL` (and `REACT_APP_WS_URL` if needed); deployed.
- [ ] Backend request timeout 60 minutes; max instances = 1 if using WebSockets for a single broadcast.
- [ ] `DASHBOARD_CRON_SECRET` set; Cloud Scheduler calls cron endpoints with `X-Cron-Secret`.
- [ ] PR-Agent (webhook or pipeline) has `DASHBOARD_URL` and required API keys/tokens; no secrets in repo.
- [ ] If using ADO self-hosted agent: VM has outbound HTTPS; agent pool online; pipeline variables set (`OPENAI_KEY`, `DASHBOARD_URL`); pipeline triggers on PR and runs `azuredevops_pipeline_runner`.

**Teardown (clean slate):** To remove all GCP resources and try again, run **`scripts/teardown-gcp.ps1`** (Windows) or **`scripts/teardown-gcp.sh`** from the repo root; use `-Force` or `-auto-approve` to skip confirmation. See `terraform/gcp/README.md` § Cleanup.

For more detail on the dashboard and GCP, see `docs/GCP_DEPLOYMENT.md`. For Azure DevOps setup (webhook vs pipeline), see `docs/docs/installation/azure.md` and the repo’s `azure-pipelines-pr-agent.yml` example.
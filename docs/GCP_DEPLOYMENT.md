# Deploying PR-Agent and Dashboard on Google Cloud Platform

This guide covers deploying the PR-Agent dashboard (frontend, backend) and the PR-Agent itself to GCP with **Google Cloud SQL** (PostgreSQL), **env-based configuration**, and **Docker** images suitable for Cloud Run or GKE.

## Architecture Overview

- **Dashboard frontend**: Static React app served by nginx (or Cloud Storage + CDN). API and WebSocket URLs are set at **build time** via `REACT_APP_API_URL` and `REACT_APP_WS_URL`.
- **Dashboard backend**: FastAPI app (uvicorn). Connects to **Cloud SQL (PostgreSQL)** via `DATABASE_URL`. Listens on `PORT` (Cloud Run sets this).
- **PR-Agent**: Runs as server (e.g. GitHub App, **Azure DevOps webhook**, or CLI). Talks to the dashboard via `DASHBOARD_URL` and optional `DASHBOARD_API_KEY` (env or config).
- **Azure DevOps (ADO)**: For ADO repos you can (a) deploy the **ADO webhook server** so new PRs trigger PR Agent via Service Hooks, or (b) run PR Agent from an **Azure Pipeline** on a self-hosted agent (pipeline calls PR Agent when a PR triggers the build). Both can be used in GCP (webhook server on Cloud Run; pipeline runs on your self-hosted agent).
- **Database**: **Cloud SQL for PostgreSQL**. SQLite is still supported for local/dev; for production GCP, use Cloud SQL only.
- **Runner/agent health**: On **Windows**, the dashboard can check local runner/agent **Windows services**. On **Linux/Cloud Run**, local service checks are disabled; health comes from **provider APIs** (GitHub Actions API, Azure DevOps pool API) only.

## Environment Variables Reference

### Dashboard Backend

| Variable | Description | Example |
|----------|-------------|--------|
| `DATABASE_URL` or `DASHBOARD_DATABASE_URL` | PostgreSQL connection string (Cloud SQL) | `postgresql://user:pass@/dbname?host=/cloudsql/PROJECT:REGION:INSTANCE` |
| `PORT` | HTTP port (Cloud Run sets this) | `8080` |
| `DASHBOARD_API_PORT` | Override port if not using `PORT` | `8000` |
| `DASHBOARD_BACKEND_BASE_URL` | Base URL of this backend (for internal callbacks / logs) | `https://dashboard-api-xxx.run.app` |
| `DASHBOARD_FRONTEND_BASE_URL` | Base URL of the frontend (for links in notifications) | `https://dashboard-xxx.run.app` |
| `DASHBOARD_CORS_ORIGINS` | Allowed CORS origins (comma-separated or via settings) | `https://dashboard-xxx.run.app` |
| `DASHBOARD_CRON_SECRET` | Secret for cron endpoints (Cloud Scheduler); if set, required for `/api/cron/*` | (store in Secret Manager) |
| `DASHBOARD_API_KEY` | When set, PR-Agent can use Bearer token for jobs/operations/logs. **Terraform**: auto-generated if not in tfvars; deploy script prints it so you can set it in PR-Agent / pipelines. | (auto-generated or set in tfvars) |
| `DASHBOARD_CORS_ORIGINS` | Comma-separated allowed origins (overrides defaults); **required for GCP** so frontend can call API | `https://dashboard-xxx.run.app` |
| `DASHBOARD_DEVELOPER_MODE` | Set to `false` in production to disable dev-only routes | `false` |
| `GCP_RUNNER_PROJECT_ID`, `GCP_RUNNER_REGION`, `GCP_RUNNER_ZONE` | Optional; when set, dashboard can **provision runner VMs on demand** from the UI. **Terraform** sets these from `project_id`/`region`/`runner_zone` so "Provision runner VM" works. | (set by Terraform when using `terraform/gcp`) |

**Note:** Cloud Run sets `PORT` at runtime; the backend Dockerfile binds `0.0.0.0` and uses `PORT` (default 8000). No need to set `PORT` in the image.

For Cloud SQL with Cloud Run, use the [Unix socket connection](https://cloud.google.com/sql/docs/postgres/connect-run):  
`postgresql://USER:PASSWORD@/DATABASE?host=/cloudsql/PROJECT_ID:REGION:INSTANCE_NAME`

### Dashboard Frontend (build-time)

| Variable | Description | Example |
|----------|-------------|--------|
| `REACT_APP_API_URL` | Backend API base URL | `https://dashboard-api-xxx.run.app` |
| `REACT_APP_WS_URL` | WebSocket URL (optional; if unset, derived from API URL) | `wss://dashboard-api-xxx.run.app/ws` |

Set these as **build args** when building the frontend Docker image (see below).

### PR-Agent (Dashboard integration)

| Variable | Description | Example |
|----------|-------------|--------|
| `DASHBOARD_URL` | Dashboard backend base URL | `https://dashboard-api-xxx.run.app` |
| `DASHBOARD_API_KEY` | Optional API key for dashboard auth | (set via Secret Manager in production) |

These override `DASHBOARD.URL` and `DASHBOARD.API_KEY` from config files.

### Azure DevOps webhook server (for ADO repos)

| Variable | Description | Example |
|----------|-------------|--------|
| `PORT` | HTTP port (Cloud Run sets this) | `3000` |
| Config (in pr_agent settings) | `azure_devops_server.webhook_username`, `webhook_password` (Basic auth for Service Hooks) | (use Secret Manager) |
| Config | `azure_devops.org`, `azure_devops.pat` or Azure Default Credentials | For PR Agent to call ADO API |

## 1. Cloud SQL (PostgreSQL) Setup

1. Create a Cloud SQL for PostgreSQL instance (e.g. via Console or `gcloud sql instances create`).
2. Create a database and user; note the connection name (`PROJECT:REGION:INSTANCE`).
3. For Cloud Run, enable the **Cloud SQL Admin API** and attach the instance to the Cloud Run service (see Cloud Run docs).
4. Store the connection string in **Secret Manager** (e.g. `DATABASE_URL`) and inject it into the dashboard backend at runtime—never commit secrets.

Example (Cloud Run with Unix socket):

```bash
# After creating instance and database
DATABASE_URL="postgresql://dashboard_user:SECRET@/dashboard_db?host=/cloudsql/my-project:us-central1:my-instance"
# Store in Secret Manager, then reference in Cloud Run
```

Run migrations: the dashboard backend runs `migrate_database()` on startup when tables are missing. For a fresh Cloud SQL DB, ensure the app has permission to create tables (or run migrations separately).

## 2. Building Docker Images

Build from the **repository root**.

### Dashboard backend

```bash
docker build -f dashboard/backend/Dockerfile -t gcr.io/PROJECT_ID/pr-agent-dashboard-backend .
```

Run locally with Cloud SQL Proxy (optional):

```bash
# Start Cloud SQL Proxy, then:
docker run -p 8000:8000 \
  -e DATABASE_URL="postgresql://user:pass@host:5432/dbname" \
  -e DASHBOARD_BACKEND_BASE_URL="http://localhost:8000" \
  pr-agent-dashboard-backend
```

### Dashboard frontend

Set the backend URL at **build time**:

```bash
docker build -f dashboard/frontend/Dockerfile \
  --build-arg REACT_APP_API_URL=https://your-dashboard-api.run.app \
  --build-arg REACT_APP_WS_URL=wss://your-dashboard-api.run.app/ws \
  -t gcr.io/PROJECT_ID/pr-agent-dashboard-frontend .
```

### PR-Agent (GitHub App)

```bash
docker build -f docker/Dockerfile --target github_app -t gcr.io/PROJECT_ID/pr-agent-github-app .
```

Set env when running: `DASHBOARD_URL`, `DASHBOARD_API_KEY` (if used).

### PR-Agent – Azure DevOps webhook server (for ADO repos)

Deploy this so Azure DevOps can send PR events (e.g. **Pull request created**) to PR Agent via Service Hooks. New PRs will trigger configured commands (e.g. describe, review).

```bash
docker build -f docker/Dockerfile --target azure_devops_webhook -t gcr.io/PROJECT_ID/pr-agent-ado-webhook .
```

- Expose HTTPS (Cloud Run or load balancer). **Service Hooks require HTTPS** and optionally Basic auth.
- In Azure DevOps: **Project settings → Service hooks → Create subscription** → Web Hook. URL = `https://your-ado-webhook.run.app/`, event e.g. **Pull request created**. If you set `webhook_username` / `webhook_password` in config, use them as Basic auth in the Service Hook.
- Configure `azure_devops_server.pr_commands` (e.g. `["/describe", "/review"]`) and `azure_devops.org` / `azure_devops.pat` (or Azure Default Credentials) so PR Agent can call the ADO API.
- Set `DASHBOARD_URL` (and `DASHBOARD_API_KEY` if used) so this server can report to the dashboard.

**Alternative: Azure Pipeline on a self-hosted agent**  
To trigger PR Agent from a **pipeline** (instead of or in addition to the webhook), add an Azure Pipeline that runs when a PR is created and invoke the PR Agent pipeline runner (e.g. `python -m pr_agent.servers.azuredevops_pipeline_runner` or your pipeline step that runs it). The pipeline runs on your **self-hosted agent** (Windows or Linux); the agent can be on-prem or on a GCP VM. No webhook server is required for this path; the agent needs `AZURE_DEVOPS_PAT`, `OPENAI_KEY`, and optional `DASHBOARD_URL` / `DASHBOARD_API_KEY`. See the repo’s Azure DevOps pipeline docs for YAML examples.

## 3. Deploying to Cloud Run

1. **Backend**
   - Deploy the dashboard backend image.
   - Add Cloud SQL connection (instance connection name).
   - Set env: `DATABASE_URL` from Secret Manager; optionally `DASHBOARD_BACKEND_BASE_URL` and `DASHBOARD_FRONTEND_BASE_URL` to your Cloud Run URLs.
   - Set **CORS**: `DASHBOARD_CORS_ORIGINS` to your frontend origin(s), comma-separated (e.g. `https://dashboard-xxx.run.app`). Required so the browser allows API/WebSocket requests from the frontend.
   - **Health**: Cloud Run can use `GET /api/health` for liveness/readiness if needed.
   - For production, set `DASHBOARD_DEVELOPER_MODE=false` (or use `[production]` in settings.toml) to disable dev-only routes.
   - Allow unauthenticated or IAM as needed.

2. **Frontend**
   - Deploy the frontend image (nginx serving static files).
   - Build the image with the correct `REACT_APP_API_URL` and `REACT_APP_WS_URL` pointing to the backend Cloud Run URL.

3. **PR-Agent**
   - Deploy the PR-Agent image (e.g. GitHub App server).
   - Set `DASHBOARD_URL` (and `DASHBOARD_API_KEY` if used) so it can report to the dashboard.

### 3.1 WebSocket and Cloud Run

The dashboard uses **WebSockets** for real-time updates (jobs, operations, logs, metrics). The setup is suitable for GCP with a few configuration steps.

**Architecture**

- **Backend**: FastAPI WebSocket at `GET /ws`. A single in-memory `WebSocketManager` keeps a list of connected clients and broadcasts JSON messages (job updates, operation steps, logs, metrics, backup progress). The server sends a ping every 30 seconds to keep connections alive.
- **Frontend**: Connects to `REACT_APP_WS_URL` if set; otherwise derives the WebSocket URL from `REACT_APP_API_URL` (e.g. `https://…` → `wss://…/ws`). Includes reconnect with backoff and a heartbeat to detect dead connections.

**Cloud Run behavior**

- **WebSocket support**: Cloud Run supports WebSocket connections; no extra proxy config is needed when using the default Cloud Run URL.
- **Request timeout**: WebSocket streams are treated as long-lived HTTP requests. Increase the **Cloud Run request timeout** (e.g. to **60 minutes**) so connections are not closed by the platform. Default is 5 minutes. Set this in the Cloud Run service (Console → Edit & deploy → Request timeout, or `gcloud run services update ... --timeout=3600`).
- **HTTP/2**: Do **not** enable HTTP/2 end-to-end for the Cloud Run service if you use WebSockets; use the default (HTTP/1.1 upgrade).
- **Scaling**: The backend’s WebSocket broadcast is **in-memory per instance**. For predictable real-time behavior, use **a single instance** (e.g. set **max instances = 1** for the dashboard backend) so all clients receive the same broadcasts. If you scale to multiple instances, each instance only sees its own WebSocket clients; cross-instance broadcast would require a shared bus (e.g. Redis Pub/Sub), which is not implemented today.

**Frontend build**

- Build the frontend with `REACT_APP_API_URL` set to the backend’s **HTTPS** URL (e.g. `https://dashboard-api-xxx.run.app`). The client will then use **wss** and `/ws` automatically. Optionally set `REACT_APP_WS_URL` explicitly (e.g. `wss://dashboard-api-xxx.run.app/ws`) if you use a path prefix or a different WebSocket URL.

**Summary**

| Item | Recommendation |
|------|----------------|
| Request timeout | 60 minutes (3600s) for the backend Cloud Run service |
| HTTP/2 end-to-end | Off (default) |
| Max instances | 1 if you want all clients to get the same real-time updates |
| REACT_APP_WS_URL | Optional; derived from REACT_APP_API_URL (https → wss, + `/ws`) |

## 4. Scheduled Events and Cloud Scheduler

On **Cloud Run**, the dashboard backend can scale to zero. In-process background tasks (cleanup, backup, job-timeout checks) only run while an instance is alive. For production you should trigger scheduled work via **Google Cloud Scheduler** calling HTTP endpoints.

### Cron endpoints (always registered)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/cron/run-cleanup` | POST | Run retention cleanup (SQLite only; returns "skipped" for Cloud SQL). |
| `/api/cron/run-job-timeout` | POST | Mark stale running jobs as failed (works with any DB). |

**Authentication:** Set `DASHBOARD_CRON_SECRET` in the backend environment. Each request must include either:

- Header `X-Cron-Secret: <secret>`, or  
- Header `Authorization: Bearer <secret>`

If `DASHBOARD_CRON_SECRET` is not set, these endpoints return 503. Use a strong random value and store it in Secret Manager.

### Example: Cloud Scheduler jobs

1. **Job timeout check** (e.g. every 10 minutes):  
   - URL: `https://your-dashboard-api.run.app/api/cron/run-job-timeout`  
   - Method: POST  
   - Auth header: `X-Cron-Secret: <your-secret>`

2. **Cleanup** (only for SQLite; for Cloud SQL use GCP managed retention or custom SQL):  
   - URL: `https://your-dashboard-api.run.app/api/cron/run-cleanup`  
   - Method: POST  
   - Schedule: e.g. daily  
   - Same header as above.

For **Cloud SQL**, retention/cleanup that deletes old rows is not built into the dashboard (the in-app cleanup is SQLite-only). Use Cloud SQL automated backups and, if you need row-level retention, a separate Cloud Run job or Cloud Function that runs your own SQL or calls a custom admin endpoint.

## 5. Backup and Retention on Cloud SQL

- **File-based backup/restore** in the dashboard (SQLite) is **disabled** when `DATABASE_URL` is PostgreSQL. Use **GCP managed backups** (automated backups, point-in-time recovery) for Cloud SQL.
- **Retention/cleanup** (deleting old logs/jobs) that uses SQLite file ops is also disabled for Cloud SQL; use Cloud Scheduler + `/api/cron/run-cleanup` only for SQLite, or GCP managed retention / custom SQL for Cloud SQL.
- **Database stats** in the admin UI work for both: table counts from the DB; file size only for SQLite.

## 6. Runner and Agent Health (Cloud-Ready)

The dashboard shows health for **GitHub self-hosted runners** and **Azure DevOps agents**.

- **On Windows** (e.g. on-prem): The dashboard can check **local Windows services** by name (GitHub Actions runner service, Azure DevOps agent service). Use "Runner service" / "Azure agent service" in the repo settings and the "Check" button to verify.
- **On Linux / Cloud Run**: Local process and Windows service checks are **not available**. The dashboard does **not** call PowerShell or list Windows services. Instead:
  - **GitHub**: Runner health comes from the **GitHub Actions API** (runners for the repo). Ensure the repo has a GitHub token with **Actions: read** for runner status.
  - **Azure DevOps**: Agent health comes from the **Azure DevOps pool API** (agents in pools). Ensure the repo has an Azure PAT with permissions to read agent pools.
- **Recommendation for GCP**: Do **not** configure "runner service name" or "Azure agent service name" for repos when the dashboard runs on Cloud Run. Rely on **API-based health** only. Optionally run the dashboard on a Windows VM if you need local service checks for on-prem runners.

## 7. Database Abstraction (No SQLite-Only Assumptions)

The dashboard is written to support **both SQLite and PostgreSQL** (Cloud SQL):

- **Connection:** `DATABASE_URL` or `DASHBOARD_DATABASE_URL`; PostgreSQL uses `psycopg2-binary` (in backend requirements).
- **Migrations:** `migrate_database()` uses dialect-appropriate types (e.g. `TIMESTAMP` on PostgreSQL, `DATETIME` on SQLite). New tables from models use SQLAlchemy `create_all()` (dialect-safe).
- **System settings / UPSERT:** `system_settings` and `SystemSettingsService` use `ON CONFLICT DO UPDATE` on PostgreSQL and `INSERT OR REPLACE` on SQLite.
- **Reporting:** Startup and status APIs report the actual database type (e.g. "PostgreSQL" or "SQLite") from the engine dialect.
- **Retention/backup/export:** When the DB is not SQLite, file-based backup, restore, cleanup, and export return clear "use GCP / pg_dump" style messages; stats still return table counts.

## 8. .env.example (Dashboard)

Use these as a reference; do not commit real secrets.

```bash
# Dashboard backend
DATABASE_URL=postgresql://user:password@localhost:5432/dashboard
# Or for Cloud SQL (Cloud Run): postgresql://user:pass@/dbname?host=/cloudsql/PROJECT:REGION:INSTANCE
DASHBOARD_DATABASE_URL=   # alternative env name
PORT=8000
DASHBOARD_BACKEND_BASE_URL=http://localhost:8000
DASHBOARD_FRONTEND_BASE_URL=http://localhost:3000

# Dashboard frontend (build-time only)
REACT_APP_API_URL=http://localhost:8000
REACT_APP_WS_URL=   # optional; default derived from REACT_APP_API_URL

# Cron (for Cloud Scheduler; optional)
# DASHBOARD_CRON_SECRET=your-random-secret

# PR-Agent (when using dashboard)
DASHBOARD_URL=http://localhost:8000
DASHBOARD_API_KEY=
```

## 9. Checklist

- [ ] Cloud SQL (PostgreSQL) instance and database created; connection string in Secret Manager.
- [ ] Dashboard backend image built and deployed; `DATABASE_URL` and (optionally) base URLs set.
- [ ] **CORS**: `DASHBOARD_CORS_ORIGINS` set to frontend origin(s), e.g. `https://your-dashboard.run.app`.
- [ ] Dashboard frontend image built with correct `REACT_APP_API_URL` (and `REACT_APP_WS_URL` if needed); deployed.
- [ ] **WebSocket (if using real-time UI)**: Backend Cloud Run request timeout set to 60 minutes; consider max instances = 1 so all clients get broadcasts.
- [ ] PR-Agent image built and deployed with `DASHBOARD_URL` (and `DASHBOARD_API_KEY` if used).
- [ ] No secrets in repo; use Secret Manager and env injection.
- [ ] If using cron: `DASHBOARD_CRON_SECRET` set; Cloud Scheduler jobs call `/api/cron/run-job-timeout` (and optionally `/api/cron/run-cleanup` for SQLite) with the secret header.
- [ ] Optional: `DASHBOARD_DEVELOPER_MODE=false` in production to disable dev-only endpoints.

## 10. CI/CD with Cloud Build

> **Full documentation**: See [docs/CI_CD_SETUP.md](CI_CD_SETUP.md) for the comprehensive CI/CD guide including environment isolation details, runner VM management, troubleshooting, and day-2 operations.

The `scripts/setup-cicd-gcp.sh` (bash) and `scripts/setup-cicd-gcp.ps1` (PowerShell) scripts perform a **one-run setup** that provisions all GCP infrastructure via Terraform and creates a Cloud Build CI/CD trigger connected to your GitHub repository. After setup, every push to the designated branch automatically builds and deploys the dashboard.

### Quick Start

```bash
# Single environment
./scripts/setup-cicd-gcp.sh --env dev --project my-gcp-project

# All environments (dev + stage + prod) -- creates missing branches automatically
./scripts/setup-cicd-gcp.sh --env all --project my-gcp-project --auto-approve
```

```powershell
# PowerShell equivalents
.\scripts\setup-cicd-gcp.ps1 -Env dev -Project my-gcp-project
.\scripts\setup-cicd-gcp.ps1 -Env all -Project my-gcp-project -AutoApprove
```

### Environment-to-Branch Mapping

| Environment | Branch    | Terraform prefix       |
|-------------|-----------|------------------------|
| `dev`       | `develop` | `pr-agent-dash-dev`    |
| `stage`     | `staging` | `pr-agent-dash-stage`  |
| `prod`      | `main`    | `pr-agent-dash`        |
| `all`       | (all above)| (all above)           |

Each environment gets fully isolated GCP resources (Cloud SQL, Cloud Run services, Artifact Registry, secrets, config buckets, runner VMs, etc.) via a unique Terraform prefix and separate state path.

### Options

| Flag (bash) | Flag (PowerShell) | Description |
|-------------|-------------------|-------------|
| `--env <dev\|stage\|prod\|all>` | `-Env` | Target environment(s) |
| `--project <id>` | `-Project` | GCP project ID |
| `--region <region>` | `-Region` | GCP region (default: `us-central1`) |
| `--auto-approve` | `-AutoApprove` | Skip Terraform confirmation prompts |
| `--skip-deploy` | `-SkipDeploy` | Infra + trigger only; no Docker build |

### How CI/CD Works After Setup

Pushes to the environment's branch that modify `dashboard/**`, `terraform/gcp/**`, or `cloudbuild-deploy.yaml` trigger Cloud Build, which builds new Docker images and deploys via `gcloud run services update --image` (preserving all existing configuration).

### Monitoring Builds

```
https://console.cloud.google.com/cloud-build/builds?project=YOUR_PROJECT_ID
```

## 11. Troubleshooting: dashboard logs not appearing

PR-Agent sends logs to the dashboard with `POST /logs/immediate` and `POST /logs/batch` using:

- **`DASHBOARD_URL`** – backend base URL (no trailing slash issues; client normalizes).
- **`DASHBOARD_API_KEY`** – sent as `Authorization: Bearer <key>` (must match the backend’s `DASHBOARD_API_KEY`).

### What to check in Cloud Logging (backend)

Run (replace project and service name; backend is often `*-backend`):

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="YOUR_PREFIX-backend" AND (textPayload:"/logs/" OR jsonPayload.message:"/logs/" OR httpRequest.requestUrl:"logs")' \
  --project=YOUR_PROJECT_ID --limit=50 --format=json
```

Look for:

| Symptom | Likely cause |
|--------|----------------|
| **401** on `/logs/immediate` or `/logs/batch` | Runner `DASHBOARD_API_KEY` missing or does not match Cloud Run env / Secret |
| **500** with `Failed to process immediate log` or `_handle_log_operation` | Fixed in code: log insert must use the persistence queue helper (deploy latest backend) |
| **No POST /logs at all** | PR-Agent not configured: `DASHBOARD_URL` unset on runner, or dashboard sink disabled |

### Runner / pipeline

On the VM or in pipeline variables, confirm:

```bash
echo "$DASHBOARD_URL"
# Optional: do not print the key in shared logs; only verify it is set
test -n "$DASHBOARD_API_KEY" && echo "DASHBOARD_API_KEY is set"
```

See also [RUNNER_VM_AND_PR_AGENT_FLOW.md](RUNNER_VM_AND_PR_AGENT_FLOW.md) for where `DASHBOARD_URL` is written for cloud runners.

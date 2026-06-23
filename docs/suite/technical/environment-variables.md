# Environment Variables

Catalog for the dashboard backend, PR-Agent, Azure Pipelines, and runner VMs.

---

## Shared (dashboard + PR-Agent)

| Variable | Required | Description |
|----------|----------|-------------|
| `PR_AGENT_CONFIG_GCS_BUCKET` | Prod | GCS bucket name (`{project}-{prefix}-config`) |
| `PR_AGENT_CONFIG_GCS_PREFIX` | Prod | Object prefix (default `pr-agent-config/`) |
| `PR_AGENT_CONFIG_PATH` | Dev | Local config dir; **overrides GCS** |
| `PR_AGENT_CONFIG_CACHE_DIR` | No | GCS download cache (PR-Agent) |
| `DASHBOARD_URL` | Runners | Backend URL for telemetry |
| `DASHBOARD_API_KEY` | Both | Bearer token for ingest |
| `DASHBOARD__URL` | No | Dynaconf alternate for dashboard URL |

---

## Dashboard backend (Cloud Run)

| Variable | Default / source | Description |
|----------|------------------|-------------|
| `PORT` | 8080 on Cloud Run | Bind port |
| `DATABASE_URL` | Secret Manager | PostgreSQL or SQLite |
| `DASHBOARD_API_KEY` | Secret Manager | Machine auth |
| `DASHBOARD_CRON_SECRET` | Secret Manager | Scheduler auth |
| `DASHBOARD_CORS_ORIGINS` | Terraform | Comma-separated origins |
| `DASHBOARD_BACKEND_BASE_URL` | Terraform `backend_url` | Self-reference, links |
| `DASHBOARD_FRONTEND_BASE_URL` | Second Terraform apply | UI links |
| `DASHBOARD_DEVELOPER_MODE` | `false` (Terraform) | Enables `/api/dev/*` |
| `PR_AGENT_CONFIG_GCS_*` | Terraform | Config bucket access |
| `GCP_RUNNER_*` | Terraform | VM provisioning (see below) |
| `PR_AGENT_AZDO_SHARED_PIPELINE_REPO` | `pr-agent-pipelines` | Shared pipeline repo name |
| `PR_AGENT_AZDO_SHARED_PIPELINE_NAME` | `PR-Agent Shared` | Pipeline display name |
| `PR_AGENT_AZDO_USE_SHARED_PIPELINE_REPO` | `true` | Shared vs per-repo YAML |
| `K_SERVICE`, `GOOGLE_CLOUD_REGION`, `GOOGLE_CLOUD_PROJECT_NUMBER` | Cloud Run metadata | Auto URL resolution |

Log ingest limits: `DASHBOARD_MAX_LOG_BATCH_ENTRIES`, `DASHBOARD_MAX_LOG_INGEST_BODY_BYTES`

The JWT secret is hardcoded in `AuthService` (`dashboard/backend/services/auth_service.py`) for the default deployment. Rotate via code/config before production hardening.

---

## Dashboard frontend (build-time)

| Variable | Description |
|----------|-------------|
| `REACT_APP_API_URL` | Backend REST base |
| `REACT_APP_WS_URL` | WebSocket URL (`wss://.../ws`) |

These are baked into static assets on each frontend Docker build.

---

## Runner VM env file

**Path:** `/opt/pr-agent-runner/env`  
**Written by:** `gcp_runner_service._get_startup_script` (dashboard provision) or `runner-startup.sh.tpl` (Terraform legacy: 5 vars, no PAT)

| Variable | Dashboard provision |
|----------|---------------------|
| `DASHBOARD_URL` | Yes |
| `DASHBOARD_API_KEY` | Yes |
| `PR_AGENT_CONFIG_GCS_BUCKET` | Yes |
| `PR_AGENT_CONFIG_GCS_PREFIX` | Yes |
| `GCP_RUNNER_PR_AGENT_IMAGE` | Yes |
| `AZURE_DEVOPS_PAT` | Yes (when connection has PAT) |

Permissions: `chmod 640`, group `azagent` when the ADO agent is installed.

---

## Azure Pipeline: system (automatic)

ADO injects these; the runner expects them on every PR build.

| Variable | Description |
|----------|-------------|
| `BUILD_REASON` | Must be `PullRequest` |
| `SYSTEM_PULLREQUEST_PULLREQUESTID` | PR ID |
| `SYSTEM_COLLECTIONURI` | Org base URL |
| `SYSTEM_TEAMPROJECT` | Project (fallback) |
| `BUILD_REPOSITORY_NAME` | Pipeline repo name |
| `SYSTEM_PULLREQUEST_SOURCEREPOSITORYURI` | **Actual PR repo** |
| `SYSTEM_ACCESSTOKEN` | OAuth token (alternate to PAT) |

---

## Azure Pipeline: secrets & config

| Variable | Description |
|----------|-------------|
| `AZURE_DEVOPS_PAT` | ADO API auth |
| `OPENAI_KEY` / `OPENAI.KEY` | OpenAI (both forms accepted) |
| `OPENAI_ORG` / `OPENAI.ORG` | OpenAI org |
| `ANTHROPIC_KEY` / `ANTHROPIC.KEY` | Anthropic |
| `DASHBOARD_URL` | Overrides stale GCS values |
| `DASHBOARD_API_KEY` | Telemetry auth |
| `PR_AGENT_CONFIG_GCS_BUCKET` | Config bucket |
| `PR_AGENT_CONFIG_GCS_PREFIX` | Config prefix |
| `GCP_RUNNER_PR_AGENT_IMAGE` / `PR_AGENT_IMAGE` | Docker image for pipeline |
| `CSHARP_CODE_CONTEXT_SERVICE__BASE_URL` | Context service URL override |
| `CSHARP_CODE_CONTEXT_SERVICE__ENABLED` | Enable context (`true` / `false`) |

Full settings: `[csharp_code_context_service]` in `csharp_code_context.config.toml` and `csharp_code_context.secrets.toml`. See [Code context and time estimation](../internals/code-context-and-estimation.md).

### Auto-run toggles

Set via pipeline step, not the YAML variables block:

| Variable | Description |
|----------|-------------|
| `AZURE_DEVOPS_CONFIG.AUTO_DESCRIBE` | `/describe` |
| `AZURE_DEVOPS_CONFIG.AUTO_REVIEW` | `/review` |
| `AZURE_DEVOPS_CONFIG.AUTO_IMPROVE` | `/improve` |
| `AZURE_DEVOPS_CONFIG.ENABLE_OUTPUT` | Publish to PR |
| `AZURE_DEVOPS_CONFIG.PR_ACTIONS` | Action filter (default includes `pullrequest`) |

Legacy fallbacks: `AZURE_DEVOPS.AUTO_*`

Runtime overrides: `CONFIG.GIT_PROVIDER`, `CONFIG.MODEL`, `CONFIG.LOG_LEVEL`, `CONFIG.PUBLISH_OUTPUT_PROGRESS`

---

## PR-Agent runtime

| Variable | Description |
|----------|-------------|
| `LOG_LEVEL`, `LOG_SANE` | Logging |
| `AUTO_CAST_FOR_DYNACONF` | Set internally during repo settings merge |

### LiteLLM provider keys (via TOML or env)

OpenAI, Anthropic, Google, Mistral, DeepSeek, DeepInfra, OpenRouter, Azure OpenAI, Bedrock, Ollama: see `pr_agent/algo/ai_handlers/litellm_ai_handler.py` for the full mapping.

---

## Resolution priority

```
Config files:  PR_AGENT_CONFIG_PATH  →  GCS  →  package defaults
Dashboard URL: pipeline DASHBOARD_URL env  →  [dashboard].url in TOML
ADO PAT:       pipeline AZURE_DEVOPS_PAT  →  [azure_devops].pat in secrets
LLM keys:      pipeline OPENAI_KEY/ANTHROPIC_KEY  →  secrets.toml  →  get_settings().set()
Auto flags:    pipeline env  →  legacy env  →  repo TOML  →  global (None = enabled)
```

---


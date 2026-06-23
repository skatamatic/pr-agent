# Config, Cloud Run, and operations

## Shared configuration (GCS)

| Environment variable | Set on | Meaning |
|---------------------|--------|---------|
| `PR_AGENT_CONFIG_GCS_BUCKET` | Backend Cloud Run, runner VM env file | GCS bucket name |
| `PR_AGENT_CONFIG_GCS_PREFIX` | Same | Object prefix inside bucket |
| `PR_AGENT_CONFIG_PATH` | Local dev only | Local directory; **wins over GCS** when set |

**Load order in PR-Agent:** package defaults → overlay from GCS (or local path) → runtime repo settings → pipeline env overrides.

Production Cloud Run backend is **not** given `PR_AGENT_CONFIG_PATH`; it uses GCS env vars only.

Secrets in GCS are stored as `secrets.toml` (no leading dot); locally mapped to `.secrets.toml`.

## Cloud Run settings (backend)

Defaults from `terraform/gcp/variables.tf`:

| Setting | Default | Scope |
|---------|---------|-------|
| `max_instance_count` | **1** | Backend only (WebSocket consistency) |
| `timeout` | **3600s** (60 min) | Backend only |
| VPC connector | Yes | Backend → Cloud SQL private IP |
| Frontend | Port 80, no VPC connector | Static nginx |

Frontend scaling is not constrained the same way; long AI work happens on the runner VM, not Cloud Run.

## Azure DevOps runner placement

```
Azure DevOps PR
  → build validation policy
  → pipeline on self-hosted agent pool
  → docker pull PR-Agent image
  → python3 -m pr_agent.servers.azuredevops_pipeline_runner
  → dashboard telemetry + ADO API
```

**Dashboard on-demand (recommended):** Repositories → Action Runners → Provision VM.

**Terraform legacy:** set `enable_runner_vm = true` in tfvars for a single VM at deploy time.

**Bring your own agent:** skip provisioning and use an existing pool.

`enable_runner_vm` defaults to **false** in Terraform: prefer dashboard provisioning.

See [Self-hosted runners](../self-hosted-runners.md) for bootstrap and env file details.

## Post-deploy: Azure DevOps pipeline variables

Set in Azure DevOps variable group or pipeline (dashboard can sync via **Fix Issues** on Azure Pipeline tab):

| Variable | Source |
|----------|--------|
| `DASHBOARD_URL` | Terraform `backend_url` |
| `DASHBOARD_API_KEY` | Terraform `dashboard_api_key` |
| `OPENAI_KEY` / `ANTHROPIC_KEY` | AI Config → synced to pipeline |
| `AZURE_DEVOPS_PAT` | Service connection or secret variable |
| `PR_AGENT_CONFIG_GCS_BUCKET` | Terraform `config_bucket` |
| `PR_AGENT_CONFIG_GCS_PREFIX` | Terraform `config_prefix` |
| `GCP_RUNNER_PR_AGENT_IMAGE` | Set automatically after PR-Agent image build |

**Existing runner VMs do not auto-update** when a new PR-Agent image is pushed: re-provision or manually `docker pull` on the VM.

## Environment isolation (CI/CD)

| Environment | Branch | Terraform prefix |
|-------------|--------|------------------|
| Development | `develop` | `pr-agent-dash-dev` |
| Staging | `staging` | `pr-agent-dash-stage` |
| Production | `main` | `pr-agent-dash` |

See [docs/CI_CD_SETUP.md](../../../CI_CD_SETUP.md) for trigger and resource naming.

## Operational notes

- Frontend connects to `wss://{backend}/ws` for live job and log updates.
- Cloud Scheduler hits `/api/cron/run-job-timeout` to mark jobs failed after **1 hour** of inactivity.
- `/api/cron/run-cleanup` is for **SQLite/dev** only; on Cloud SQL it returns `{"skipped": true}`.
- A second Terraform apply sets `DASHBOARD_CORS_ORIGINS` once the frontend URL is known.
- Pass `OVERWRITE_CONFIG_SEED=1` on deploy to overwrite GCS seed objects.
- Maintenance mode blocks most JWT routes; `/api/health*` and `/api/status` stay public.

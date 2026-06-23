# Technical reference

Architecture and API docs for integrators and maintainers. Default deployment: **Azure DevOps Services** on **Google Cloud**.

## Architecture and deployment

| Section | Summary |
|---------|---------|
| [Deployment on Google Cloud](deployment/README.md) | Live stack, topology, Terraform, deploy scripts, operations |
| [Azure PR architecture](azure-architecture/README.md) | End-to-end PR flow, triggers, skips, telemetry |
| [PR-Agent internals](internals/README.md) | Pipeline runner, tools, telemetry |
| [Self-hosted runners](self-hosted-runners.md) | VM bootstrap, env file, deprovision |

### Deployment subpages

- [Topology and GCP services](deployment/topology-and-services.md)
- [Terraform and deploy scripts](deployment/terraform-and-images.md)
- [Config, Cloud Run, and operations](deployment/config-cloud-run-and-ops.md)

### Azure architecture

Single page under `technical/azure-architecture/README.md` (triggers, skips, telemetry, and sequence diagrams).

### Internals subpages

- [Code context and time estimation](internals/code-context-and-estimation.md)
- [Config, AI, and filters](internals/config-ai-and-filters.md)

## Configuration reference

- [TOML configuration system](toml-configuration-system.md)
- [Environment variables](environment-variables.md)
- [Dashboard API](dashboard-api/README.md)

## How-to cross-links

- [Configuring PR filters](../how-to/configuring-pr-filters.md)
- [Choosing and configuring AI models](../how-to/choosing-and-configuring-ai-models.md)
- [Maintenance and diagnostics](../how-to/maintenance/README.md)

## Execution model

```
ADO PR → build validation → self-hosted agent
  → docker run pr-agent image
  → config_loader (GCS at import)
  → azuredevops_pipeline_runner.run_action()
  → apply_repo_settings → pr_filters → job_context → tools
  → optional code context + dev-time estimation
  → ADO comments + dashboard telemetry
```

## Key source files

- ADO runner: `pr_agent/servers/azuredevops_pipeline_runner.py`
- PR filters: `pr_agent/algo/pr_filters.py`
- Config I/O: `dashboard/backend/services/config_service.py`
- VM provisioning: `dashboard/backend/services/gcp_runner_service.py`
- Terraform: `terraform/gcp/main.tf`

## Auth (quick reference)

- **Browser UI**: JWT from `POST /api/auth/login`
- **PR-Agent ingest**: `Authorization: Bearer {DASHBOARD_API_KEY}`
- **Cloud Scheduler**: `X-Cron-Secret` or Bearer `{DASHBOARD_CRON_SECRET}`

See [Dashboard API → Security model](dashboard-api/README.md#security-model).

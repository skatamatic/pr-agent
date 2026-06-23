# AI Code Reviews - PR-Agent

Automated **deep** pull-request reviews on **Azure DevOps**, with a **dashboard** for onboarding, monitoring, configuration, and ROI.

## Start here

| Role | Start here |
|------|------------|
| **Developers** | [Using AI code reviews](overview/using-ai-code-reviews.md) |
| **Admins / DevOps** | [Adding an Azure DevOps repository](how-to/onboarding/README.md) |
| **Engineering** | [Technical reference](technical/README.md) |

| Goal | Page |
|------|------|
| Understand the product | [What is this project?](overview/what-is-this-project.md) |
| Deploy on GCP | [Deployment on Google Cloud](technical/deployment/README.md) |
| Configure PR filters | [Configuring PR filters](how-to/configuring-pr-filters.md) |
| Configure AI models | [Choosing and configuring AI models](how-to/choosing-and-configuring-ai-models.md) |
| Fix a failed run | [Maintenance and diagnostics](how-to/maintenance/README.md) |

## Documentation sections

**[PR-Agent overview](overview/README.md)**

- [What is this project?](overview/what-is-this-project.md)
- [Using AI code reviews](overview/using-ai-code-reviews.md) (developers)

**[How-to guides](how-to/README.md)**

- [Adding an Azure DevOps repository](how-to/onboarding/README.md) (wizard and post-onboarding)
- [Maintenance and diagnostics](how-to/maintenance/README.md) (monitoring and troubleshooting)
- [Cleanup and retention](how-to/cleanup-and-retention.md)
- [Configuration and overrides](how-to/configuration-and-overrides.md)
- [Configuring PR filters](how-to/configuring-pr-filters.md)
- [Choosing and configuring AI models](how-to/choosing-and-configuring-ai-models.md)
- [Reading metrics and ROI](how-to/reading-metrics-and-roi.md)

**[Technical reference](technical/README.md)**

- [Deployment on Google Cloud](technical/deployment/README.md)
- [Azure PR architecture](technical/azure-architecture/README.md)
- [PR-Agent internals](technical/internals/README.md)
- [Dashboard API](technical/dashboard-api/README.md)
- [Environment variables](technical/environment-variables.md)
- [TOML configuration](technical/toml-configuration-system.md)
- [Self-hosted runners](technical/self-hosted-runners.md)

**[Screenshot assets](assets/README.md)** (checklist for UI captures)

## Conventions

- Target platform: **Azure DevOps Services** (cloud).
- API paths use `/api` except log ingest (`/logs/immediate`, `/logs/batch`).
- Wizard UI labels: **Step 1–5** (internal state is 0-indexed).

## Repo docs outside this suite

- `deployment.md`: extended GCP architecture reference
- `docs/GCP_DEPLOYMENT.md`: env vars and troubleshooting
- `docs/CI_CD_SETUP.md`: Cloud Build triggers by branch

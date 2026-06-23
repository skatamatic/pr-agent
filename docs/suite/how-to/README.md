# How-to guides



Administrator and operator guides for running PR-Agent on **Azure DevOps** through the dashboard.



These pages are **view-centric**: navigation tabs, buttons, wizards, and what you see on screen. REST routes, request bodies, and automation live under [Technical reference](../technical/README.md) → [Dashboard API](../technical/dashboard-api/README.md).



## Guides



### Onboarding and operations



- [Adding an Azure DevOps repository](onboarding/README.md): wizard overview, verify, troubleshoot

  - [Wizard steps (1–5)](onboarding/wizard-steps.md): detailed step-by-step

- [Maintenance and diagnostics](maintenance/README.md): diagnostic checklist, health and logs

  - [Monitoring and logs](maintenance/monitoring-and-logs.md)

  - [Troubleshooting](maintenance/troubleshooting.md)

- [Cleanup and retention](cleanup-and-retention.md): delete jobs/repos, bulk cleanup



### Configuration



- [Configuration and overrides](configuration-and-overrides.md): AI Config, PR-Agent Config, Best Practices

- [Configuring PR filters](configuring-pr-filters.md): skip/terminate rules, opt-out, line limits

- [Choosing and configuring AI models](choosing-and-configuring-ai-models.md): models, keys, pipeline sync

- [Reading metrics and ROI](reading-metrics-and-roi.md): Metrics tab, ROI reporting



## Fix Issues after onboarding



The wizard saves the repository but does **not** sync pipeline variables. After **Add Repository**, open the repo card → **Azure Pipeline** tab → **Fix Issues**.



## Before you onboard a repo



- ADO org URL and PAT (Code read & write, Build read & execute)

- At least one **online** agent in the target pool

- LLM keys in AI Config

- Populated GCS config bucket in production



PR flow: [Azure PR architecture](../technical/azure-architecture/README.md). Developer guide: [Using AI code reviews](../overview/using-ai-code-reviews.md).


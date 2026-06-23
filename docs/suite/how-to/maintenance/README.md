# Maintenance and diagnostics

Day-2 operations: health checks, live logs, and fixing failed PR runs.

## Pages in this section

| Page | Topics |
|------|--------|
| [Monitoring and logs](monitoring-and-logs.md) | Overview cards, Jobs, Logs tab |
| [Troubleshooting](troubleshooting.md) | API keys, PAT, context service, pipeline, runners |

## Diagnostic checklist

When a PR run fails, work top to bottom:

```
□ Overview: Database + PR-Agent Config green?
□ AI Config: Test Model succeeds?
□ General: Test Token green (PAT has Code write)?
□ Azure Pipeline: Fix Issues run, checklist green?
□ Azure DevOps: Agent online in pool?
□ Test PR triggers pipeline (PullRequest)?
□ Dashboard Jobs: new run appears?
□ Logs show tool execution (not all skipped)?
□ Comment visible on PR in Azure DevOps?
```

## Stale jobs and retention

Long-running jobs that never finish are marked **failed** automatically after about an hour on production deployments.

Bulk delete of old jobs and repos: [Cleanup and retention](../cleanup-and-retention.md). Skipped runs: [Configuring PR filters](../configuring-pr-filters.md).

Scheduled job and retention automation for operators: [Dashboard API: Admin and cron](../../technical/dashboard-api/admin-and-cron.md).

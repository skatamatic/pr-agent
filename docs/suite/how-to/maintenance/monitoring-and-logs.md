# Monitoring and logs

## Where to look

| Dashboard area | Use it for |
|----------------|------------|
| **Overview** | Database, PR-Agent Config, Context Service, and Repositories health cards |
| **Jobs** | Run status, per-tool operations, errors, duration |
| **Logs** | Live pipeline and tool output (filter by job or operation) |
| **Repositories → General** | PAT **Test Token** |
| **Repositories → Azure Pipeline** | Readiness checklist, **Fix Issues** |
| **Repositories → Status** | Runner and config check for one repo |

## Live logs

1. Open **Logs**
2. Optionally filter by job or operation (or click **View Logs** from a job row)
3. New lines stream in while a run is active

From **Jobs**, expand a failed run and read **operation-level** errors. A job can show **completed** if any tool succeeded; **failed** only when every tool failed.

## Common failure patterns

| What you see | What to do |
|--------------|------------|
| LLM auth error in logs | Fix keys in **AI Config** → **Test Model**, then **Fix Issues** on the repo |
| Unknown or wrong model | Check model names in **AI Config → AI Models** |
| Azure DevOps 401/403 | PAT expired or missing scope; update PAT on **General** tab |
| Context service timeout | **AI Config → Code Context** → **Test Connection**; check Overview card |
| PR-Agent config not found | **PR-Agent Config** → **Create**, or check **AI Config → Advanced → Repo Settings Branch** |
| No job in dashboard | Pipeline may not be a PR build, or variables missing after onboarding → **Fix Issues** |
| Job **skipped** | PR filters matched; see [Configuring PR filters](../configuring-pr-filters.md) |
| Job stuck **running** | Platform marks stale runs failed after about an hour; see [Maintenance](README.md) |

## Overview health cards

Green cards mean the dashboard can reach the database, load config from GCS, reach the code context service, and see monitored repositories. If a card is red, open it for the error message before debugging individual PR runs.

For REST or automation details, see [Dashboard API: Health](../technical/dashboard-api/health-and-status.md) and [Logs](../technical/dashboard-api/logs.md).

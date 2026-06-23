# Dashboard API

FastAPI backend at `dashboard/backend/main.py`. JSON routes sit under `/api`; log ingest uses `/logs/*` (backward compatibility with PR-Agent clients).

**Base URL**

- Local: `http://localhost:8000`
- Cloud Run: `https://{service}-{project}.run.app`

OpenAPI when running locally: `/docs` and `/redoc`.

---

## Who calls what

| Caller | Auth | Typical use |
|--------|------|-------------|
| React UI | User JWT | Jobs, logs, repos, config |
| PR-Agent on a pipeline runner | `DASHBOARD_API_KEY` | Create jobs, stream logs, update operations |
| Cloud Scheduler | `DASHBOARD_CRON_SECRET` | Job timeout sweep, retention cleanup |
| Monitoring / curl | None | Health and liveness only |

There is no RBAC: you're either authenticated or you're not. Any valid JWT can hit admin routes (cleanup, config writes, repo delete). Treat the dashboard as a single-administrator tool behind network controls, not a multi-tenant product.

---

## Security model

### Authentication modes

**1. User JWT (browser sessions)**

```
POST /api/auth/login
Authorization: Bearer {token}   # subsequent requests
```

- Algorithm: HS256, default expiry 24 hours
- Signing secret is hardcoded in `AuthService` (`dashboard/backend/services/auth_service.py`) unless you change it. Rotate for production.
- Bootstrap user `admin` / `mobile` is created on first startup when no admin exists

**2. Dashboard API key (machine ingest)**

```
Authorization: Bearer {DASHBOARD_API_KEY}
```

- Set `DASHBOARD_API_KEY` on both backend and runner
- Accepted on routes using `require_auth_or_api_key` (job/operation/log ingest)
- Same privilege as a logged-in user on those routes. There is no ingest-only scoped key.

**3. Cron secret**

```
X-Cron-Secret: {DASHBOARD_CRON_SECRET}
# or
Authorization: Bearer {DASHBOARD_CRON_SECRET}
```

- Routes: `/api/cron/*`
- Returns **503** when the secret is not configured

**4. Public (no auth)**

- `/api/health`, `/api/health/{database|config|context}`
- `/api/status`
- `/api/repositories/permissions-guide`

WebSocket auth, maintenance mode, sensitive fields, and deployment hardening are documented in [WebSocket](websocket.md) and the category pages below.

### Sensitive data in responses

- Repository GETs never return PATs or GitHub tokens. You get `has_azure_pat` / `has_github_token` booleans.
- Global config GET masks secret values as `***`
- Logs may contain PR diffs and model output. Lock down the dashboard URL accordingly.

### Deployment hardening

- Put Cloud Run behind IAM, VPN, or an SSO proxy
- Load `DASHBOARD_API_KEY` and `DASHBOARD_CRON_SECRET` from Secret Manager
- Change the default admin password on first login
- Restrict CORS via `DASHBOARD_CORS_ORIGINS`

---

## Response envelope

Successful JSON responses use `APIResponse`:

```json
{
  "data": { },
  "message": "Optional human-readable summary",
  "total": 42,
  "page": null,
  "per_page": null,
  "timestamp": "2026-06-16T12:00:00.000Z"
}
```

List endpoints often set `total`. Not every route populates every field.

Errors use FastAPI defaults:

```json
{
  "detail": "Human-readable error message"
}
```

Common status codes: `401` (auth), `403` (rare), `404`, `422` (validation), `500`, `503` (maintenance on list routes / cron misconfig).

---

## API categories

| Category | Doc | Prefix |
|----------|-----|--------|
| Auth | [Auth](auth.md) | `/api/auth/*` |
| Health & status | [Health & status](health-and-status.md) | `/api/health*`, `/api/status*` |
| Jobs & operations | [Jobs & operations](jobs-and-operations.md) | `/api/jobs*`, `/api/operations*` |
| Logs | [Logs](logs.md) | `/api/logs*`, `/logs/*` |
| Configuration | [Configuration](configuration.md) | `/api/config*`, `/api/models/*` |
| Repositories | [Repositories](repositories.md) | `/api/repositories*`, `/api/azure-devops/*` |
| Runners | [Runners](runners.md) | `/api/action-runner-connections*` |
| Notifications | [Notifications](notifications.md) | `/api/notifications/*` |
| Metrics | [Metrics](metrics.md) | `/api/metrics/*` |
| Admin & cron | [Admin & cron](admin-and-cron.md) | `/api/admin/*`, `/api/cron/*` |
| WebSocket | [WebSocket](websocket.md) | `/ws` |

Route registration lives in `dashboard/backend/main.py` (`_setup_routes()`). Dev routes under `/api/dev/*` register when `developer_mode=true`.

For when ingest calls fire in the PR pipeline (including code context and dev-time insights), see [Azure PR architecture](../azure-architecture/README.md). ROI aggregation: [Metrics](metrics.md).

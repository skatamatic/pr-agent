# Admin & Cron

Part of the [Dashboard API](README.md) reference.

Retention cleanup, database maintenance, and Cloud Scheduler hooks.

---

## Admin (JWT)

| Method | Path |
|--------|------|
| POST | `/api/admin/cleanup/preview` |
| POST | `/api/admin/cleanup/execute` |
| GET/POST | `/api/admin/retention/config` |
| GET | `/api/admin/database/stats` |
| POST | `/api/admin/database/cleanup` |
| POST/GET/DELETE | `/api/admin/database/backup`, `.../backups`, `.../backups/{filename}`, `.../backups/{filename}/restore` |
| GET/POST | `/api/admin/backup/directory` |
| POST | `/api/admin/database/export` |
| GET | `/api/admin/timezone/validate` |

### Cleanup preview / execute

Both require `cutoff_date` (ISO 8601). Optional `repository` filters to one repo. Execute also accepts `data_types` (default: `operations`, `jobs`, `logs`, `notification_events`).

```json
{
  "cutoff_date": "2025-01-01T00:00:00Z",
  "repository": "MyProject/my-repo",
  "data_types": ["jobs", "operations", "logs"]
}
```

Execute creates an automatic backup before deletion when configured.

See [Cleanup & retention how-to](../../how-to/cleanup-and-retention.md) for administrator guidance.

---

## Cron (secret)

| Method | Path | Notes |
|--------|------|-------|
| POST | `/api/cron/run-job-timeout` | Mark stale jobs failed |
| POST | `/api/cron/run-cleanup` | SQLite only; skipped on PostgreSQL |

Auth: `X-Cron-Secret: {DASHBOARD_CRON_SECRET}` or `Authorization: Bearer {DASHBOARD_CRON_SECRET}`. Returns **503** when the secret is not configured.

**Response example** (`run-job-timeout`):

```json
{
  "data": {
    "stale_found": 2,
    "stale_marked_failed": 2
  },
  "message": "Job timeout check completed"
}
```

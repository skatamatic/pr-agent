# Logs

Part of the [Dashboard API](README.md) reference.

Log query routes use the `/api` prefix. Ingest routes use `/logs/*` (no `/api`) for PR-Agent backward compatibility.

---

## GET `/api/logs`

Query: `limit`, `level`, `job_id`, `operation_id`, time range. Subject to maintenance mode.

---

## GET `/api/logs/job/{job_id}`

Logs for one job.

---

## GET `/api/logs/operation/{operation_id}`

Logs for one operation.

---

## POST `/logs/immediate`

No `/api` prefix. JWT or API key. Not blocked by maintenance mode.

```json
{
  "level": "INFO",
  "message": "Found .pr_agent.toml on branch master",
  "job_id": "job-abc123",
  "operation_id": "op-xyz",
  "timestamp": "2026-06-16T12:00:01Z",
  "source": "pr_agent"
}
```

---

## POST `/logs/batch`

```json
{
  "logs": [
    { "level": "INFO", "message": "...", "job_id": "...", "operation_id": "..." }
  ]
}
```

Body size capped by `DASHBOARD_MAX_LOG_INGEST_BODY_BYTES` (default 5MB). Entry count capped by `DASHBOARD_MAX_LOG_BATCH_ENTRIES` (default 1000).

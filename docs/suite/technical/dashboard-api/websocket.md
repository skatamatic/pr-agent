# WebSocket

Part of the [Dashboard API](README.md) reference.

Real-time updates for the React UI. Connect to `WS /ws`.

---

## Authentication

Connect with either:

- Header: `Authorization: Bearer {jwt_or_api_key}`
- Query: `?token=`, `?access_token=`, or `?api_key=`

Unauthenticated connections are closed with code 1008.

---

## Maintenance mode

When `maintenance_mode` is `"true"` in system settings:

- **503:** `GET /api/jobs`, `GET /api/operations`, `GET /api/logs`: list endpoints that depend on `check_maintenance_mode`
- **Still available:** `/api/health*`, `/api/status`, ingest routes, config, repos, and this WebSocket feed

PR-Agent keeps posting telemetry during maintenance; the UI shows a banner and list polling fails until maintenance is cleared.

---

## Event types

Subscribe by connecting to `/ws`. Incoming messages are JSON:

| type | When |
|------|------|
| `welcome` | Connected |
| `job_update` | Job created or status changed |
| `operation_update` | Operation created or updated |
| `log` | New log line |
| `metrics_update` | Metrics recalculated |
| `system_status` | System state change |
| `ping` | Keepalive (server sends every ~30s) |

Example payload:

```json
{
  "type": "job_update",
  "data": {
    "job_id": "job-abc123",
    "status": "running",
    "repository": "MyProject/my-repo"
  }
}
```

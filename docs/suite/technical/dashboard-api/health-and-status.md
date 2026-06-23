# Health & Status

Part of the [Dashboard API](README.md) reference.

Public health probes and authenticated system status for the UI.

---

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/api/health` | Public | Aggregate |
| GET | `/api/health/database` | Public | DB ping |
| GET | `/api/health/config` | Public | Can load GCS/local config |
| GET | `/api/health/context` | Public | Optional C# context service |
| GET | `/api/status` | Public | Simple alive check |
| GET | `/api/status/realtime` | JWT | Overview polling metrics |
| GET | `/api/system/alerts` | JWT | Active alerts |
| GET | `/api/system/performance` | JWT | Perf snapshot |
| GET | `/api/developer-mode` | JWT | Whether dev routes are registered |

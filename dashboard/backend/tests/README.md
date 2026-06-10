# Dashboard Backend Tests

Production-oriented test suite for the PR-Agent dashboard backend.

## Run tests

From the **dashboard/backend** directory:

```bash
python -m pytest tests/ -v
```

Or use the project test runner:

```bash
python run_tests.py
```

Tests use **in-memory SQLite** (`DATABASE_URL=sqlite:///:memory:` set in `conftest.py`), so no real database is modified.

## Coverage

Run from **dashboard/backend** so the `services` package resolves. Use **dotted** module names (not path-style `services/...`):

```bash
python -m pytest tests/ --cov=services --cov-report=term-missing
```

To narrow to the robust cache package:

```bash
python -m pytest tests/test_robust_cache_repository_contract.py --cov=services.robust_cache_service --cov-report=term-missing
```

## Coverage by area

| Area | Files | What's tested |
|------|--------|----------------|
| **Health & status** | test_health_api | `/api/health`, `/api/health/database`, config, context, `/api/status`, developer-mode, debug paths |
| **Auth** | test_auth_api | Login (success, invalid user/password), verify (no token, invalid token, valid token), change-password |
| **Cron (GCP)** | test_cron_api | `/api/cron/run-cleanup`, `/api/cron/run-job-timeout` – 401 without/wrong secret, 200 with X-Cron-Secret or Bearer |
| **Operations & jobs** | test_operations_jobs_api | List jobs, get job 404, list operations (auth), get operation 404, job operations, POST jobs/create, job status, operations create, operation status, deletion preview, delete job |
| **Logs** | test_logs_api | GET logs (list, by job, by operation), POST `/logs/immediate`, POST `/logs/batch` |
| **Internal log ingest auth** | test_internal_log_ingest_headers | `internal_log_ingest_headers()` (Bearer when `DASHBOARD_API_KEY` set); POST `/logs/immediate` & `/logs/batch` with those headers |
| **Log batch / WS** | test_logs_batch_limits | `MAX_LOG_BATCH_ENTRIES`, single `logs_batch` WebSocket broadcast, empty batch, single-transaction batch insert |
| **Logs cache merge** | test_logs_cache_merge | Unique log ids after inserts; GET `/api/logs` with `search` / `offset` / `repository` |
| **Metrics** | test_metrics_api | Summary, config, recalculate, operations/repositories breakdown |
| **Config** | test_config_api, test_config | GET/POST config, pr-agent-path, validate path; CORS/port/database_url from env |
| **Models & discovery** | test_model_service, test_models_api | GET `/api/models/available`, POST `/api/models/test`, cache, auth, benchmark response shape |
| **Repositories** | test_repositories_api | List, names, create (minimal), get 404, health |
| **Admin** | test_admin_api | Retention config, database stats |
| **System** | test_system_api | Status realtime, alerts, performance |
| **Notifications** | test_notifications_api | GET notification configs (200 or 500 if table missing) |
| **Cleanup** | test_cleanup_api, test_data_cleanup_service | Admin cleanup preview/execute, service logic |
| **Job deletion** | test_job_deletion_api, test_job_deletion_service | Deletion preview, delete job, service logic |
| **Retention** | test_retention_service | Non-SQLite cleanup/backup skip; retention config |
| **WebSocket** | test_websocket_manager | Connect, disconnect, broadcast, connection count |
| **System settings** | test_system_settings_service | get/set/delete/get_all settings, pr-agent path get/set/validate, effective path, validation (path exists, not dir, settings dir, config file, valid) |
| **Notification service** | test_notification_service | load_configurations, _should_send (TEST, event types, repo filter), _get_event_details, _format_duration, send_notification (mocked), get/save config |
| **Config service** | test_config_service | refresh_paths, validate_current_path, is_path_valid, get_config, get_config_schema |
| **Repository service** | test_repository_service | get_repositories, create_repository, get_repository, duplicate raises, get_repository_names |
| **Health service** | test_health_service | _get_health_config_summary, _log_health_service_startup/shutdown |
| **Operation service** | test_operation_service | get_operations, get_operation (404), update_operation_status (no-op paths) |
| **Database** | test_database_manager | get_system_setting, set_system_setting, overwrite |
| **Timezone** | test_timezone_utils | utcnow_aware, ensure_timezone_aware/naive, safe_datetime_compare, parse_datetime_safe, get_cutoff_datetime, format_datetime_for_db, get_minutes_since, to_utc_iso |

## API conventions

- **Owner/repo string** (e.g. `org/name`) is always the field **`repository`** on jobs, operations, logs, and related JSON/query parameters (no `repo` alias).

## Repository field contract (unit)

- [`test_robust_cache_repository_contract.py`](test_robust_cache_repository_contract.py) — log ingest strips legacy `repo`, serializers expose `repository` only (mocked DB); `_get_logs_from_cache` filters by `repository` (in-memory LRU only).

## Robust cache service (unit / integration)

- [`test_robust_cache_service_comprehensive.py`](test_robust_cache_service_comprehensive.py) — `CacheEntry` / `LRUCache`, `AsyncPersistenceQueue` helpers, enqueue + flush, full `RobustCacheService` cache-through paths (jobs, operations, logs), DB error paths (mocked), cleanup + memory pressure, optional SQLite round-trips via `ensure_db_schema` (`create_log`, `create_logs_batch`, job insert).

```bash
python -m pytest tests/test_robust_cache_service_comprehensive.py --cov=services.robust_cache_service --cov-report=term-missing
```

## Fixtures (conftest.py)

- **client_app**: `TestClient(main.app)` with in-memory DB.
- **test_db**, **mock_database_manager**, **mock_metrics_service**, **mock_retention_service**: For service-level tests.
- **populated_test_db**, **old_data_db**: Preloaded data for cleanup/deletion tests.

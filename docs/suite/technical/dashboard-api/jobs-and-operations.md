# Jobs & Operations

Part of the [Dashboard API](README.md) reference.

Telemetry for PR-Agent Azure DevOps pipeline runs. Read routes require JWT. Write routes accept JWT **or** API key.

ADO pipeline jobs use `source=azuredevops_pipeline`. The `job_type` field in examples is a required API enum value for these runs.

When `maintenance_mode` is `"true"`, `GET /api/jobs`, `GET /api/operations`, and `GET /api/logs` return **503**. Ingest routes (`POST /api/jobs/create`, status updates, etc.) stay available.

---

## GET `/api/jobs`

Query: `limit`, `include_operations`, `status`, `job_type`, `repository`, `ensure_counts`. Subject to maintenance mode.

**Response `200`**

```json
{
  "data": [
    {
      "job_id": "job-abc123",
      "job_type": "webhook",
      "source": "azuredevops_pipeline",
      "status": "completed",
      "repository": "MyProject/my-repo",
      "pr_url": "https://dev.azure.com/.../pullrequest/42",
      "started_at": "...",
      "completed_at": "...",
      "duration": 87.5,
      "operations_count": 3,
      "completed_operations": 3,
      "failed_operations": 0
    }
  ],
  "total": 1
}
```

---

## GET `/api/jobs/{job_id}`

Query: `include_operations` (default `true`). Not blocked by maintenance mode.

---

## GET `/api/jobs/{job_id}/operations`

Operations for one job.

---

## POST `/api/jobs/create`

Used by PR-Agent (`dashboard_client.create_job`). Not blocked by maintenance mode.

**Request** (either form)

Minimal:

```json
{
  "job_type": "webhook",
  "source": "azuredevops_pipeline",
  "repository": "MyProject/my-repo",
  "pr_url": "https://dev.azure.com/org/project/_git/repo/pullrequest/42",
  "trigger_event": "pullrequest"
}
```

With explicit ID (preferred for idempotent telemetry):

```json
{
  "job_id": "job-uuid-from-agent",
  "job_type": "webhook",
  "source": "azuredevops_pipeline",
  "repository": "MyProject/my-repo",
  "pr_url": "https://dev.azure.com/...",
  "trigger_event": "pullrequest",
  "started_at": "2026-06-16T12:00:00Z",
  "pr_number": 42,
  "pr_title": "Add feature X"
}
```

**Response `200`**

```json
{
  "data": { "job_id": "job-abc123" },
  "message": "Job created successfully"
}
```

Broadcasts WebSocket `job_update` (see [WebSocket](websocket.md)).

---

## POST `/api/jobs/{job_id}/status`

**Request**

```json
{
  "status": "completed",
  "result_summary": { "tools_run": ["describe", "review"], "failures": [] },
  "error_details": null,
  "completed_at": "2026-06-16T12:01:30Z"
}
```

Status strings are normalized (`success` → `completed`, `error` → `failed`, etc.).

Valid terminal statuses: `completed`, `failed`, `cancelled`, `skipped`.

---

## GET `/api/operations`

Query: `limit`, `status`, `repository`. Subject to maintenance mode.

---

## GET `/api/operations/{operation_id}`

Single operation record.

---

## POST `/api/operations/create`

**Request**

```json
{
  "operation_id": "op-uuid",
  "job_id": "job-abc123",
  "operation_type": "review",
  "command": "/review",
  "repository": "MyProject/my-repo",
  "pr_url": "https://dev.azure.com/..."
}
```

**Response:** `{ "data": { "operation_id": "..." } }`

---

## POST `/api/operations/{operation_id}/status`

**Request**

```json
{
  "status": "completed",
  "current_step": "Publishing",
  "result_data": { },
  "error_details": null
}
```

Operation statuses include `starting`, `processing`, `fetching_context`, `generating`, `completed`, `failed`, `skipped`, and others. See `OperationStatus` in `dashboard/backend/models.py`.

---

## POST `/api/operations/{operation_id}/ai-metrics`

Single-model token usage.

```json
{
  "model_used": "anthropic/claude-sonnet-4-6-20260205",
  "input_tokens": 12000,
  "output_tokens": 800,
  "estimated_dev_hours_saved": 0.5
}
```

---

## POST `/api/operations/{operation_id}/multi-model-ai-metrics`

```json
{
  "models_data": {
    "anthropic/claude-sonnet-4-6-20260205": { "input_tokens": 10000, "output_tokens": 600 },
    "gpt-5.3-codex-spark": { "input_tokens": 2000, "output_tokens": 200 }
  },
  "estimated_dev_hours_saved": 0.5
}
```

Use one metrics endpoint per logical update, not both.

---

## POST `/api/operations/{operation_id}/step`

Progress log line tied to an operation.

```json
{
  "step": "Generating review",
  "details": "Calling model...",
  "timestamp": "2026-06-16T12:00:45Z"
}
```

---

## GET / PUT `/api/operations/{operation_id}/insights`

Structured **dev-time analysis** and optional self-reflection data. PR-Agent writes this after the primary tool completes and `DevTimeEstimator` returns category breakdowns (reviewer time saved, context-switch time, suggestion value, etc.). The Jobs UI **Operation Insights** panel reads this payload.

**PUT body:**

```json
{
  "insights": {
    "dev_time_analysis": {
      "final_assessment": { "total_developer_hours_saved": 2.5 },
      "change_complexity_assessment": { },
      "description_quality_assessment": { }
    },
    "dev_time_estimation": { "hours": 2.5, "confidence": "medium" }
  }
}
```

Shape varies by operation type (describe vs review vs improve). Hours also surface on the operation row via `estimated_dev_hours_saved` from the ai-metrics POST.

See [Metrics](metrics.md) for aggregation and ROI config.

---

## DELETE `/api/jobs/{job_id}`

JWT only. Preview first via `GET /api/jobs/{job_id}/deletion-preview`.

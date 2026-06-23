# Code context and time estimation

## Code context service

Enriches prompts with repository structure and dependency context beyond the PR diff.

| Piece | Location |
|-------|----------|
| Entry | `get_pr_context()` in `pr_agent/algo/pr_processing.py` |
| HTTP client | `pr_agent/algo/csharp_context_client.py` |
| Settings | `[csharp_code_context_service]` in GCS overlay |
| GCS files | `csharp_code_context.config.toml`, `csharp_code_context.secrets.toml` |

**Flow:**

1. Tool builds diff and language groups.
2. If `enabled` and any changed file ends with `.cs`, client calls `POST /api/analyze` with ADO PAT.
3. Response `mergedResults` is JSON-serialized into the prompt.
4. Results cached in-process per PR.

Operation status may show **`fetching_context`**. Failures log and continue without context.

Dashboard: `GET /api/health/context`, `POST /api/config/test-context-service`.

## Developer time estimation

After describe/review/improve, estimates developer hours saved for dashboard ROI.

| Piece | Location |
|-------|----------|
| Service | `pr_agent/algo/dev_time_estimator.py` |
| Prompts | `pr_agent/settings/pr_dev_time_estimation_prompts.toml` |
| Config | `[pr_dev_time_estimation].model` optional override |

**Flow:**

1. Primary tool completes; diff + AI output passed to `DevTimeEstimator`.
2. Second LLM call returns category breakdown (reviewer time, context switching, etc.).
3. Posts `estimated_dev_hours_saved` via `POST /api/operations/{id}/ai-metrics`.
4. Structured result in `PUT /api/operations/{id}/insights` (`dev_time_analysis`).

Hours capped per tool (typically ±16h). Dashboard **Metrics** aggregates hours × rate × multiplier minus token cost.

See [Reading metrics and ROI](../../how-to/reading-metrics-and-roi.md) and [Metrics API](../dashboard-api/metrics.md).

# Shared Config Storage: Env-Based Path / Volume

## Problem

The dashboard’s config editor and PR-Agent need to use the **same** config files. Today the dashboard uses a path derived from its install (and optionally from DB); PR-Agent uses paths relative to its package. In cloud deployments they don’t share a filesystem, so edits in the dashboard don’t affect PR-Agent.

## Design: One Env Pointing to a Volume (Local or GCS)

**No database for config paths.** Both dashboard and PR-Agent get the config location from **environment variables** only. You point them at the same place (a local directory or a GCS bucket+prefix), and they stay in sync.

- **Local:** Set `PR_AGENT_CONFIG_PATH` to a directory path that contains the config files (e.g. a mounted volume or a shared folder). Both dashboard and PR-Agent read/write that path.
- **GCS:** Set `PR_AGENT_CONFIG_GCS_BUCKET` (and optionally `PR_AGENT_CONFIG_GCS_PREFIX`). Both dashboard and PR-Agent use that bucket/prefix; dashboard writes TOML objects there, PR-Agent downloads them at startup and uses them as overlay.

Same env names for both sides so “dashboard and pr_agent can point to the same thing.”

## Env Vars (single source; no DB)

| Env | Used by | Meaning |
|-----|---------|---------|
| `PR_AGENT_CONFIG_PATH` | Dashboard, PR-Agent | **Local path** to a directory containing config files (`configuration.toml`, `secrets.toml`, etc.). If set, both use this; no DB, no “effective path” logic. |
| `PR_AGENT_CONFIG_GCS_BUCKET` | Dashboard, PR-Agent | **GCS bucket** name. If set, config is read/written in GCS (dashboard writes here; PR-Agent downloads from here at startup). |
| `PR_AGENT_CONFIG_GCS_PREFIX` | Dashboard, PR-Agent | **Object prefix** in the bucket (e.g. `pr-agent-config/`). Optional. |

- If **both** `PR_AGENT_CONFIG_PATH` and GCS vars are set, **local path wins** (so you can override in dev).
- If **neither** is set: dashboard falls back to default (repo root / `pr_agent/settings`); PR-Agent uses package-relative paths as today (no shared config).

## File layout

- **Local:** `PR_AGENT_CONFIG_PATH` is the directory that contains:
  - `configuration.toml`
  - `.secrets.toml` (or `secrets.toml` if we standardize)
  - `csharp_code_context.config.toml`, `csharp_code_context.secrets.toml`, `ignore.toml` (optional)
- **GCS:** Objects under the prefix with the same filenames (e.g. `configuration.toml`, `secrets.toml`, …).

## Deployment

- **GCP (Terraform):** The Terraform in `terraform/gcp` creates a GCS bucket for config, uploads seed `configuration.toml` and `secrets.toml`, and sets `PR_AGENT_CONFIG_GCS_BUCKET` and `PR_AGENT_CONFIG_GCS_PREFIX` on the dashboard backend. So after `terraform apply`, the dashboard uses GCS automatically. Set the **same** env vars on any PR-Agent deployment (Cloud Run job, pipeline, VM) so it loads the same config. Run `./scripts/deploy-gcp.sh`; it prints the bucket and prefix to set for PR-Agent.
- **Cloud Run (dashboard + PR-Agent):** Set `PR_AGENT_CONFIG_GCS_BUCKET` (and prefix) on both services; use the same bucket/prefix. No shared disk; GCS is the volume.
- **Self-hosted runner (VM):** Set GCS env in the PR-Agent container (`PR_AGENT_CONFIG_GCS_BUCKET`, `PR_AGENT_CONFIG_GCS_PREFIX`) so it pulls from GCS at startup; no DB, no local path.
- **Local dev:** Set `PR_AGENT_CONFIG_PATH` to a shared folder, or leave unset to use dashboard default and PR-Agent package defaults (no shared config).

## Implementation

- **Dashboard:** Resolve config location only from env (and default fallback). No DB for path. ConfigService uses `PR_AGENT_CONFIG_PATH` as the settings directory when set; when GCS env is set (and no local path), use a GCS backend.
- **PR-Agent:** If `PR_AGENT_CONFIG_PATH` is set, use that directory as the settings overlay (or primary). If GCS env is set, download config files from GCS into a temp/overlay dir and use that. Same env names as dashboard.
- **DB:** Remove config path from DB. The “PR-Agent path” UI can show the current source (from env or default) read-only, or be removed; no storing path in DB.

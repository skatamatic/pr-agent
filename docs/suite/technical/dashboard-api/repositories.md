# Repositories

Part of the [Dashboard API](README.md) reference.

Repository registration, Azure DevOps wizard, pipeline setup, and per-repo config files. JWT required unless noted.

---

## GET `/api/repositories`

List registered repos.

---

## POST `/api/repositories`

**Request** (`RepositoryCreate`)

```json
{
  "name": "MyProject/my-repo",
  "provider": "azure_devops",
  "url": "https://dev.azure.com/org/project/_git/my-repo",
  "is_active": true,
  "azure_pat": "your-pat",
  "config": {
    "auto_review": true,
    "auto_describe": true,
    "auto_improve": false,
    "monitor_prs": true
  }
}
```

PAT is stored in DB; never returned on GET.

---

## GET `/api/repositories/names` · GET `/api/repositories/health`

Name list and aggregate health summary.

---

## Azure DevOps wizard (unsaved repo)

| Method | Path | Body highlights |
|--------|------|-----------------|
| POST | `/api/azure-devops/discovery` | `{ "org_url", "pat" }` → projects/repos list |
| POST | `/api/azure-devops/pat-identity` | `{ "org_url", "pat", "repo_id?" }` |
| POST | `/api/azure-devops/branches` | `{ "org_url", "pat", "project", "repository" }` |
| POST | `/api/azure-devops/pipeline/setup` | `{ "org_url", "pat", "project", "repository", "branch", "policy_required", ... }` |

---

## Azure pipeline (saved repo)

| Method | Path |
|--------|------|
| GET/PUT | `/api/repositories/{id}/azure-pipeline-config` |
| GET | `.../sync-status`, `.../template`, `.../env-vars`, `.../installation-guide`, `.../check` |
| POST | `.../push`, `.../sync-variables`, `.../policies` |
| GET/POST/DELETE | `.../policies`, `.../policies/{policy_id}` |

---

## Per-repo files

| Method | Path |
|--------|------|
| GET/PUT | `/api/repositories/{id}/pr-agent-config` |
| GET/PUT | `/api/repositories/{id}/best-practices` |
| GET | `/api/repositories/{id}/effective-config` |
| POST | `.../pr-agent-config/check-pr-status`, `.../best-practices/check-pr-status` |

PUT bodies are typically `{ "content": "...toml or markdown..." }`.

---

## Other repo utilities

| Method | Path | Notes |
|--------|------|-------|
| GET/PUT/DELETE | `/api/repositories/{id}` | CRUD |
| GET | `.../detailed-status` | Extended status |
| GET | `.../branches` | Branch list (saved credentials) |
| POST | `.../check-health`, `.../check-config`, `.../test-token` | Validation |
| POST | `.../azure-cleanup` | Remove Azure pipeline artifacts |
| POST/GET | `.../cleanup/*`, `.../activation-sync/*` | Async cleanup / activation |
| GET/POST/PUT | `.../runner-service/*`, `.../azure-agent-service/*` | Self-hosted runner services |
| GET | `/api/system/runner-services` | All runner services |
| POST | `/api/repositories/update-configs` | Bulk config push |

---

## GET `/api/repositories/permissions-guide`

Public. Returns **GitHub** token scope guidance. For Azure DevOps PAT scopes, see [Adding an Azure DevOps repository](../../how-to/onboarding/README.md).

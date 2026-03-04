# Deployment scripts and Terraform – quality and accuracy review

Review of `terraform/gcp/`, `scripts/deploy-gcp.*`, and `scripts/build-push-gcp.*`.

---

## Summary

| Area | Verdict | Notes |
|------|---------|--------|
| **Terraform correctness** | Good | One fix: DB password in URL should avoid special chars. |
| **Terraform structure** | Good | Clear modules, dependencies, conditionals. |
| **Scripts (deploy)** | Good | One fix: treat `null` frontend_url as empty. |
| **Scripts (build-push)** | Good | Repo ID matches Terraform when prefix is default. |
| **Docs / README** | Good | Small cleanup: duplicate rows, init note for GCS. |

---

## Terraform

### Correct

- **APIs**: All required APIs enabled (Run, SQL Admin, Secret Manager, Scheduler, Artifact Registry, Compute, Service Networking, VPC Access) with `depends_on` where needed.
- **VPC**: Custom network, global address for peering, `google_service_networking_connection` with `deletion_policy = "ABANDON"` (avoids destroy failures). Connector uses `network = vpc.name` and dedicated `/28` CIDR.
- **Cloud SQL**: Private IP only, `depends_on` service networking. `connection_name` and Unix-socket `DATABASE_URL` format are correct for Cloud Run + proxy.
- **Secrets**: Stored in Secret Manager; IAM grants Cloud Run default SA `secretAccessor`; `version = "latest"` is valid.
- **Cloud Run**: Backend has VPC access (`PRIVATE_RANGES_ONLY`), Cloud SQL volume, secret refs, dynamic env for base URLs. Frontend is minimal. PORT 8080 matches Cloud Run and backend config (reads `PORT` env).
- **Scheduler**: POST to `/api/cron/run-job-timeout` with `X-Cron-Secret`; no OIDC needed when service allows unauthenticated.
- **Outputs**: Use `local.backend_image_set` / `frontend_image_set` so no index-out-of-range when count is 0.
- **Variables**: Sensible defaults; URL-injection vars documented as script-set.

### Fix applied

- **DB password in DATABASE_URL**: `random_password` with `special = true` can produce `@`, `#`, `?`, etc., which break PostgreSQL URLs. Set `special = false` for the DB password so the connection string stays valid without encoding.

### Optional / regional

- **VPC connector subnet**: With `auto_create_subnetworks = false` and no explicit subnet, the connector’s `ip_cidr_range` may create an implicit subnet; this is region-dependent. If you see “no space in network” type errors, add an explicit `google_compute_subnetwork` for the connector’s range and reference it if the provider supports it.
- **Deletion protection**: Cloud SQL has `deletion_protection = false` for easy destroy; set to `true` in production.

---

## Deploy scripts

### deploy-gcp.ps1 / deploy-gcp.sh

- **Flow**: First apply → read `backend_url` / `frontend_url` → second apply with `-var=backend_base_url=...` and `-var=frontend_base_url=...` is correct.
- **When backend is not deployed**: Output is `null` (string); script skips second apply and prints guidance. Good.
- **Fix applied**: When backend is deployed but frontend is not, `terraform output -raw frontend_url` returns the string `"null"`. Passing that as `frontend_base_url` would set the backend env to the literal `"null"`. Both scripts now treat `"null"` or empty frontend URL as empty string so CORS and base URL stay correct.

### build-push-gcp.ps1 / build-push-gcp.sh

- **Repo ID**: Scripts use `pr-agent-dash-repo`; Terraform uses `"${var.prefix}-repo"` (default `pr-agent-dash-repo`). Match when prefix is default.
- **Backend URL for frontend**: Placeholder when unset; WS URL derived from backend URL (https → wss, append `/ws`) is correct.
- **Working directory**: Both switch to repo root and build from there; Dockerfiles expect repo root. Correct.

---

## Backend state (GCS)

- **backend.tf.example**: Copy to `backend.tf` and set `bucket` (and optionally `prefix`). Terraform merges multiple `terraform {}` blocks, so this plus `main.tf` is valid.
- **Doc note**: After adding `backend.tf`, run `terraform init -reconfigure` (or `-migrate-state` if moving existing state). README and `backend.tf.example` comment updated to mention this.

---

## README / docs

- **Duplicate variable rows**: Variables table listed `backend_base_url` and `frontend_base_url` twice; duplicates removed.
- **Deploy script path**: README says “from repo root” and uses `./scripts/deploy-gcp.ps1`; on Windows the user may run `.\scripts\deploy-gcp.ps1`; both are fine (noted in review only).

---

## Checklist (post-review)

- [x] DB password safe for connection string (special = false).
- [x] Deploy scripts treat null frontend_url as empty.
- [x] README variable table de-duplicated.
- [x] GCS backend init note (reconfigure / migrate-state) added.

# CI/CD for PR-Agent Dashboard on GCP

This document covers:

1. **Initial deploy** – “Set project ID, run script, get a working deployment.”
2. **Ongoing changes** – GitHub, Cloud Build, automatic deployment on push to protected branches (e.g. `main`, `dev`), migrations, and keeping self-hosted runners on the latest PR-Agent images.

---

**Quick reference:** First time → `./scripts/full-deploy-gcp.sh -auto-approve` (or PowerShell). To redeploy **everything** (dashboard + PR-Agent image for runner VMs) from latest code → `./scripts/redeploy-gcp.sh -auto-approve` (or `.\scripts\redeploy-gcp.ps1 -AutoApprove`).

---

## 1. Initial deployment: “Set project ID, wait, working deployment”

### Option A: Full one-shot script (recommended for first time)

From the **repository root**, with only `project_id` set (in `terraform/gcp/terraform.tfvars` or env):

```bash
# Copy tfvars and set project_id (and optionally region)
cp terraform/gcp/terraform.tfvars.example terraform/gcp/terraform.tfvars
# Edit: project_id = "your-gcp-project"

export PROJECT_ID=your-gcp-project
./scripts/full-deploy-gcp.sh -auto-approve
```

What the script does:

1. **Terraform init** and **apply** (infra only: VPC, Cloud SQL, Secret Manager, Artifact Registry, GCS config).
2. **Build and push** backend image to Artifact Registry.
3. **Terraform apply** with `backend_image` (deploys backend Cloud Run).
4. **Build and push** frontend image (with `REACT_APP_API_URL` = backend URL from output).
5. **Terraform apply** with `frontend_image` and `backend_base_url` / `frontend_base_url` (deploys frontend and sets CORS/links).
6. **Optional**: wait for `GET /api/health` (up to 120s). Skip with `SKIP_HEALTH_WAIT=1`.
7. Prints **backend URL**, **frontend URL**, **DASHBOARD_API_KEY**, and config bucket.

Result: a working dashboard (backend + frontend on Cloud Run, DB, secrets, scheduler). You then set `DASHBOARD_API_KEY` in PR-Agent / pipelines and use “Provision runner VM” in the dashboard when adding repos.

### Option B: Single-script redeploy (after initial deploy)

After infra and first deploy exist, one script rebuilds and redeploys **everything** from latest code: PR-Agent image (for self-hosted runner VMs), dashboard backend, and dashboard frontend. All images go to the same GCP Artifact Registry; Terraform updates Cloud Run and passes the PR-Agent image URL so **new** runner VMs pre-pull it.

**PowerShell:** `.\scripts\redeploy-gcp.ps1 -AutoApprove -WaitForHealth`  
**Bash:** `./scripts/redeploy-gcp.sh -auto-approve`

Options: `-ProjectId` / `PROJECT_ID`, `-SkipPrAgentImage` / `SKIP_PR_AGENT_IMAGE=1` (dashboard only).  
**Note:** Existing runner VMs do not auto-update; new VMs get the latest image. Re-provision or `docker pull` on existing VMs to refresh.

### Option C: Manual steps (build → tfvars → deploy)

If you prefer to build images yourself and keep image URLs in `terraform.tfvars`:

1. Create `terraform/gcp/terraform.tfvars` with `project_id` (and optionally `region`, `prefix`).
2. `cd terraform/gcp && terraform init && terraform apply` (infra only).
3. From repo root: `PROJECT_ID=... ./scripts/build-push-gcp.sh` (backend only first time; use `BACKEND_URL` from Terraform output when building frontend).
4. Add `backend_image` and `frontend_image` to `terraform.tfvars`.
5. Run `./scripts/deploy-gcp.sh` (or `deploy-gcp.ps1`). Use `WAIT_FOR_HEALTH=1` (or `-WaitForHealth` in PowerShell) to wait for `/api/health` after apply.

---

## 2. Handling changes: CI/CD pipeline

### Goals

- **Non-destructive**: Terraform apply updates Cloud Run with new images; no unnecessary recreation of DB or secrets.
- **Migrations**: Dashboard backend runs `migrate_database()` on startup; no separate migration job required.
- **Protected branches**: Deploy only on push to `main` (or `dev`) so arbitrary branches don’t affect production.
- **Runner VM / PR-Agent image**: Newly provisioned runner VMs get the image set in `GCP_RUNNER_PR_AGENT_IMAGE`; existing VMs can be updated by re-pulling or re-provisioning (see below).

### Options for ongoing deploys

| Method | Trigger | Build | Deploy | Best for |
|--------|---------|--------|--------|----------|
| **Cloud Build** | Push to branch (e.g. `main`) or tag | Cloud Build builds and pushes images | Terraform apply (or Cloud Run update) | GCP-native; state in GCS |
| **GitHub Actions** | Push to `main` or workflow_dispatch | Build on GitHub or call Cloud Build | Terraform apply (needs GCP creds in secrets) | Single place for CI + CD |
| **Manual** | You run script | build-push-gcp.sh | deploy-gcp.sh | Small teams |

Recommended: **Cloud Build** for build + push; optionally **Cloud Build** or **GitHub Actions** for Terraform apply, with state in GCS and a service account with minimal permissions.

---

## 3. Cloud Build setup

### 3.1 Build and push (no Terraform)

- **Trigger**: Push to `main` (or `dev`), or tag `v*`.
- **Steps**:
  1. Build backend and frontend Docker images (frontend needs `REACT_APP_API_URL` / `REACT_APP_WS_URL`; use substitution or Secret Manager).
  2. Push to Artifact Registry with tag = `sha` or `latest`.
- **Result**: New images available; deploy either by a second Cloud Build step (Terraform or `gcloud run deploy`) or by a separate pipeline.

See **`cloudbuild.yaml`** in the repo root for a reference that:

- Builds backend and frontend.
- Pushes to `$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_ID/backend:$SHORT_SHA` (and frontend).
- Does **not** run Terraform (so you can run Terraform from a separate trigger or manually with the new image tags).

### 3.2 Deploy (Terraform apply)

- **Option A – Cloud Build step**: Add a step that runs `terraform init` (with GCS backend) and `terraform apply -auto-approve -var="backend_image=..." -var="frontend_image=..."` using the images built in the same run. Store Terraform state in GCS; use a service account with roles: `run.admin`, `sqladmin`, `secretmanager`, etc.
- **Option B – Separate trigger**: One trigger “build and push”; second trigger “deploy” that runs Terraform with image tags from the first (e.g. pass via Artifact Registry “latest” or a file).

### 3.3 Non-destructive behavior

- Terraform only updates the Cloud Run services’ image when `backend_image` / `frontend_image` change. Cloud SQL, secrets, and VPC are unchanged unless you change variables.
- Database migrations run inside the backend container on startup (`database.initialize_database()` → `migrate_database()`). No separate migration job; rolling out a new backend image is enough.

---

## 4. GitHub integration

### 4.1 Webhook / push event

- **Cloud Build trigger**: Connect the repo to Cloud Build; trigger on push to `main` (and optionally `dev`). No GitHub Actions needed for build if Cloud Build does it.
- **GitHub Actions**: To run Terraform from GitHub, store GCP credentials (e.g. workload identity or service account key) in GitHub Secrets and run `terraform apply` in a workflow on `push` to `main`. Prefer least-privilege and short-lived credentials.

### 4.2 Branch protection

- Protect `main` (and `dev` if you use it): require PR review, status checks (e.g. build-and-test). Only allow merges that pass; then Cloud Build or GitHub Actions deploys on push to `main`.

### 4.3 Reference workflow

- **`.github/workflows/deploy-gcp.yaml`** (in repo): Optionally runs on `push` to `main`, checks out code, builds images (or triggers Cloud Build), runs Terraform apply with new image tags, and optionally waits for health. Requires `GCP_PROJECT_ID`, `GCP_SA_KEY` (or workload identity) and optionally `BACKEND_URL` for frontend build.

---

## 5. Self-hosted runner and PR-Agent image

### 5.1 How runner VMs get the PR-Agent image

- **At provision time**: The dashboard (or Terraform) runs a startup script on the GCE VM. The script can **pre-pull** a Docker image when `GCP_RUNNER_PR_AGENT_IMAGE` (dashboard) or `pr_agent_runner_image` (Terraform) is set.
- **Recommendation**: Set `GCP_RUNNER_PR_AGENT_IMAGE` (e.g. `codiumai/pr-agent:0.23-github_action`) in the dashboard backend config (or Terraform variable). New VMs provisioned from the dashboard will then pre-pull that image.

### 5.2 Keeping existing runner VMs on the latest image

- **Option 1 – Re-provision**: Deprovision the runner VM and provision again; the new VM gets the current startup script and pre-pull image.
- **Option 2 – Pin in workflow**: In GitHub Actions, pin the image tag (e.g. `codiumai/pr-agent:0.23-github_action`). To roll forward, update the workflow to a new tag and merge to `main`; the next job pulls the new image (or use the pre-pulled one if the tag matches).
- **Option 3 – Periodic pull on VM**: Optional cron on the runner VM to `docker pull` the desired tag so the next job uses it. Not implemented by default; can be added to the startup script or a separate systemd timer.

For a **non-destructive** approach: use a **fixed tag** (e.g. `0.23-github_action`) in workflows and in `GCP_RUNNER_PR_AGENT_IMAGE`. When you want to roll forward, update the tag in config and in the workflow and (if desired) re-provision runner VMs so they pre-pull the new tag.

---

## 6. Resuming after a failure

- **Terraform** is idempotent: run `terraform apply -auto-approve` again; it will only create or update resources that are missing or changed. No need to “resume” manually; fix the error (e.g. fix config, delete a failed GCP resource if instructed) then re-apply.
- **full-deploy-gcp.sh**: Re-run the same script after fixing the issue. Terraform steps will skip existing resources; build/push and apply will continue from where they left off.
- **If only infra (no images) was applied**: Run build-push (backend, then frontend with backend URL), add image URLs to tfvars, then run `deploy-gcp.sh` (or `deploy-gcp.ps1`).
- **VPC Access Connector conflict**: If you see “Invalid IP CIDR range… conflicts with an existing subnetwork”, the Terraform config now uses the connector’s `subnet` block (existing subnet) instead of `ip_cidr_range` to avoid double-allocating the same range. If a failed connector exists in GCP, delete it: `gcloud compute networks vpc-access connectors delete CONNECTOR_NAME --region=REGION --project=PROJECT_ID`, then run `terraform apply` again.

## 7. Summary checklist

| Item | Initial deploy | Ongoing CI/CD |
|------|----------------|----------------|
| **Set project ID** | In `terraform.tfvars` or `PROJECT_ID` | Same project; Terraform state in GCS |
| **Build images** | `full-deploy-gcp.sh` or `build-push-gcp.sh` | Cloud Build or GitHub Actions |
| **Deploy** | `full-deploy-gcp.sh` or `deploy-gcp.sh` | Cloud Build step or GitHub Actions (Terraform apply) |
| **Migrations** | Automatic on backend startup | Automatic on each new backend deploy |
| **Health** | Optional wait in script | Optional wait in pipeline; alert on failure |
| **Runner image** | Set `GCP_RUNNER_PR_AGENT_IMAGE` for new VMs | Update tag in config + workflow; re-provision or pull on VMs |

---

## 8. Files reference

| File | Purpose |
|------|---------|
| `scripts/full-deploy-gcp.sh` / `full-deploy-gcp.ps1` | One-shot **initial** deploy: infra → backend → frontend → optional health wait. Does not set PR-Agent image; run **redeploy** once to set it, or set `pr_agent_runner_image` in tfvars. |
| `scripts/redeploy-gcp.sh` / `redeploy-gcp.ps1` | **Redeploy everything**: PR-Agent image + backend + frontend. Use after initial deploy for "latest code + latest runner image." |
| `scripts/deploy-gcp.sh` / `deploy-gcp.ps1` | Apply Terraform with existing image URLs; optional `WAIT_FOR_HEALTH` |
| `scripts/build-push-gcp.sh` / `build-push-gcp.ps1` | Build and push backend + frontend to Artifact Registry |
| `terraform/gcp/*` | Infra and Cloud Run; Terraform state can live in GCS for CI/CD |
| `cloudbuild.yaml` | Reference Cloud Build: build + push images (no Terraform in same file) |
| `.github/workflows/deploy-gcp.yaml` | Reference GitHub Actions: deploy on push to `main` (optional; requires `GCP_PROJECT_ID` and `GCP_SA_KEY` secrets) |

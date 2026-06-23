# Deployment on Google Cloud

PR-Agent and the Dashboard run on **Google Cloud Platform**. Step-by-step commands: `deployment.md` and `docs/GCP_DEPLOYMENT.md`.

## Live development stack

Current **dev** deployment (branch `develop`, Terraform prefix `pr-agent-dash-dev`):

| Resource | Name | Console |
|----------|------|---------|
| GCP project | `nex-ai-fracgpt-dev` | [Project dashboard](gcp://project) |
| Cloud Run (all) | `us-central1` | [Cloud Run](gcp://cloud-run) |
| Backend API | `pr-agent-dash-dev-backend` | [Backend service](gcp://cloud-run/backend) |
| Frontend | `pr-agent-dash-dev-frontend` | [Frontend service](gcp://cloud-run/frontend) |
| Cloud SQL | `pr-agent-dash-dev-sql` | [Cloud SQL](gcp://cloud-sql) |
| Config bucket | `nex-ai-fracgpt-dev-pr-agent-dash-dev-config` | [GCS config bucket](gcp://gcs/documents) |
| Artifact Registry | `pr-agent-dash-dev-repo` | [Artifact Registry](gcp://artifacts) |
| Secrets | `{prefix}-database-url`, `-api-key`, `-cron-secret` | [Secret Manager](gcp://secrets) |
| Terraform state | `nex-ai-fracgpt-dev-tfstate` | GCS backend (separate from config bucket) |

Terraform inputs: `terraform/gcp/terraform.tfvars` (`project_id`, `prefix`, `region`). Staging and production use prefixes `pr-agent-dash-stage` and `pr-agent-dash` on their respective projects when promoted via CI/CD.

## Pages in this section

| Page | Topics |
|------|--------|
| [Topology and GCP services](topology-and-services.md) | Dashboard stack, PR execution path, service roles |
| [Terraform and deploy scripts](terraform-and-images.md) | IaC, first-time deploy, container images, Cloud Build |
| [Config, Cloud Run, and operations](config-cloud-run-and-ops.md) | GCS config, Cloud Run limits, runners, post-deploy vars, CI/CD |

## First-time checklist

1. Copy and edit `terraform/gcp/terraform.tfvars`
2. Run `./scripts/full-deploy-gcp.sh -auto-approve`
3. Save `dashboard_api_key` from Terraform output immediately
4. Configure Azure DevOps pipeline variables: see [Config, Cloud Run, and operations](config-cloud-run-and-ops.md#post-deploy-azure-devops-pipeline-variables)
5. Open frontend URL → login → **AI Config** → set LLM keys
6. Add first repository: [Adding an Azure DevOps repository](../../how-to/onboarding/README.md)

**PR-Agent image build requires** `.dockerignore.pr-agent` in repo root.


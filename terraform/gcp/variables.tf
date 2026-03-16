# ------------------------------------------------------------------------------
# PR-Agent Dashboard + optional PR-Agent on GCP
# ------------------------------------------------------------------------------

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region (e.g. us-central1)"
  type        = string
  default     = "us-central1"
}

variable "prefix" {
  description = "Prefix for resource names (e.g. pr-agent-dash)"
  type        = string
  default     = "pr-agent-dash"
}

variable "restricted_permissions_mode" {
  description = "When true, skip IAM/policy management operations that often require elevated admin roles; intended for constrained deployers."
  type        = bool
  default     = false
}

# ------------------------------------------------------------------------------
# Cloud SQL
# ------------------------------------------------------------------------------

variable "db_tier" {
  description = "Cloud SQL machine tier (e.g. db-f1-micro, db-custom-1-3840)"
  type        = string
  default     = "db-f1-micro"
}

variable "db_name" {
  description = "Cloud SQL database name"
  type        = string
  default     = "dashboard_db"
}

variable "db_user_name" {
  description = "Cloud SQL user name"
  type        = string
  default     = "dashboard_user"
}

variable "db_user_password" {
  description = "Cloud SQL user password (leave empty to generate randomly)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "manage_sql_instance" {
  description = "Create/manage Cloud SQL instance via Terraform. Set false to reuse an existing instance."
  type        = bool
  default     = true
}

variable "existing_sql_instance_name" {
  description = "Existing Cloud SQL instance name to reuse when manage_sql_instance=false."
  type        = string
  default     = ""
}

variable "existing_sql_connection_name" {
  description = "Existing Cloud SQL connection name (PROJECT:REGION:INSTANCE) used when reusing an external SQL instance."
  type        = string
  default     = ""
}

# ------------------------------------------------------------------------------
# Images (set after building and pushing)
# ------------------------------------------------------------------------------

variable "backend_image" {
  description = "Full image URL for dashboard backend (e.g. us-central1-docker.pkg.dev/PROJECT/repo/backend:latest)"
  type        = string
  default     = ""
}

variable "frontend_image" {
  description = "Full image URL for dashboard frontend"
  type        = string
  default     = ""
}

# ------------------------------------------------------------------------------
# Secrets (create placeholders in Terraform; set values in Console or gcloud)
# ------------------------------------------------------------------------------

variable "cron_secret" {
  description = "DASHBOARD_CRON_SECRET for Cloud Scheduler (leave empty to generate)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "dashboard_api_key" {
  description = "DASHBOARD_API_KEY for PR-Agent Bearer auth. Leave empty to auto-generate (recommended for one-click deploy); deploy script prints it for use in PR-Agent / pipelines."
  type        = string
  default     = ""
  sensitive   = true
}

variable "manage_secret_manager_resources" {
  description = "Create Secret Manager secrets/versions and wire Cloud Run to read them."
  type        = bool
  default     = true
}

# ------------------------------------------------------------------------------
# Cloud Run
# ------------------------------------------------------------------------------

variable "backend_max_instances" {
  description = "Max instances for dashboard backend (1 recommended for WebSocket broadcast)"
  type        = number
  default     = 1
}

variable "backend_timeout_seconds" {
  description = "Request timeout for backend (seconds; 3600 for WebSockets)"
  type        = number
  default     = 3600
}

variable "allow_unauthenticated" {
  description = "Allow unauthenticated access to Cloud Run services"
  type        = bool
  default     = true
}

# ------------------------------------------------------------------------------
# Cloud Scheduler
# ------------------------------------------------------------------------------

variable "job_timeout_schedule" {
  description = "Cron schedule for run-job-timeout (e.g. \"*/10 * * * *\" every 10 min)"
  type        = string
  default     = "*/10 * * * *"
}

# ------------------------------------------------------------------------------
# VPC (private Cloud SQL + VPC connector for Cloud Run)
# ------------------------------------------------------------------------------

variable "vpc_connector_cidr" {
  description = "CIDR for Serverless VPC Access connector (/28); must not overlap with vpc_peering_cidr"
  type        = string
  default     = "10.8.0.0/28"
}

variable "existing_vpc_name" {
  description = "Existing VPC network name to reuse. When set with restricted_permissions_mode=true, Terraform skips creating network/peering."
  type        = string
  default     = ""
}

variable "existing_vpc_connector_id" {
  description = "Existing Serverless VPC Access connector full resource ID (projects/PROJECT/locations/REGION/connectors/NAME)."
  type        = string
  default     = ""
}

variable "vpc_peering_cidr_prefix" {
  description = "Prefix length for Private Service Access peering range (16 = /16)"
  type        = number
  default     = 16
}

# ------------------------------------------------------------------------------
# GCS config bucket (dashboard + PR-Agent share config here)
# ------------------------------------------------------------------------------

variable "config_bucket_name" {
  description = "GCS bucket for PR-Agent config (dashboard writes here; PR-Agent reads at startup). Empty = default to project_id-pr-agent-config"
  type        = string
  default     = ""
}


# ------------------------------------------------------------------------------
# URL injection (set by deploy script from Terraform outputs; rarely set by hand)
# ------------------------------------------------------------------------------

variable "backend_base_url" {
  description = "Dashboard backend public URL (deploy script sets from output backend_url)"
  type        = string
  default     = ""
}

variable "frontend_base_url" {
  description = "Dashboard frontend public URL (deploy script sets from output frontend_url)"
  type        = string
  default     = ""
}

# ------------------------------------------------------------------------------
# Optional: self-hosted action runner VM (Azure DevOps / GitHub Actions)
# ------------------------------------------------------------------------------

variable "enable_runner_vm" {
  description = "Create a single Compute Engine VM via Terraform (legacy). Prefer false and use dashboard 'Provision runner VM' to create runner VMs on demand per connection."
  type        = bool
  default     = false
}

variable "runner_machine_type" {
  description = "Machine type for runner VM (e.g. e2-medium)"
  type        = string
  default     = "e2-medium"
}

variable "runner_zone" {
  description = "Zone for runner VM (default: region + '-a')"
  type        = string
  default     = ""
}

variable "runner_subnet_cidr" {
  description = "CIDR for runner subnet (must not overlap with vpc_connector_cidr or vpc_peering)"
  type        = string
  default     = "10.0.1.0/24"
}

variable "pr_agent_repo_url" {
  description = "Git URL to clone PR-Agent on the runner VM"
  type        = string
  default     = "https://github.com/Codium-ai/pr-agent.git"
}

variable "pr_agent_runner_image" {
  description = "Optional Docker image to pre-pull on the runner VM. Use your Artifact Registry image (e.g. REGION-docker.pkg.dev/PROJECT/pr-agent-dash-repo/pr-agent:latest) or Docker Hub (e.g. codiumai/pr-agent:0.23-github_action). Empty = skip. Set automatically by scripts/redeploy-gcp.ps1 and redeploy-gcp.sh."
  type        = string
  default     = ""
}

variable "ado_org_url" {
  description = "Azure DevOps organization URL (e.g. https://dev.azure.com/myorg). When set with ado_pat and ado_pool, the runner VM auto-registers the ADO agent."
  type        = string
  default     = ""
}

variable "ado_pat" {
  description = "Azure DevOps PAT with Agent Pools (read, manage) scope. Used once for agent registration."
  type        = string
  default     = ""
  sensitive   = true
}

variable "ado_pool" {
  description = "Azure DevOps agent pool name (e.g. PRAgent_Cloud)."
  type        = string
  default     = ""
}

variable "ado_agent_name" {
  description = "Optional agent name. Defaults to the VM hostname if empty."
  type        = string
  default     = ""
}

variable "manage_runtime_iam_bindings" {
  description = "Manage runtime IAM bindings (project compute admin + Artifact Registry reader for runtime SA)."
  type        = bool
  default     = true
}

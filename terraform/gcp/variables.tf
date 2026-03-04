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

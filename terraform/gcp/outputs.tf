# ------------------------------------------------------------------------------
# Outputs – use backend_url and frontend_url for DASHBOARD_BACKEND_BASE_URL /
# DASHBOARD_FRONTEND_BASE_URL and for building the frontend with REACT_APP_API_URL.
# ------------------------------------------------------------------------------

output "project_id" {
  description = "GCP project ID"
  value       = var.project_id
}

output "region" {
  description = "GCP region"
  value       = var.region
}

output "cloud_sql_connection_name" {
  description = "Cloud SQL instance connection name (for DATABASE_URL and Cloud Run)"
  value       = local.connection_name
}

output "vpc_network_name" {
  description = "VPC network name (private Cloud SQL and connector)"
  value       = local.use_existing_vpc ? var.existing_vpc_name : google_compute_network.vpc[0].name
}

output "artifact_registry_repository" {
  description = "Artifact Registry repository (for docker push)"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.repository_id}"
}

output "backend_url" {
  description = "Dashboard backend Cloud Run URL (set as backend_base_url and use for REACT_APP_API_URL)"
  value       = local.backend_image_set ? google_cloud_run_v2_service.backend[0].uri : null
}

output "frontend_url" {
  description = "Dashboard frontend Cloud Run URL"
  value       = local.frontend_image_set ? google_cloud_run_v2_service.frontend[0].uri : null
}

output "cron_secret_for_scheduler" {
  description = "Generated DASHBOARD_CRON_SECRET (stored in Secret Manager; Scheduler uses it)"
  value       = local.cron_secret
  sensitive   = true
}

output "dashboard_api_key" {
  description = "DASHBOARD_API_KEY for PR-Agent Bearer auth (auto-generated if not in tfvars; set as env DASHBOARD_API_KEY in PR-Agent / pipelines)"
  value       = local.backend_image_set ? local.dashboard_api_key : null
  sensitive   = true
}

output "config_bucket" {
  description = "GCS bucket for PR-Agent config; set PR_AGENT_CONFIG_GCS_BUCKET and PR_AGENT_CONFIG_GCS_PREFIX on dashboard and PR-Agent so they share config"
  value       = google_storage_bucket.config.name
}

output "config_prefix" {
  description = "GCS object prefix for config (pr-agent-config/)"
  value       = local.config_prefix
}

output "runner_instance_name" {
  description = "Runner VM instance name (when enable_runner_vm = true)"
  value       = var.enable_runner_vm ? google_compute_instance.runner[0].name : null
}

output "runner_zone" {
  description = "Runner VM zone"
  value       = var.enable_runner_vm ? google_compute_instance.runner[0].zone : null
}

output "runner_env_path" {
  description = "Path on runner VM to env file (source this for DASHBOARD_URL, GCS config)"
  value       = "/opt/pr-agent-runner/env"
}

output "pr_agent_runner_image" {
  description = "PR-Agent Docker image URL passed to runner VMs and backend (for redeploy script when skipping PR-Agent build)"
  value       = var.pr_agent_runner_image != "" ? var.pr_agent_runner_image : null
}

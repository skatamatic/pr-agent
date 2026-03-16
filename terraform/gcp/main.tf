# ------------------------------------------------------------------------------
# PR-Agent Dashboard on GCP – Terraform
# See deployment.md and docs/GCP_DEPLOYMENT.md for architecture.
# ------------------------------------------------------------------------------

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ------------------------------------------------------------------------------
# APIs
# ------------------------------------------------------------------------------

resource "google_project_service" "run" {
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "sqladmin" {
  service            = "sqladmin.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "secretmanager" {
  service            = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "scheduler" {
  service            = "cloudscheduler.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "artifactregistry" {
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "compute" {
  service            = "compute.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "servicenetworking" {
  service            = "servicenetworking.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "vpcaccess" {
  service            = "vpcaccess.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "storage" {
  service            = "storage.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudbuild" {
  service            = "cloudbuild.googleapis.com"
  disable_on_destroy = false
}

# ------------------------------------------------------------------------------
# GCS bucket for shared PR-Agent config (dashboard + PR-Agent point here)
# ------------------------------------------------------------------------------

resource "google_storage_bucket" "config" {
  name                        = var.config_bucket_name != "" ? var.config_bucket_name : "${var.project_id}-${var.prefix}-config"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true # Allow terraform destroy to delete bucket and contents (teardown)

  depends_on = [google_project_service.storage]
}

resource "google_storage_bucket_iam_member" "config_backend" {
  count  = local.backend_image_set ? 1 : 0
  bucket = google_storage_bucket.config.name
  role   = "roles/storage.objectAdmin"
  member = local.cloud_run_sa
}

# Runner VM needs GCS config access when backend is not deployed (backend uses same SA when set)
resource "google_storage_bucket_iam_member" "config_runner" {
  count  = var.enable_runner_vm && !local.backend_image_set ? 1 : 0
  bucket = google_storage_bucket.config.name
  role   = "roles/storage.objectAdmin"
  member = local.cloud_run_sa
}

locals {
  config_prefix          = "pr-agent-config/"
  use_existing_vpc       = var.restricted_permissions_mode && var.existing_vpc_name != ""
  use_existing_connector = var.restricted_permissions_mode && var.existing_vpc_connector_id != ""
  use_secret_manager     = var.manage_secret_manager_resources && !var.restricted_permissions_mode
  manage_runtime_iam     = var.manage_runtime_iam_bindings && !var.restricted_permissions_mode
}

resource "google_storage_bucket_object" "config_seed_configuration" {
  name    = "${local.config_prefix}configuration.toml"
  bucket  = google_storage_bucket.config.name
  content = file("${path.module}/config-seed/configuration.toml")

  lifecycle {
    ignore_changes = [content, detect_md5hash]
  }
}

resource "google_storage_bucket_object" "config_seed_secrets" {
  name    = "${local.config_prefix}secrets.toml"
  bucket  = google_storage_bucket.config.name
  content = file("${path.module}/config-seed/secrets.toml")

  lifecycle {
    ignore_changes = [content, detect_md5hash]
  }
}

# ------------------------------------------------------------------------------
# VPC (private Cloud SQL + VPC connector for Cloud Run)
# ------------------------------------------------------------------------------

resource "google_compute_network" "vpc" {
  count                   = local.use_existing_vpc ? 0 : 1
  name                    = "${var.prefix}-vpc"
  auto_create_subnetworks = false
  routing_mode            = "GLOBAL"
  depends_on              = [google_project_service.compute]
}

# Subnet for Serverless VPC Access connector (required when auto_create_subnetworks = false)
resource "google_compute_subnetwork" "connector" {
  count         = local.use_existing_vpc ? 0 : 1
  name          = "${var.prefix}-connector-subnet"
  ip_cidr_range = var.vpc_connector_cidr
  region        = var.region
  network       = google_compute_network.vpc[0].id
}

# Subnet for runner VM (and other compute in VPC)
resource "google_compute_subnetwork" "runner" {
  count         = var.enable_runner_vm && !local.use_existing_vpc ? 1 : 0
  name          = "${var.prefix}-runner-subnet"
  ip_cidr_range = var.runner_subnet_cidr
  region        = var.region
  network       = google_compute_network.vpc[0].id
}

resource "google_compute_global_address" "private_ip_range" {
  count         = local.use_existing_vpc ? 0 : 1
  name          = "${var.prefix}-private-ip-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = var.vpc_peering_cidr_prefix
  network       = google_compute_network.vpc[0].id
}

resource "google_service_networking_connection" "private_vpc" {
  count                   = local.use_existing_vpc ? 0 : 1
  network                 = google_compute_network.vpc[0].id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_range[0].name]
  deletion_policy         = "ABANDON"
  depends_on              = [google_project_service.servicenetworking]
}

# Use existing connector subnet (do not use ip_cidr_range here - that would create a second
# allocation and conflict with google_compute_subnetwork.connector).
resource "google_vpc_access_connector" "connector" {
  count  = local.use_existing_connector ? 0 : 1
  name   = "${var.prefix}-conn"
  region = var.region
  subnet {
    name = google_compute_subnetwork.connector[0].name
  }
  depends_on = [google_project_service.vpcaccess, google_compute_subnetwork.connector]
}

# ------------------------------------------------------------------------------
# Passwords / secrets (random if not provided)
# ------------------------------------------------------------------------------

resource "random_password" "db_password" {
  length  = 24
  special = false # avoid URL-unsafe chars in DATABASE_URL (e.g. @, ?, #)
}

resource "random_password" "cron_secret" {
  length  = 32
  special = false
}

resource "random_password" "dashboard_api_key" {
  length  = 32
  special = false
}

locals {
  db_password       = coalesce(var.db_user_password, random_password.db_password.result)
  cron_secret       = coalesce(var.cron_secret, random_password.cron_secret.result)
  dashboard_api_key = coalesce(var.dashboard_api_key, random_password.dashboard_api_key.result)
  instance_name     = var.manage_sql_instance ? "${var.prefix}-sql" : var.existing_sql_instance_name
  connection_name   = var.existing_sql_connection_name != "" ? var.existing_sql_connection_name : "${var.project_id}:${var.region}:${local.instance_name}"
  sql_instance_name = var.manage_sql_instance ? google_sql_database_instance.main[0].name : var.existing_sql_instance_name
  network_self_link = local.use_existing_vpc ? "projects/${var.project_id}/global/networks/${var.existing_vpc_name}" : google_compute_network.vpc[0].id
  vpc_connector_id  = local.use_existing_connector ? var.existing_vpc_connector_id : google_vpc_access_connector.connector[0].id
  database_url      = "postgresql://${var.db_user_name}:${local.db_password}@/${var.db_name}?host=/cloudsql/${local.connection_name}"
}

# ------------------------------------------------------------------------------
# Cloud SQL
# ------------------------------------------------------------------------------

resource "google_sql_database_instance" "main" {
  count            = var.manage_sql_instance ? 1 : 0
  name             = local.instance_name
  database_version = "POSTGRES_15"
  region           = var.region

  settings {
    tier = var.db_tier
    ip_configuration {
      ipv4_enabled    = false
      private_network = local.network_self_link
    }
  }

  deletion_protection = false

  depends_on = [
    google_project_service.sqladmin,
    google_service_networking_connection.private_vpc,
  ]
}

resource "google_sql_database" "db" {
  name     = var.db_name
  instance = local.sql_instance_name
}

resource "google_sql_user" "user" {
  name     = var.db_user_name
  instance = local.sql_instance_name
  password = local.db_password
}

# ------------------------------------------------------------------------------
# Secret Manager
# ------------------------------------------------------------------------------

resource "google_secret_manager_secret" "database_url" {
  count     = local.use_secret_manager ? 1 : 0
  secret_id = "${var.prefix}-database-url"

  replication {
    auto {}
  }
  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret_version" "database_url" {
  count       = local.use_secret_manager ? 1 : 0
  secret      = google_secret_manager_secret.database_url[0].id
  secret_data = local.database_url
}

resource "google_secret_manager_secret" "cron_secret" {
  count     = local.use_secret_manager ? 1 : 0
  secret_id = "${var.prefix}-cron-secret"

  replication {
    auto {}
  }
  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret_version" "cron_secret" {
  count       = local.use_secret_manager ? 1 : 0
  secret      = google_secret_manager_secret.cron_secret[0].id
  secret_data = local.cron_secret
}

# DASHBOARD_API_KEY for PR-Agent / programmatic access (auto-generated if not provided)
resource "google_secret_manager_secret" "dashboard_api_key" {
  count     = local.backend_image_set && local.use_secret_manager ? 1 : 0
  secret_id = "${var.prefix}-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret_version" "dashboard_api_key" {
  count       = local.backend_image_set && local.use_secret_manager ? 1 : 0
  secret      = google_secret_manager_secret.dashboard_api_key[0].id
  secret_data = local.dashboard_api_key
}

resource "google_secret_manager_secret_iam_member" "dashboard_api_key_access" {
  count     = local.backend_image_set && local.use_secret_manager ? 1 : 0
  secret_id = google_secret_manager_secret.dashboard_api_key[0].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = local.cloud_run_sa
}

# ------------------------------------------------------------------------------
# Artifact Registry
# ------------------------------------------------------------------------------

resource "google_artifact_registry_repository" "repo" {
  location      = var.region
  repository_id = "${var.prefix}-repo"
  description   = "PR-Agent Dashboard and PR-Agent images"
  format        = "DOCKER"

  depends_on = [google_project_service.artifactregistry]
}

# ------------------------------------------------------------------------------
# Cloud Run (only when images are set)
# ------------------------------------------------------------------------------

data "google_project" "project" {}

locals {
  backend_image_set  = var.backend_image != ""
  frontend_image_set = var.frontend_image != ""
  cloud_run_sa       = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
  # Cloud Run can be reached via hash-style URL (.uri) or project-number URL; allow both for CORS.
  frontend_alt_url = "https://${var.prefix}-frontend-${data.google_project.project.number}.${var.region}.run.app"
  # Always include the known Cloud Run frontend URL(s) so CORS works even when frontend_base_url is not set.
  cors_origins_list = join(",", distinct(concat([local.frontend_alt_url], var.frontend_base_url != "" ? [var.frontend_base_url] : [])))
}

# IAM: allow Cloud Run to read secrets
resource "google_secret_manager_secret_iam_member" "database_url_access" {
  count     = local.backend_image_set && local.use_secret_manager ? 1 : 0
  secret_id = google_secret_manager_secret.database_url[0].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = local.cloud_run_sa
}

resource "google_secret_manager_secret_iam_member" "cron_secret_access" {
  count     = local.backend_image_set && local.use_secret_manager ? 1 : 0
  secret_id = google_secret_manager_secret.cron_secret[0].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = local.cloud_run_sa
}

resource "google_cloud_run_v2_service" "backend" {
  count    = local.backend_image_set ? 1 : 0
  name     = "${var.prefix}-backend"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    timeout = "${var.backend_timeout_seconds}s"
    scaling {
      max_instance_count = var.backend_max_instances
    }
    vpc_access {
      connector = local.vpc_connector_id
      egress    = "PRIVATE_RANGES_ONLY"
    }
    containers {
      image = var.backend_image

      ports {
        container_port = 8080
      }

      # PORT is set automatically by Cloud Run; do not set it here.
      dynamic "env" {
        for_each = var.backend_base_url != "" ? [1] : []
        content {
          name  = "DASHBOARD_BACKEND_BASE_URL"
          value = var.backend_base_url
        }
      }
      dynamic "env" {
        for_each = var.frontend_base_url != "" ? [1] : []
        content {
          name  = "DASHBOARD_FRONTEND_BASE_URL"
          value = var.frontend_base_url
        }
      }
      dynamic "env" {
        for_each = local.cors_origins_list != "" ? [1] : []
        content {
          name  = "DASHBOARD_CORS_ORIGINS"
          value = local.cors_origins_list
        }
      }
      env {
        name  = "DASHBOARD_DEVELOPER_MODE"
        value = "false"
      }
      dynamic "env" {
        for_each = local.use_secret_manager ? [1] : []
        content {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.database_url[0].secret_id
              version = "latest"
            }
          }
        }
      }
      dynamic "env" {
        for_each = local.use_secret_manager ? [] : [1]
        content {
          name  = "DATABASE_URL"
          value = local.database_url
        }
      }
      dynamic "env" {
        for_each = local.use_secret_manager ? [1] : []
        content {
          name = "DASHBOARD_CRON_SECRET"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.cron_secret[0].secret_id
              version = "latest"
            }
          }
        }
      }
      dynamic "env" {
        for_each = local.use_secret_manager ? [] : [1]
        content {
          name  = "DASHBOARD_CRON_SECRET"
          value = local.cron_secret
        }
      }
      env {
        name  = "PR_AGENT_CONFIG_GCS_BUCKET"
        value = google_storage_bucket.config.name
      }
      env {
        name  = "PR_AGENT_CONFIG_GCS_PREFIX"
        value = local.config_prefix
      }
      dynamic "env" {
        for_each = local.backend_image_set && local.use_secret_manager ? [1] : []
        content {
          name = "DASHBOARD_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.dashboard_api_key[0].secret_id
              version = "latest"
            }
          }
        }
      }
      dynamic "env" {
        for_each = local.backend_image_set && !local.use_secret_manager ? [1] : []
        content {
          name  = "DASHBOARD_API_KEY"
          value = local.dashboard_api_key
        }
      }
      env {
        name  = "GCP_RUNNER_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCP_RUNNER_REGION"
        value = var.region
      }
      env {
        name  = "GCP_RUNNER_ZONE"
        value = var.runner_zone != "" ? var.runner_zone : "${var.region}-a"
      }
      env {
        name  = "GCP_RUNNER_MACHINE_TYPE"
        value = var.runner_machine_type
      }
      env {
        name  = "GCP_RUNNER_NETWORK"
        value = local.network_self_link
      }
      env {
        name  = "GCP_RUNNER_PREFIX"
        value = "${var.prefix}-runner"
      }
      env {
        name  = "GCP_RUNNER_PR_AGENT_IMAGE"
        value = var.pr_agent_runner_image
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
    }
    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [local.connection_name]
      }
    }
  }

  # Cloud Build CI/CD updates the container image via `gcloud run services update`.
  # Ignore image drift so `terraform apply` (without -var=backend_image) doesn't revert
  # to the originally deployed image. Also ignore client/client_version metadata that
  # gcloud sets. Env vars (including GCP_RUNNER_PR_AGENT_IMAGE added by the pr-agent
  # pipeline) are preserved because `gcloud run services update --update-env-vars` only
  # adds/modifies; it doesn't remove existing vars.
  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
    ]
  }

  depends_on = [
    google_project_service.run,
    google_project_service.compute,
    google_secret_manager_secret_version.database_url,
    google_secret_manager_secret_version.cron_secret,
    google_secret_manager_secret_version.dashboard_api_key,
    google_secret_manager_secret_iam_member.database_url_access,
    google_secret_manager_secret_iam_member.cron_secret_access,
    google_secret_manager_secret_iam_member.dashboard_api_key_access,
    google_storage_bucket.config,
    google_storage_bucket_iam_member.config_backend,
  ]
}

# IAM: allow Cloud Run backend to create/delete Compute instances (for on-demand runner VM provisioning)
resource "google_project_iam_member" "backend_compute_admin" {
  count   = local.backend_image_set && local.manage_runtime_iam ? 1 : 0
  project = var.project_id
  role    = "roles/compute.instanceAdmin.v1"
  member  = local.cloud_run_sa
}

# IAM: allow default compute SA to pull images from Artifact Registry (runner VMs use this SA)
resource "google_artifact_registry_repository_iam_member" "runner_ar_reader" {
  count      = local.backend_image_set && local.manage_runtime_iam ? 1 : 0
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.repo.name
  role       = "roles/artifactregistry.reader"
  member     = local.cloud_run_sa
}

resource "google_cloud_run_v2_service" "frontend" {
  count    = local.frontend_image_set ? 1 : 0
  name     = "${var.prefix}-frontend"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      image = var.frontend_image

      ports {
        container_port = 80
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
    ]
  }

  depends_on = [google_project_service.run]
}

# Allow unauthenticated invocations if requested
resource "google_cloud_run_v2_service_iam_member" "backend_invoker" {
  count    = local.backend_image_set && var.allow_unauthenticated ? 1 : 0
  location = google_cloud_run_v2_service.backend[0].location
  name     = google_cloud_run_v2_service.backend[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "frontend_invoker" {
  count    = local.frontend_image_set && var.allow_unauthenticated ? 1 : 0
  location = google_cloud_run_v2_service.frontend[0].location
  name     = google_cloud_run_v2_service.frontend[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ------------------------------------------------------------------------------
# Cloud Scheduler (job timeout)
# ------------------------------------------------------------------------------

resource "google_cloud_scheduler_job" "job_timeout" {
  count       = local.backend_image_set ? 1 : 0
  name        = "${var.prefix}-run-job-timeout"
  description = "Call dashboard cron run-job-timeout"
  schedule    = var.job_timeout_schedule
  time_zone   = "UTC"
  region      = var.region

  http_target {
    uri         = "${google_cloud_run_v2_service.backend[0].uri}/api/cron/run-job-timeout"
    http_method = "POST"
    headers = {
      "X-Cron-Secret" = local.cron_secret
    }
  }

  depends_on = [
    google_project_service.scheduler,
    google_cloud_run_v2_service.backend,
  ]
}

# ------------------------------------------------------------------------------
# Optional: self-hosted action runner VM (same VPC; install ADO/GitHub agent after)
# ------------------------------------------------------------------------------

data "google_compute_image" "runner_ubuntu" {
  count   = var.enable_runner_vm && !local.use_existing_vpc ? 1 : 0
  family  = "ubuntu-2204-lts"
  project = "ubuntu-os-cloud"
}

locals {
  runner_zone = var.runner_zone != "" ? var.runner_zone : "${var.region}-a"
}

resource "google_compute_instance" "runner" {
  count        = var.enable_runner_vm && !local.use_existing_vpc ? 1 : 0
  name         = "${var.prefix}-runner"
  machine_type = var.runner_machine_type
  zone         = local.runner_zone

  boot_disk {
    initialize_params {
      image = data.google_compute_image.runner_ubuntu[0].self_link
      size  = 50
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.runner[0].id
    access_config {}
  }

  metadata_startup_script = templatefile("${path.module}/runner-startup.sh.tpl", {
    dashboard_url     = var.backend_base_url
    dashboard_api_key = local.dashboard_api_key
    config_bucket     = google_storage_bucket.config.name
    config_prefix     = local.config_prefix
    pr_agent_repo_url = var.pr_agent_repo_url
    pr_agent_image    = var.pr_agent_runner_image
    ado_org_url       = var.ado_org_url
    ado_pat           = var.ado_pat
    ado_pool          = var.ado_pool
    ado_agent_name    = var.ado_agent_name
  })

  service_account {
    scopes = ["cloud-platform"]
  }

  tags = ["pr-agent-runner"]

  depends_on = [
    google_compute_subnetwork.runner,
    google_project_service.compute,
  ]
}

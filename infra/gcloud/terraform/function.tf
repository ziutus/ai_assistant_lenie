resource "google_project_service" "cloudfunctions" {
  project            = var.project_id
  service            = "cloudfunctions.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudbuild" {
  project            = var.project_id
  service            = "cloudbuild.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "run" {
  project            = var.project_id
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "artifactregistry" {
  project            = var.project_id
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "eventarc" {
  project            = var.project_id
  service            = "eventarc.googleapis.com"
  disable_on_destroy = false
}

# Dedicated service account for the control function, scoped to start/stop/get on the
# lenie-vpn-relay instance only (IAM condition on the resource name) - mirrors the
# least-privilege IAM policy the deleted AWS `ec2-manager` Lambda used
# (infra/aws/serverless/lambdas/ec2-manager/lambda_function.py).
resource "google_service_account" "vpn_relay_control" {
  account_id   = "vpn-relay-control"
  display_name = "lenie-vpn-relay start/stop/status Cloud Function"
}

# Cloud Functions 2nd gen deploys via Cloud Run, which requires the identity running
# `terraform apply` to have iam.serviceaccounts.actAs on the function's runtime service
# account - otherwise deployment fails with a 403 on Cloud Run service creation. Uses the
# caller's own identity dynamically (whoever is authenticated) rather than hardcoding a user.
data "google_client_openid_userinfo" "deployer" {}

resource "google_service_account_iam_member" "vpn_relay_control_deployer_actas" {
  service_account_id = google_service_account.vpn_relay_control.name
  role               = "roles/iam.serviceAccountUser"
  member             = "user:${data.google_client_openid_userinfo.deployer.email}"
}

resource "google_project_iam_custom_role" "vpn_relay_instance_admin" {
  role_id     = "vpnRelayInstanceAdmin"
  title       = "VPN relay instance admin"
  description = "Start/stop/get on the lenie-vpn-relay instance only"
  permissions = [
    "compute.instances.start",
    "compute.instances.stop",
    "compute.instances.get",
  ]
}

resource "google_project_iam_member" "vpn_relay_control_instance_admin" {
  project = var.project_id
  role    = google_project_iam_custom_role.vpn_relay_instance_admin.id
  member  = "serviceAccount:${google_service_account.vpn_relay_control.email}"

  condition {
    title       = "vpn-relay-instance-only"
    description = "Restrict to the lenie-vpn-relay instance only"
    expression  = "resource.name == \"projects/${var.project_id}/zones/${var.zone}/instances/${google_compute_instance.vpn_relay.name}\""
  }
}

resource "google_storage_bucket" "function_source" {
  name                        = "${var.project_id}-gcf-source"
  location                    = var.region
  uniform_bucket_level_access = true
}

data "archive_file" "vpn_relay_control_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../functions/vpn-relay-control"
  output_path = "${path.module}/data/vpn-relay-control.zip"
}

resource "google_storage_bucket_object" "vpn_relay_control_source" {
  name   = "vpn-relay-control-${data.archive_file.vpn_relay_control_zip.output_md5}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.vpn_relay_control_zip.output_path
}

# The Cloud Build step that fetches the function source from GCS runs as the default Compute
# Engine service account - this project doesn't auto-grant it Editor (Google stopped doing that
# for new projects), so it needs explicit read access to the source bucket or the build's
# gcs-fetcher step fails with a non-zero exit before ever reaching a permission-denied message.
data "google_project" "this" {
  project_id = var.project_id
}

resource "google_storage_bucket_iam_member" "function_source_build_reader" {
  bucket = google_storage_bucket.function_source.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${data.google_project.this.number}-compute@developer.gserviceaccount.com"
}

# Cloud Functions' own admin robot re-copies the source into a managed staging bucket
# (gcf-v2-sources-<project number>-<region>, created automatically on first deploy) before the
# build reads from it - that bucket predates uniform bucket-level access and relies on legacy
# ACL grants (projectEditor/projectViewer), which the default Compute Engine SA no longer gets
# automatically. Same fix as above, applied to that bucket instead of our own.
resource "google_storage_bucket_iam_member" "gcf_managed_source_build_reader" {
  bucket = "gcf-v2-sources-${data.google_project.this.number}-${var.region}"
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${data.google_project.this.number}-compute@developer.gserviceaccount.com"
}

# Same root cause as the two grants above (default Compute Engine SA has zero project-level
# roles in this project): the buildpack "creator" step needs to push the built image to
# Artifact Registry and write build logs to Cloud Logging. Matches Google's own troubleshooting
# guidance for this exact error (linked from the deploy failure message) - not project-wide
# Editor, just the two roles the build actually needs, applies to any future Cloud Function too.
resource "google_project_iam_member" "build_sa_artifact_registry_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${data.google_project.this.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_iam_member" "build_sa_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${data.google_project.this.number}-compute@developer.gserviceaccount.com"
}

# 2nd gen, no HTTP trigger / API Gateway / public invoker yet - deliberately narrow scope for
# this stage (see docs/adr/adr-023-gcloud-vpn-relay-nas-access.md). Invoke manually via
# `make gcloud-vpn-start|stop|status` (gcloud functions call), same as the deleted AWS
# `ec2-manager` Lambda was invoked before API Gateway was put in front of it.
resource "google_cloudfunctions2_function" "vpn_relay_control" {
  name     = "vpn-relay-control"
  location = var.region

  build_config {
    runtime     = "python312"
    entry_point = "vpn_relay_control"
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.vpn_relay_control_source.name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    available_memory      = "256Mi"
    timeout_seconds       = 60
    service_account_email = google_service_account.vpn_relay_control.email
    environment_variables = {
      INSTANCE_NAME = google_compute_instance.vpn_relay.name
      ZONE          = var.zone
      PROJECT_ID    = var.project_id
    }
  }

  depends_on = [
    google_project_service.cloudfunctions,
    google_project_service.cloudbuild,
    google_project_service.run,
    google_project_service.artifactregistry,
    google_project_service.eventarc,
    google_service_account_iam_member.vpn_relay_control_deployer_actas,
    google_storage_bucket_iam_member.function_source_build_reader,
    google_storage_bucket_iam_member.gcf_managed_source_build_reader,
    google_project_iam_member.build_sa_artifact_registry_writer,
    google_project_iam_member.build_sa_log_writer,
  ]
}

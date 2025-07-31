
resource "google_cloud_run_v2_job" "ebook_convert" {
  name     = "${var.project_name}-${var.environment}-ebook-convert"
  location = var.region
  project  = var.google_project_id

  template {
     parallelism = 1
     task_count  = 1
    template {
      max_retries = 1
      timeout     = "600s"

      # service_account = var.service_account_email

      volumes {
        name = "ebooks"
        gcs {
          bucket = google_storage_bucket.books_bucket.name
        }
      }

      containers {
        image = var.container_image_ebook_converter

        volume_mounts {
          mount_path = "/mnt/dane"
          name       = "ebooks"
        }

        resources {
          limits = {
            cpu    = "1000m"
            memory = "512Mi"
          }
        }
      }
    }
  }
}

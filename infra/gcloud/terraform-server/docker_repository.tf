# Tworzenie Artifact Registry dla obrazów Docker
resource "google_artifact_registry_repository" "docker_repository" {
  location      = var.region
  repository_id = "${var.project_name}-${var.environment}"
  description   = "Docker repository for ${var.project_name} images"
  format        = "DOCKER"
}

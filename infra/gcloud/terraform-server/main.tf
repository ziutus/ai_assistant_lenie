terraform {
  required_version = ">= 1.0.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.27.0"
    }
  }

  # google cloud storage
  backend "gcs" {
    bucket = "lenie-ai-dev-2025-03-terraform"
    prefix = "terraform/state"
}

}
provider "google" {
  project = var.google_project_id
  region = var.region
}

# module "lenie-ai-server" {
#   source = "./modules/lenie-ai-server-compute"
#   zone = var.zone
# }

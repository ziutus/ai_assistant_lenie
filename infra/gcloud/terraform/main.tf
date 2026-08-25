terraform {
  required_version = ">= 1.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.27.0"
    }
  }

  backend "gcs" {
    bucket = "lenie-ai-478308-tfstate"
    prefix = "vpn-relay"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

variable "google_project_id" {
  type = string
  description = "google project id"
}

variable "region" {
  type = string
  description = "region"
}

variable "zone" {
  type = string
  description = "zone"
}

variable "bucket_terraform_state" {
  type = string
  description = "bucket terraform state"
}

variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "container_image_ebook_converter" {
  description = "Pełna nazwa obrazu kontenera Docker."
  type        = string
}

variable "dns_domain_name" {
  type = string
}

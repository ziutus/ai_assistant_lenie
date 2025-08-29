resource "google_dns_managed_zone" "dev_zone" {
  name        = "dev-2025-03-zone"
  dns_name    = "dev-2025-03.lenie-ai.eu."  # Pamiętaj o kropce na końcu
  description = "Strefa DNS dla środowiska dev-2025-03"
  project     = var.google_project_id

  visibility = "public"
}

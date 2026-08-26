resource "google_project_service" "dns" {
  project            = var.project_id
  service            = "dns.googleapis.com"
  disable_on_destroy = false
}

# Delegated subdomain for GCP-hosted resources (ADR-023). lenie-ai.eu itself stays in AWS
# Route53 (landing page, DynamoDB page cache) - only this one subdomain's NS records point
# here, added manually and once to the Route53 zone (see infra/gcloud/terraform/CLAUDE.md).
resource "google_dns_managed_zone" "gcloud_lenie_ai_eu" {
  name        = "gcloud-lenie-ai-eu"
  dns_name    = "gcloud.lenie-ai.eu."
  description = "Delegated subdomain for GCP-hosted resources - NS delegated from the lenie-ai.eu Route53 zone"
  visibility  = "public"

  depends_on = [google_project_service.dns]
}

# Dedicated service account for the VM, scoped only to this one DNS zone - not the default
# Compute Engine service account, and not project-wide dns.admin.
resource "google_service_account" "vpn_relay_vm" {
  account_id   = "vpn-relay-vm"
  display_name = "lenie-vpn-relay VM (updates its own Cloud DNS A record on boot)"
}

resource "google_dns_managed_zone_iam_member" "vpn_relay_vm_dns_admin" {
  managed_zone = google_dns_managed_zone.gcloud_lenie_ai_eu.name
  role         = "roles/dns.admin"
  member       = "serviceAccount:${google_service_account.vpn_relay_vm.email}"
}

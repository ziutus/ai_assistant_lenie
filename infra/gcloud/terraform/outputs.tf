output "vpn_relay_external_ip" {
  description = "Ephemeral external IP of the OpenVPN relay instance"
  value       = google_compute_instance.vpn_relay.network_interface[0].access_config[0].nat_ip
}

output "gcloud_dns_zone_name_servers" {
  description = "Name servers for the gcloud.lenie-ai.eu Cloud DNS zone - delegate these via a one-time NS record in the lenie-ai.eu Route53 zone (Z07906713RCJHAZLQEP4C), see CLAUDE.md"
  value       = google_dns_managed_zone.gcloud_lenie_ai_eu.name_servers
}

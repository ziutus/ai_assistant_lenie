output "vpn_relay_external_ip" {
  description = "Ephemeral external IP of the OpenVPN relay instance"
  value       = google_compute_instance.vpn_relay.network_interface[0].access_config[0].nat_ip
}

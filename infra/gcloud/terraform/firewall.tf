resource "google_compute_firewall" "allow_openvpn" {
  name    = "lenie-allow-openvpn"
  network = "default"

  allow {
    protocol = "udp"
    ports    = ["1194"]
  }

  target_tags   = ["vpn-relay"]
  source_ranges = ["0.0.0.0/0"]
}

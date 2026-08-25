resource "google_compute_instance" "vpn_relay" {
  name         = "lenie-vpn-relay"
  machine_type = "e2-micro"
  zone         = var.zone
  tags         = ["vpn-relay"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 10
      type  = "pd-standard"
    }
  }

  network_interface {
    network = "default"
    access_config {}
  }

  metadata_startup_script = file("${path.module}/data/openvpn-install-startup.sh")
}

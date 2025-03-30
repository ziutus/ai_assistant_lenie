
resource "google_compute_instance" "lenie-ai-server" {

  machine_type = var.instance_type
  name         = "lenie-ai-server"
  zone = var.zone

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2004-lts"
    }
  }

  network_interface {
    network = "default"
    access_config {}
  }
}

# Tworzenie bucketa do przechowywania książek
resource "google_storage_bucket" "books_bucket" {
  name          = "${var.project_name}-${var.environment}-books"
  location      = var.region
  #location      = "europe-west3"
  force_destroy = false  # Ustaw na true, jeśli chcesz umożliwić usunięcie nawet niepustego bucketa

  # Opcjonalnie możesz dodać więcej konfiguracji
  storage_class = "STANDARD"
  uniform_bucket_level_access = true
}

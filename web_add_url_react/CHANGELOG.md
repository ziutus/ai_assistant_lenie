# CHANGELOG

Wszystkie istotne zmiany w tym projekcie będą udokumentowane w tym pliku.

Format zgodny z [Keep a Changelog](https://keepachangelog.com/) i semantycznym wersjonowaniem [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-02-20
### Zmienione
- Potwierdzono URL endpointu API po konsolidacji bramek API Gateway (z 3 do 2 bramek)
- Endpoint `/url_add` jest teraz obsługiwany przez skonsolidowaną bramkę api-gw-app

## [0.1.0] - 2025-01-01
### Dodano
- Pierwsza wersja aplikacji do dodawania URL-i
- Formularz z polami: URL, typ dokumentu, źródło, język, notatka, tekst
- Komunikacja z API przez axios (POST /url_add)
- Obsługa parametru `?apikey=` w URL do automatycznego uzupełnienia klucza API
- Budowanie w Docker (nginx:alpine, port 80)

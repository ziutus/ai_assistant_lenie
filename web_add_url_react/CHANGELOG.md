# CHANGELOG

Wszystkie istotne zmiany w tym projekcie będą udokumentowane w tym pliku.

Format zgodny z [Keep a Changelog](https://keepachangelog.com/) i semantycznym wersjonowaniem [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-02-20
### Zmienione
- Endpoint `/url_add` jest teraz obsługiwany przez skonsolidowaną bramkę api-gw-app (URL aplikacji już wskazywał na właściwą bramkę — potwierdzono i udokumentowano)
- Usunięto debug log klucza API z konsoli przeglądarki (poprawa bezpieczeństwa)

## [0.1.0] - 2025-08-28
### Dodano
- Pierwsza wersja aplikacji do dodawania URL-i
- Formularz z polami: URL, typ dokumentu, źródło, język, notatka, tekst
- Komunikacja z API przez axios (POST /url_add)
- Obsługa parametru `?apikey=` w URL do automatycznego uzupełnienia klucza API
- Budowanie w Docker (nginx:alpine, port 80)

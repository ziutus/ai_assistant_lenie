# CHANGELOG

Wszystkie istotne zmiany w tym projekcie będą udokumentowane w tym pliku.

Format zgodny z [Keep a Changelog](https://keepachangelog.com/) i semantycznym wersjonowaniem [Semantic Versioning](https://semver.org/).

## [1.0.25] - 2026-07-18
### Dodane
- Tryb „Odśwież istniejący dokument” wysyłający aktualny, wyrenderowany HTML strony wraz z ID dokumentu Lenie.

## [1.0.24] - 2026-07-14
### Dodane
- Lista źródeł (Source) pobierana dynamicznie z backendu (`GET /sources?active=1`) zamiast 4 zaszytych opcji; zaszyte opcje pozostają jako fallback offline (dodatkowo cache w `chrome.storage.local`)
- Opcja „+ Dodaj nowe źródło…" w dropdownie — tworzy źródło przez `POST /sources`
- Zapamiętywanie ostatnio wybranego źródła (`chrome.storage.sync.lastSource`)

## [1.0.23] - 2026-02-20
### Zmienione
- Zaktualizowano domyślny URL endpointu API na skonsolidowaną bramkę api-gw-app (endpoint /url_add przeniesiony do głównej bramki)

## [1.0.22] - 2025-08-29
### Zmienione
- usunięto pola do AI summary i AI correction. To będzie robionie automatycznie w backend.

## [1.0.21] - 2025-08-29
### Zmienione
- Zaktualizowano adres API GW endpoint

## [ 1.0.20] - 2025-08-29
### Zmienione
- Pole token pozwala podejrzeć wartość tokena, jesteś wstanie sprawdzić czy jest poprawny

## [1.0.19] - 2025-08-29
### Zmienione
- Zaktualizowano adres API GW endpoint
- Pole token jest teraz typu password

## [1.0.18] - 2025-08-29
### Zmienione
- Podział na taby, gdzie pierwsza zakładka zawiera menu do dodawania stron, a druga to ustawienia


## [1.0.17] - 2025-01-19
### Dodano
- Dodano informacje o problemach na API GW, do tej chwili wtyczna niezależnie od odpowiedzi z API GW, 
  zawsze informowała, że strona została dodana do systemu.


## [1.0.16] - 2025-01-19
### Dodano
- Dodano obsługę automatycznego wykrywania języka strony.

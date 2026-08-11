# CHANGELOG

## [1.0.46] - 2026-08-11
### Fixed
- Import Gmaila usuwa również wiersze zawierające wyłącznie newsletterowe spacje i znaki niewidoczne.

## [1.0.45] - 2026-08-11
### Fixed
- Import Gmaila usuwa puste wiersze wynikające z układu HTML wiadomości.

## [1.0.44] - 2026-08-11
### Added
- Linki widoczne w importowanej wiadomości Gmail są zapisywane jako `etykieta (URL)`.
- Przekierowania Gmaila są rozpakowywane lokalnie, bez otwierania linków.

## [1.0.43] - 2026-08-11
### Added
- Pilot importu pojedynczej otwartej wiadomości Gmail jako dokumentu `email`.
- Wysyłana jest wyłącznie widoczna treść wiadomości, bez HTML Gmaila i interfejsu skrzynki.

Wszystkie istotne zmiany w tym projekcie będą udokumentowane w tym pliku.

Format zgodny z [Keep a Changelog](https://keepachangelog.com/) i semantycznym wersjonowaniem [Semantic Versioning](https://semver.org/).

## [1.0.42] - 2026-07-29
### Poprawione
- Identyfikator `external_uuid` jest generowany wyłącznie kryptograficznie bez fallbacku `Math.random()`.

## [1.0.41] - 2026-07-29
### Poprawione
- Błędy autoryzacji wskazują teraz, czy odrzucił je NAS czy AWS, oraz które pole klucza należy sprawdzić.

## [1.0.40] - 2026-07-29
### Dodane
- W sieci lokalnej rozszerzenie preferuje NAS (`192.168.200.7:5055`), a poza nią używa AWS jako fallbacku.
- Ustawienia przechowują osobno adres NAS i adres AWS.
- Klucze uwierzytelniające NAS i AWS są przechowywane osobno.
- Dodano uprawnienia hosta dla lokalnego API NAS i AWS API Gateway.

## [1.0.38] - 2026-07-28
### Zmienione
- Diagnostyka została przeniesiona do osobnej zakładki popupu.

## [1.0.37] - 2026-07-28
### Poprawione
- Fallback LinkedIna nie pobiera już pierwszego komentarza jako treści głównego posta.
- Ekstrakcja kończy się przy znaczniku `… more` lub bloku reakcji.

## [1.0.36] - 2026-07-28
### Zmienione
- Język strony wybiera się z menu `pl`, `en` albo `inne`.
- Po wybraniu `inne` pojawia się dodatkowe pole na kod/nazwę języka.
- Dla postów społecznościowych język interfejsu serwisu nie nadpisuje wyboru użytkownika.

## [1.0.35] - 2026-07-28
### Poprawione
- Dodano fallback ekstrakcji dla stron LinkedIna, które renderują post wyłącznie w `body.innerText`.

## [1.0.34] - 2026-07-28
### Poprawione
- Rozszerzono ekstrakcję postów LinkedIn o dodatkowe kontenery, selektory i metadane strony.
- Diagnostyka pokazuje teraz strukturę DOM istotną dla importu LinkedIna.

## [1.0.33] - 2026-07-28
### Dodane
- Panel diagnostyczny popupu z informacjami o rozpoznaniu URL i ekstrakcji posta.
- Możliwość skopiowania raportu diagnostycznego bez klucza API.

## [1.0.32] - 2026-07-28
### Dodane
- Automatyczne rozpoznawanie i ekstrakcja pojedynczych postów LinkedIn.
- Platforma posta (`facebook` lub `linkedin`) jest przekazywana do backendu i zapisywana w dokumencie.
- Posty LinkedIn, podobnie jak Facebooka, są oznaczane jako wymagające zalogowania.

## [1.0.31] - 2026-07-28
### Poprawione
- Numer wersji wyświetlany w popupie jest zgodny z wersją manifestu.

## [1.0.27] - 2026-07-28
### Dodane
- Automatyczne rozpoznawanie adresów pojedynczych postów Facebooka.
- Typ `social_media_post` oraz edytowalne pole treści posta.
- Próba wyodrębnienia treści i autora posta bez importowania komentarzy oraz HTML Facebooka.
- Ręczne uzupełnienie treści, gdy Facebook nie udostępni jej w DOM.

## [1.0.28] - 2026-07-28
### Poprawione
- Ekstrakcja posta czeka na hydrację DOM Facebooka.
- Dodano bezpieczny fallback do widocznego kontenera treści posta, gdy link posta nie znajduje się w DOM.

## [1.0.29] - 2026-07-28
### Dodane
- Pole `requires_login`, niezależne od `paywall`.
- Dla postów Facebooka pole jest domyślnie zaznaczone i wysyłane do backendu.

## [1.0.30] - 2026-07-28
### Poprawione
- Automatyczne rozpoznawanie starszego formatu Facebooka `permalink.php?story_fbid=...`.

## [1.0.26] - 2026-07-20
### Zmienione
- Ponowne dodanie URL jest rozpoznawane jako duplikat zamiast tworzyć kolejny dokument.
- Duplikaty są wykrywane po znormalizowanym adresie (m.in. bez fragmentów i parametrów śledzących).
- „Odśwież istniejący dokument” zastąpiono bezpieczną operacją uzupełnienia brakującego surowego HTML, bez ręcznego podawania ID.

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

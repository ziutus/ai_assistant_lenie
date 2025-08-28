# Lenie AI Assistant

Lenie AI Assistant to rozszerzenie przeglądarki, umożliwiające użytkownikom wysyłanie danych o odwiedzanych stronach internetowych do API oraz zarządzanie ich konfiguracją. Wtyczka obsługuje różne typy treści, takie jak strony internetowe, linki czy filmy YouTube.

## Funkcjonalności

- **Konfiguracja API**: Możliwość ustawienia klucza API i adresu serwera.
- **Obsługa różnych typów treści**: Strony internetowe, linki, filmy YouTube i inne.
- **Wsparcie AI**:
    - Opcja generowania podsumowania strony za pomocą AI.
    - Możliwość korekty danych AI.
- **Zarządzanie płatnymi treściami**: Wybór czy strona zawiera paywall.
- **Automatyczne wykrywanie tytułu i języka strony**.
- **Wysyłanie danych do serwera** z możliwością edycji notatek, listy rozdziałów i dodatkowych szczegółów.

## Instalacja

1. Pobierz repozytorium lub sklonuj je za pomocą:
   ```bash
   git clone <adres_repozytorium>
   ```
2. Otwórz [chrome://extensions/](chrome://extensions/) w przeglądarce Chrome.
3. Włącz tryb deweloperski (Developer mode).
4. Kliknij "Załaduj rozpakowane" (Load unpacked) i wskaż folder projektu.

## Konfiguracja

1. Po instalacji rozszerzenia kliknij ikonę w pasku przeglądarki.
2. Wprowadź klucz API w polu "Klucz API".
3. Ustaw adres serwera API (domyślny: `https://pir31ejsf2.execute-api.us-east-1.amazonaws.com/v1/url_add`).
4. Skonfiguruj dodatkowe opcje: typ treści, źródło, opcje AI, itd.

## Opis plików

- **popup.html**: Główna strona interfejsu użytkownika do konfiguracji i wysyłania danych.
- **popup.js**: Logika JavaScript do obsługi interakcji użytkownika, automatycznego pobierania danych o stronie oraz wysyłania ich do API.
- **manifest.json**: Definicja manifestu rozszerzenia zgodna z wersją 3 Chrome Extensions API.
- **icon16.png / icon48.png / icon128.png**: Ikony rozszerzenia w różnych rozmiarach.

## Wymagania

- Przeglądarka Chrome z obsługą Extensions API w wersji 3.
- Konto w serwisie `lenie-ai.eu`, aby uzyskać klucz API.

## Jak używać

1. Otwórz dowolną stronę internetową w przeglądarce.
2. Kliknij ikonę Lenie AI Assistant i uzupełnij odpowiednie pola:
    - **Tytuł strony** i **język** są automatycznie pobierane.
    - Dodaj własne notatki lub listę rozdziałów.
    - Wybierz odpowiednie opcje, takie jak typ treści, źródło czy parametry AI.
3. Kliknij "Wyślij", aby przesłać dane do serwera.

## Uprawnienia

Rozszerzenie wymaga następujących uprawnień:

- **Storage**: Do przechowywania klucza API i adresu serwera.
- **ActiveTab**: Aby uzyskać dostęp do aktywnej karty.
- **Tabs i Scripting**: Do uruchamiania skryptów na aktywnej stronie w celu pobrania jej zawartości.

## Wersja

Aktualna wersja: **1.0.17**

## Contributing

Chcesz ulepszyć to rozszerzenie? Śmiało, przyjmujemy pull requesty! Przed zgłoszeniem zmian upewnij się, że Twój kod jest zgodny ze standardami projektowymi.

## Licencja

Ten projekt jest objęty licencją MIT. Szczegóły znajdują się w pliku `LICENSE`.

---

Dziękujemy za korzystanie z Lenie AI Assistant!

# Cookidoo (Thermomix)

**Status: odrzucone (automatyczny eksport przepisów nie działa).** Lenie nie ma
oficjalnej ani działającej nieoficjalnej drogi, by wysłać przepisy do Cookidoo.
Przepisy z Lenie (dokumenty z tagiem `przepis`) trafiają do Cookidoo wyłącznie
ręcznie, w edytorze „Utworzone przepisy".

## Co sprawdzono

Cookidoo to platforma Vorwerk (w Polsce Vorwerk Polska, abonament roczny, własne
przepisy w sekcji „Utworzone przepisy", limit 100 sztuk). Zbadano trzy drogi.

| Droga | Wynik |
|---|---|
| Partnerski serwis w Polsce | Brak. [Przepisownia.pl](https://www.przepisownia.pl/) należy do Vorwerk i nie ma własnego eksportu do Cookidoo: strona tylko odsyła do funkcji „Utworzone Przepisy" w Cookidoo. Rejestracja nowych użytkowników w Przepisowni jest zamknięta. |
| Publiczne API lub eksport hurtowy (CSV, JSON) | Nie znaleziono w dokumentacji Cookidoo ani Vorwerk. |
| Import z URL (strona ze `schema.org/Recipe`) | **Przetestowano 2026-11-01, odmowa.** |

### Test importu z URL

Wygenerowano stronę HTML z blokiem JSON-LD `schema.org/Recipe` (składniki, kroki
jako `HowToStep`, porcje, czas), opublikowano ją publicznie na GitHub Pages i
wklejono adres w cookidoo.pl, w „Utworzone przepisy" → „Importuj przepis".
Cookidoo odpowiedziało:

> Nie można zaimportować przepisu. Importowanie danych z tej strony nie jest
> obecnie dozwolone. Dozwolony jest tylko import danych z Cookidoo lub ze stron
> społecznościowych Vorwerk.

Import po URL działa więc tylko z domen Cookidoo i społeczności Vorwerk
(np. Przepisownia). Strona z poprawnym `schema.org/Recipe` na własnej domenie
jest odrzucana, więc publikowanie przepisów z Lenie jako stron WWW nic nie daje.

## Dlaczego nie nieoficjalna automatyzacja

Skrypt albo rozszerzenie przeglądarki wypełniające edytor Cookidoo technicznie
byłoby możliwe, ale:

- [regulamin Vorwerk](https://login.vorwerk.com/account/register/tos) zabrania
  kopiowania i odtwarzania treści oraz aplikacji bez pisemnej zgody,
- ryzykiem jest blokada konta abonenckiego,
- edytor Cookidoo i tak jest miejscem, gdzie wpisuje się ustawienia urządzenia
  (temperatura, obroty, czas), więc automatyzacja dałaby tylko część pracy.

Nie budujemy tego bez wyraźnej decyzji właściciela projektu.

## Co robimy zamiast

Ręczne wpisanie przepisu w edytorze Cookidoo. Gdy przepisów do przeniesienia
będzie dużo, wariantem do rozważenia jest widok w Lenie przygotowany pod
przepisywanie: składniki w osobnych polach do skopiowania i kroki z propozycją
ustawień Thermomixa. Wymaga osobnej decyzji; nie jest zaplanowany.

## Uwagi do ewentualnego powrotu do tematu

- Jeśli Vorwerk udostępni oficjalne API albo import z dowolnego URL, wrócić do
  tej decyzji. Warto wtedy ponownie powtórzyć powyższy test (strona
  `schema.org/Recipe` na publicznym URL).
- Przepisy z książek (np. „Insulinooporność. Szybkie dania") nie nadają się do
  publikowania w sieci bez zgody autorów. Do jakiegokolwiek eksportu nadają się
  przepisy własne albo przerobione na własne słowa.
- Ustawienia Thermomixa (kroki typu „3 min / 120°C / obr. 1") w naszych
  przepisach są propozycjami i trzeba je przetestować na urządzeniu.

Ogólne zasady dla integracji: [README.md](README.md).

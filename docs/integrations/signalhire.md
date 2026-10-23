# SignalHire

**Status: odrzucone** (2026-10-23). Nie integrujemy. Wracamy do tematu tylko przy
zmianie założeń opisanych na końcu.

SignalHire to wyszukiwarka danych kontaktowych (prywatne e-maile i telefony,
profile z LinkedIna, GitHuba, Facebooka) nastawiona na rekrutację i sprzedaż B2B.
Baza ma ok. 900 mln profili.

## Dlaczego nie

- **Skala darmowego planu jest zbyt mała.** Plan darmowy daje 5 kredytów na start
  i 10 miesięcznie po zainstalowaniu rozszerzenia przeglądarkowego. Kredyt schodzi
  tylko wtedy, gdy narzędzie zwróci e-mail lub telefon. Przy ok. 450 kontaktach w
  książce to kilkadziesiąt wzbogaconych osób w rok. Dostęp przez API i MCP wymaga
  planu płatnego (od ok. 57–69 USD miesięcznie), czyli kosztu nieproporcjonalnego
  do domowego użycia.
- **Baza nie pokrywa naszych osób.** Kontakty w Lenie to w większości rodzina,
  znajomi i sąsiedzi, a nie osoby z profilem zawodowym. Prywatne numery komórkowe
  nie są w otwartym internecie (zob. wnioski z prób odwrotnego wyszukiwania po
  numerze), więc trafność byłaby niska.
- **Model brokera danych.** SignalHire zbiera prywatne e-maile i telefony bez wiedzy
  osób, których dotyczą (mają formularz opt-out). Wpisywanie takich danych do
  prywatnej książki kontaktów to ryzyko RODO i problem etyczny. Narusza też
  [zasadę 5 z README](README.md#zasady-dla-nowych-integracji): wzbogacamy firmy
  i domeny, nie prywatne dane osób.
- **Poza rdzeniem Lenie.** Lenie zarządza biblioteką, którą użytkownik świadomie
  zbiera. Wyszukiwanie danych o osobach trzecich w sieci to osobna domena, trzymana
  w skillu `/lenie-person-lookup`, a nie w kodzie backendu.

## Co zamiast

- Kontakty zawodowe: skill `/lenie-contact-linkedin-info` (zalogowana przeglądarka,
  bez brokera danych i bez kosztów).
- Firmy powiązane z osobą: CEIDG/KRS i heurystyka domeny e-mail
  (`/lenie-person-lookup`).
- Jednorazowa próba: rozszerzenie SignalHire zainstalowane ręcznie, 10 darmowych
  kredytów na kilka kontaktów zawodowych, bez żadnego kodu.

## Kiedy wrócić

Dopiero gdy Lenie zacznie obsługiwać kontakty biznesowe na większą skalę (setki
osób z profilami zawodowymi). Wtedy trzeba najpierw ocenić koszt planu z API oraz
zgodność z RODO, a wynik zapisywać jako fakt ze źródłem (jak w panelu „Fakty i
źródła”), nie jako dane „z pewnością prawdziwe”.

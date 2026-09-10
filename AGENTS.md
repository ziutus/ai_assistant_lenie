# AGENTS.md — reguły operacyjne Lenie NAS

## Masowe operacje na Obsidianie

Nie uruchamiaj pełnego `obsidian_reimport` jako jednorazowej migracji na
produkcyjnym NAS-ie. Job bez `relative_path` przechodzi po całym vaultcie;
każda zmieniona notatka może wykonać wiele zewnętrznych wywołań embeddingów,
operacji na PostgreSQL i commitów. Wspólny worker obsługuje przy tym inne
zadania.

Incydent z 2026-09-09 potwierdził to ryzyko: jeden job przeskanował 916 plików
(687 aktualizacji, 228 pominięć), a NAS uległ awarii podczas długiego,
nieograniczonego przebiegu. Błąd pojedynczego embeddingu nie był przyczyną
awarii; zwiększył czas i obciążenie całego przebiegu.

Przed kolejnym backfillem:

1. Dziel pracę na małe partie, najlepiej pojedyncze notatki przez
   `parameters.relative_path`, a najwyżej 25–50 notatek na kontrolowaną partię.
2. Nie twórz kolejnej partii, dopóki poprzednia nie ma statusu `done` i nie
   sprawdzisz `failed`, `load_1`, pamięci dostępnej oraz `iowait`.
3. Uruchamiaj backfill poza godzinami użycia NAS-a i nie łącz go z deployem ani
   migracjami schema w tym samym oknie.
4. Przed startem sprawdź, czy nie ma aktywnego `obsidian_reimport`; używaj
   idempotency key dla każdej partii. Watcher powinien obsługiwać bieżące zmiany
   pojedynczo, a pełny skan pozostaje wyłącznie dziennym safety netem.
5. Bramka host-health ogranicza pobranie nowego joba, ale nie throttluje joba już
   uruchomionego. Nie traktuj jej jako zabezpieczenia przed nieograniczonym
   backfillem.

Po każdej partii potwierdź wynik w bazie i przerwij pracę przy wzroście load albo
iowait, spadku pamięci dostępnej, błędach dostawcy embeddingów lub braku
heartbeat. Wznowienie ma następować od kolejnej małej partii, nie przez ponowne
uruchomienie całego vaultu.

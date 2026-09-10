# Bezpieczny batch backfill Obsidiana

Nie uruchamiaj produkcyjnego `obsidian_reimport` bez `relative_path` jako jednej
migracji całego vaultu. Taki job wykonuje dla każdej zmienionej notatki wiele
wywołań embeddingów, operacji PostgreSQL i commitów, a współdzielony worker
obsługuje równolegle inne zadania.

Incydent z 2026-09-09 potwierdził ryzyko: jeden job przeskanował 916 plików
(687 aktualizacji, 228 pominięć), po czym NAS uległ awarii. Brak ograniczenia
rozmiaru i czasu joba był główną słabością. Błąd pojedynczego embeddingu nie był
samodzielną przyczyną awarii.

Przed backfillem:

1. Dziel pracę na pojedyncze notatki przez `parameters.relative_path`, a jeśli
   potrzebujesz partii, ogranicz ją do 25–50 notatek.
2. Nie uruchamiaj następnej partii, dopóki poprzednia nie ma statusu `done`;
   sprawdź `failed`, `load_1`, pamięć dostępną i `iowait`.
3. Uruchamiaj pracę poza godzinami użycia NAS-a i osobno od deployu oraz migracji
   schematu.
4. Przed startem sprawdź brak aktywnego `obsidian_reimport` i używaj osobnego
   idempotency key dla każdej partii.
5. Admission gate działa tylko przed pobraniem joba. Nie throttluje joba, który
   już się wykonuje, więc nie jest zabezpieczeniem przed dużym backfillem.

Po każdej partii potwierdź wynik w bazie. Przerwij przy wzroście load albo
iowait, spadku pamięci, błędach dostawcy embeddingów lub braku heartbeat.
Wznawiaj od kolejnej małej partii, zamiast uruchamiać cały vault ponownie.

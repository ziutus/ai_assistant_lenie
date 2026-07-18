# Prompt na sesję z Codex — kontynuacja przebudowy wyszukiwania

Ten prompt jest odpowiednikiem `docs/search-rebuild-kickoff-prompt.md`, dostosowanym do sesji
z Codex CLI zamiast Claude Code — użyj go, gdy Claude Code jest niedostępny (np. limit konta) i
chcesz, żeby Codex samodzielnie kontynuował implementację, włącznie z commitem, PR-em i merge'em
(normalnie: „Codex koduje, Claude robi review i commituje" — tu Codex robi całość, bo Claude jest
poza obiegiem).

Skopiuj tekst poniżej do `codex` uruchomionego w katalogu głównym repozytorium.

---

<task>
Kontynuuję wieloetapowy projekt przebudowy wyszukiwania w Lenie (Project Lenie, backend Flask +
SQLAlchemy + PostgreSQL/pgvector, LLM Bielik 11B przez CloudFerro Sherlock). Pracowałem nad tym
z Claude Code przez wiele sesji; Claude jest teraz niedostępny (limit konta), więc Twoim zadaniem
jest samodzielnie wykonać CAŁY cykl: implementację, testy, weryfikację na żywej bazie, commit,
push, PR i merge do main — bez czekania na review od innego agenta.

Plan: `docs/search-rebuild-implementation-plan.md` (po polsku).
Dziennik postępu: `docs/search-rebuild-progress.md` (nowe wpisy na górze — PRZECZYTAJ go w
całości, zanim cokolwiek zmienisz; opisuje dokładnie co zrobiono, jakie testy przeszły i jakie
haczyki napotkano w każdym etapie).

Stan na dziś: etapy 0–6 planu są UKOŃCZONE i zmergowane do main (PR #282–#290). Następny w
kolejce jest **Etap 7 — autor, publisher i discovery source**, `M` (90–180 min), plan mówi:
podzielić na maksymalnie dwie sesje.

Zanim zaczniesz kodować:
1. Przeczytaj cały `docs/search-rebuild-implementation-plan.md`, szczególnie sekcję 3 (docelowe
   nazewnictwo) i etap 7.
2. Przeczytaj `docs/search-rebuild-progress.md` od góry — ostatnie wpisy (etap 6 sesja A i B)
   opisują dokładnie architekturę `library/search/sql_filters.py::build_document_filters()`,
   do którego etap 7 się podłącza.
3. Uruchom `git log --oneline -20` i `git branch -a | grep search`, żeby potwierdzić stan
   repozytorium — dziennik może być nieaktualny, rozstrzyga git.
4. Przeczytaj `backend/library/CLAUDE.md` (sekcja o `library/search/`), `backend/database/CLAUDE.md`
   (schemat tabel), `backend/library/person_registry.py` — to ISTNIEJĄCY wzorzec rozwiązywania
   nazw z NER (alias → Wikidata+LLM → fuzzy pg_trgm → manual_review), analogiczny do tego, co
   trzeba zbudować dla publisherów/discovery source, choć bez potrzeby integracji z Wikidata.

Etap 7 — zakres z planu (sekcja 7):

**Sesja A** (rób ją w tym uruchomieniu):
- dodać tabele `publishers` i `publisher_domains` (migracja Alembic, `upgrade`+`downgrade`
  działające, testowane na bazie NAS — patrz niżej);
- backfill domen z istniejących `web_documents.url` (portal wydawcy ≠ `discovery_source`/
  `information_sources` — patrz sekcja 3 planu, to osobne pojęcia, nie mylić);
- dodać indeksy;
- funkcja rozwiązująca `publisher_name`/`publisher_domain` → `publisher_id` — musi umieć
  zwrócić zero, jedno lub wiele dopasowań BEZ losowego wyboru przy niejednoznaczności (dokładnie
  to jest warunek zakończenia całego etapu 7, patrz niżej).

**Sesja B** (rób ją TYLKO jeśli sesja A ma zielone testy i zostało wystarczająco kontekstu/czasu):
- filtrować autora przez `document_persons.role='author'` i aliasy;
- fallback do obecnego pola `author`/`author_source` (docelowo `byline`/`byline_method`, patrz
  sekcja 3 planu — fizyczny rename kolumn to dopiero etap 11, w NOWYM kodzie używaj już nazw
  docelowych jako nazw zmiennych/koncepcji, ale kolumna w bazie SQL nadal nazywa się `author`);
  zmienić semantykę `sources` na `discovery_sources` w nowym kodzie;
- NIGDY nie utożsamiać żadnego z tych pojęć z `information_sources` (to trzecia, osobna rzecz).

Warunek zakończenia CAŁEGO etapu 7 (z planu): backend potrafi zgłosić zero, jedno lub wiele
dopasowań nazwy bez losowego wyboru.

Po zbudowaniu rozwiązywania nazw podłącz je do
`build_document_filters()` w `backend/library/search/sql_filters.py` — dziś ta funkcja rzuca
`NotImplementedError` dla `author_name`/`publisher_name`/`publisher_domain`/
`discovery_source_name` właśnie dlatego, że etap 7 jeszcze nie istniał. Po tej sesji te cztery
pola powinny działać (albo przynajmniej te, które dotyczy ukończona sesja — jeśli robisz tylko
sesję A, `publisher_name`/`publisher_domain` powinny zacząć działać, `author_name`/
`discovery_source_name` nadal rzucają `NotImplementedError` do sesji B).
</task>

<repo_conventions>
Zasady nadrzędne z planu, obowiązujące w KAŻDEJ sesji (naruszenie = zły PR):
- LLM interpretuje tekst, ale nie generuje SQL i nie zna identyfikatorów bazy — ten etap jest
  czysto backendowy/SQL, LLM nie bierze w nim udziału.
- Nowe nazwy domenowe (sekcja 3 planu) stosuj w nowym kodzie/API od razu; fizyczne rename'y
  kolumn/tabel to dopiero etap 11 — NIE rób ich teraz.
- Awaria walidacji/rozwiązywania nazw nie może wywalić wyszukiwania (fallback na "brak
  dopasowania", nie wyjątek 500) — patrz jak `SearchService.search_similar()` już to robi dla
  `SearchQueryValidationError` (`library/search_service.py`) — trzymaj się tego wzorca.
- Migracje Alembic i zmiany SQL testuj na bazie NAS (`192.168.200.7:5434`, user `postgres`,
  hasło `postgres`, baza `lenie-ai`), NIE na lokalnym Dockerze. `psql` z Windows:
  `PGPASSWORD=postgres "/c/Program Files/PostgreSQL/18/bin/psql.exe" -h 192.168.200.7 -p 5434 -U postgres -d lenie-ai`.
  Każda migracja musi mieć działający `upgrade` I `downgrade`.
- Testy z `backend/`: `PYTHONPATH=. .venv/Scripts/python -m pytest tests/unit/ -q` (venv
  projektu, NIE uvx — pełna suita importuje moduły wymagające sqlalchemy/flask). Lint:
  `uvx ruff check backend/` z katalogu głównego repo.
- Nie łącz w jednym commicie migracji schematu + logiki rozwiązywania nazw + zmiany
  `sql_filters.py` jeśli da się to sensownie rozdzielić na commity; ale JEDEN PR na sesję jest OK
  (tak jak w dotychczasowych PR-ach #282–#290 tego planu — jeden PR = jeden etap/sesja).
- Zawsze osobny branch: `feat/search-etap-7a-publishers` (sesja A) /
  `feat/search-etap-7b-author-discovery-source` (sesja B), NIGDY commit prosto na main.
- Commity podpisuj: `git commit --author="Codex <noreply@openai.com>" -m "..."` (istniejąca
  konwencja w tym repo dla pracy Codexa — sprawdź `git log --all --format='%an <%ae>'` jeśli
  chcesz się upewnić).
- Po zaimplementowaniu: `git push -u origin <branch>`, potem
  `gh pr create --base main --title "..." --body "..."`, potem `gh pr merge <numer> --merge`.
  Rób to samodzielnie — nie ma tu Claude'a, który by to zrobił za Ciebie.
- NIE commituj plików z sekretami. Nowe zmienne konfiguracyjne (jeśli jakieś potrzebne) czytaj
  przez `library/config_loader.py`.
- Nigdy nie usuwaj brancha `before_claude_code`.
</repo_conventions>

<verification_loop>
Dla KAŻDEJ sesji (A i ewentualnie B):
1. Zaimplementuj + napisz testy jednostkowe (mockowane sesje, konwencja z
   `backend/tests/CLAUDE.md` — sprawdź istniejące testy `test_search_sql_filters.py`,
   `test_repository_sql_filters.py`, `test_list_by_filters.py` jako wzorzec stylu: kompilowanie
   SQL do stringa przez `.compile(compile_kwargs={"literal_binds": True})` i sprawdzanie
   fragmentów tekstu).
2. Uruchom PEŁNĄ suitę (`pytest tests/unit/ -q`) — musi być 100% zielono, nie tylko nowe testy.
   Aktualny stan bazowy (przed Twoimi zmianami): **1785 passed**. Jeśli po Twoich zmianach liczba
   testów spadnie albo cokolwiek czerwone — napraw przed commitem.
3. `uvx ruff check backend/` z katalogu głównego — musi być czyste.
4. Migrację Alembic zastosuj na bazie NAS (`alembic upgrade head`), zweryfikuj psql-em, potem
   `alembic downgrade` do poprzedniej rewizji i z powrotem `upgrade head` — potwierdź że
   reversible.
5. Napisz krótki skrypt weryfikacyjny E2E (zapisz w katalogu tymczasowym, NIE w repo) wywołujący
   realną funkcję rozwiązywania nazw na realnych danych z NAS (np. sprawdź, czy istnieje w bazie
   jakiś portal/publisher z wieloma wariantami URL i czy Twoja funkcja poprawnie go rozwiąże;
   sprawdź przypadek niejednoznaczny — powinien zwrócić listę kandydatów, nie zgadywać). Usuń
   skrypt po weryfikacji, nic nie zostawiaj w bazie (rollback/DELETE testowych wierszy, jeśli
   coś wstawiałeś).
6. Dopiero po zielonych testach + czystym lint + potwierdzonej migracji na NAS + E2E rób commit.
</verification_loop>

<completeness_contract>
Nie zatrzymuj się na pierwszym działającym rozwiązaniu bez sprawdzenia edge case'ów: pusta nazwa,
nazwa z polskimi znakami diakrytycznymi (portal może być wpisany "Onet.pl" vs "onet.pl" vs
"onet"), wielokrotne dopasowanie tej samej domeny do dwóch różnych publisherów (nie powinno się
zdarzyć — jeśli Twój model danych na to pozwala, dodaj constraint), publisher bez żadnej domeny
w bazie. Sprawdź też, czy `build_document_filters()` nadal rzuca `NotImplementedError` dla pól
NIE objętych sesją, którą akurat robisz (np. jeśli robisz tylko sesję A, `author_name` i
`discovery_source_name` powinny nadal rzucać — nie zostawiaj częściowo działającego filtra bez
jasnego rozgraniczenia, co działa a co nie).
</completeness_contract>

<default_follow_through_policy>
Podejmuj rozsądne decyzje samodzielnie i kontynuuj — nie pytaj o rzeczy, które i tak rozstrzygnie
kod/testy (np. dokładna nazwa kolumny, kształt indeksu). Zatrzymaj się i zapytaj wyłącznie jeśli:
natrafisz na sprzeczność między planem a stanem kodu (tak jak instruuje krok 2 dotychczasowego
kickoff promptu Claude), albo migracja wymagałaby nieodwracalnej operacji na danych produkcyjnych
na NAS.
</default_follow_through_policy>

<session_closeout>
Na końcu KAŻDEJ sesji (nawet jeśli robisz tylko sesję A i kończysz):
1. Zaktualizuj `docs/search-rebuild-progress.md` — dopisz nowy wpis NA GÓRZE (wzoruj się na
   formacie istniejących wpisów: Zakres wykonany / Testy uruchomione / Otwarte ryzyka /
   Następny krok). Podaj dokładne liczby testów, numer PR, hash mergowanego commita.
2. Zaktualizuj `backend/library/CLAUDE.md` i `backend/tests/CLAUDE.md` — opisz nowe moduły/testy
   tak jak są opisane istniejące wpisy w tych plikach (styl: gęsty, konkretny, z wyjaśnieniem
   "dlaczego", nie tylko "co").
3. Upewnij się, że PR jest zmergowany do main i `git log --oneline -3 origin/main` to pokazuje.
4. Napisz krótkie podsumowanie na końcu (po polsku): co zrobiłeś, jakie testy przeszły, co zostało
   na sesję B (jeśli robiłeś tylko A), żeby użytkownik (Krzysztof) mógł to przeczytać bez
   zaglądania w kod.
</session_closeout>

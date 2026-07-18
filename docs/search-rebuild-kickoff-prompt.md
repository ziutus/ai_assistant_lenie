# Prompt na rozpoczęcie sesji implementacyjnej przebudowy wyszukiwania

Skopiuj poniższy prompt do Claude Code (lub innego modelu kodującego) uruchomionego w katalogu głównym repozytorium — zarówno przy pierwszej sesji, jak i przy każdej kolejnej, gdy trzeba odświeżyć kontekst.

---

Rozpoczynam sesję implementacyjną przebudowy wyszukiwania w projekcie Lenie. Plan prac znajduje się w:

`docs/search-rebuild-implementation-plan.md`

Kontekst:

- Hobbystyczny projekt Lenie; duże i niekompatybilne zmiany są dozwolone. Slack bot był kodem testowym i nie jest wymaganym konsumentem.
- Backend: Flask + SQLAlchemy + PostgreSQL z pgvector. Frontend: React (`/search`). Domyślny LLM: Bielik 11B v3.0 przez CloudFerro Sherlock.
- Potwierdzony cennik CloudFerro (2026-07-18): `Bielik-11B-v3.0-Instruct` 0,56 EUR / 1 mln tokenów we/wy; embedding `BAAI/bge-multilingual-gemma2` 0,50 PLN netto / 1 mln tokenów. Pieniądze wyłącznie jako `NUMERIC`/`Decimal`, nigdy `float`.
- Pracuję w krótkich sesjach 45–120 minut z powodu limitów pracy z modelami. Jedna sesja = dokładnie jeden etap `S` albo połowa etapu `M`. Nie zaczynaj kolejnego etapu, jeśli testy bieżącego nie przechodzą.

Krok 1 — odtwórz stan prac (zanim cokolwiek zmienisz):

1. Przeczytaj cały plan `docs/search-rebuild-implementation-plan.md`.
2. Jeżeli istnieje `docs/search-rebuild-progress.md`, przeczytaj go — zawiera dziennik sesji: co wykonano, jakie testy uruchomiono, otwarte ryzyka i zaplanowany następny krok.
3. Jeżeli istnieje raport review planu (np. `docs/search-rebuild-review*.md`), uwzględnij jego ustalenia; przy sprzeczności raportu z planem zapytaj mnie, zanim wybierzesz.
4. Sprawdź `git log --oneline -15` i listę branchy `feat/search-*`, aby zweryfikować, które etapy realnie są w main lub w otwartych PR-ach. Dziennik może być nieaktualny — rozstrzyga stan repozytorium.
5. Na tej podstawie wskaż: ostatni ukończony etap, etap bieżącej sesji i jego warunek zakończenia z planu.

Krok 2 — zweryfikuj założenia etapu w kodzie:

Przed implementacją sprawdź pliki, których etap dotyczy (minimum: `backend/library/db/models.py`, `backend/library/search_service.py`, `backend/library/ai.py`, `backend/library/api/cloudferro/sherlock/sherlock.py`, `backend/server.py`, `backend/alembic/versions/`). Jeżeli plan rozmija się z aktualnym kodem, zgłoś to przed pisaniem kodu.

Krok 3 — plan sesji i implementacja:

1. Przedstaw krótki plan sesji: zakres (co wchodzi, co świadomie zostaje poza sesją), pliki do zmiany, testy do napisania/uruchomienia oraz bezpieczny punkt przerwania.
2. Po mojej akceptacji implementuj na feature branchu (np. `feat/search-etap-N-krotki-opis`); nigdy bezpośrednio na main.
3. Testy uruchamiaj z `backend/`: `PYTHONPATH=. .venv/Scripts/python -m pytest tests/unit/ -q` (venv projektu, nie uvx); lint: `uvx ruff check backend/` z katalogu głównego.
4. Migracje Alembic i zmiany SQL testuj na bazie NAS (`192.168.200.7:5434`), nie na lokalnym Dockerze; migracja musi mieć działający `upgrade` i `downgrade`.
5. Nie łącz w jednym commicie migracji schematu, zmiany promptu i UI. Commit z `--author="Claude Code <noreply@anthropic.com>"`.
6. Nie commituj plików z sekretami; nowe zmienne konfiguracyjne dopisuj do `scripts/vars-classification.yaml` i czytaj przez config_loader.

Krok 4 — zamknięcie sesji (obowiązkowe, nawet jeśli etap nieukończony):

Zaktualizuj (lub utwórz) `docs/search-rebuild-progress.md`, dopisując na górze wpis: data, numer etapu, wykonany zakres, uruchomione testy i ich wynik, otwarte ryzyka, następny krok. Jeżeli sesja kończy się przed zielonymi testami, zapisz plan naprawczy i nie zaczynaj następnego etapu.

Zasady nadrzędne z planu, które obowiązują w każdej sesji:

- LLM interpretuje tekst, ale nie generuje SQL i nie zna identyfikatorów bazy.
- Nowe nazwy domenowe (sekcja 3 planu: `document_id`, `published_on`, `byline`, `discovery_source_id`, `subject_period_*` itd.) stosuj w API i nowym kodzie od początku; fizyczne rename'y tabel dopiero w etapie 11.
- Awaria Bielika nie może blokować wyszukiwania (fallback na surową frazę) ani wyszukiwarki transakcyjnie (zapis logów nie może wywalić wyszukiwania).
- Każde wywołanie LLM zostawia dokładnie jeden rekord usage; koszt liczy wyłącznie centralny serwis (nie dodawaj do `AiResponse` atrybutów `cost_usd`/`cost`/`credits_used` — szczegóły w etapach 3 i 3b planu).

---

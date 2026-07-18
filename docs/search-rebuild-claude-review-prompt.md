# Prompt do review planu w Claude Code

Skopiuj poniższy prompt do Claude Code uruchomionego w katalogu głównym repozytorium.

---

Przeprowadź krytyczne review planu przebudowy wyszukiwania znajdującego się w:

`docs/search-rebuild-implementation-plan.md`

Kontekst:

- Jest to hobbystyczny projekt Lenie; duże i niekompatybilne zmiany są dozwolone.
- PostgreSQL i SQLAlchemy przechowują dokumenty, embeddingi pgvector, osoby/autorów, źródła odkrycia, źródła informacji oraz okresy historyczne treści.
- Frontend React ma stronę `/search`.
- Domyślnym LLM jest już zaimplementowany Bielik 11B v3.0 przez CloudFerro Sherlock.
- Potwierdzony cennik CloudFerro dla `Bielik-11B-v3.0-Instruct` wynosi 0,56 EUR za 1 mln tokenów wejściowych i 0,56 EUR za 1 mln tokenów wyjściowych (informacja właściciela projektu z 2026-07-18).
- Potwierdzony cennik CloudFerro dla embeddingu `BAAI/bge-multilingual-gemma2` wynosi 0,50 PLN netto za 1 mln tokenów we/wy (informacja właściciela projektu z 2026-07-18). Wywołania embeddingów mają wchodzić w zakres `llm_usage_logs`; zwróć uwagę, że cenniki są w różnych walutach (EUR/PLN), a istniejący `TranscriptionLog` rozlicza w USD.
- Slack bot był kodem testowym i nie jest wymaganym konsumentem. Nie optymalizuj planu pod jego kompatybilność.
- Celem jest interpretowanie luźnych polskich zapytań, np. „niewolnictwo w afryce miedzy od konca II wojny swiatowej”, pokazanie użytkownikowi ustawionych przez Bielika filtrów oraz zapisywanie błędów i korekt w bazie.
- Prace muszą być dzielone na krótkie, zamykalne etapy z powodu limitów godzinowych i dziennych pracy z modelami.

Najpierw przeczytaj cały plan, a następnie zweryfikuj jego założenia w aktualnym kodzie. W szczególności sprawdź:

- `backend/library/db/models.py`
- `backend/library/search_service.py`
- `backend/library/stalker_web_documents_db_postgresql.py`
- `backend/library/ai_intent_parser.py`
- `backend/library/ai.py`
- `backend/library/api/cloudferro/sherlock/sherlock.py`
- `backend/library/time_periods.py`
- `backend/server.py`
- `backend/alembic/versions/`
- `backend/database/init/`
- `web_interface_react/src/modules/shared/pages/search.tsx`
- `web_interface_react/src/modules/shared/hooks/useSearch.ts`
- `shared/types/`

Nie implementuj zmian. Przygotuj raport review zawierający:

1. Krótką ocenę, czy proponowana architektura prowadzi do celu.
2. Fakty z repozytorium, które potwierdzają albo podważają założenia planu, ze ścieżkami i numerami linii.
3. Błędy merytoryczne, pominięte zależności i ryzyka migracji.
4. Ocenę docelowego nazewnictwa pól i tabel. Zaproponuj lepsze nazwy tam, gdzie obecne propozycje nadal są niejednoznaczne.
5. Ocenę rozdzielenia: publisher, discovery source, information source, author/byline, publication date, ingestion date i subject period.
6. Ocenę kontraktu `POST /search`, `POST /search/parse` i endpointu feedbacku.
7. Ocenę schematu `search_interpretation_logs`, prywatności, retencji i przydatności danych do późniejszego ulepszania parsera.
8. Ocenę ogólnego `llm_usage_logs`: tokenów, latency, kosztów, wersjonowania cennika, powiązania z operacją oraz odporności na przyszłe modele i providerów.
9. Ocenę odporności na błędny JSON, prompt injection, timeout Bielika, niejednoznaczne nazwy i błędne okresy historyczne.
10. Ocenę kolejności etapów. Wskaż zależności, które uniemożliwiają wykonanie etapu niezależnie.
11. Proponowany poprawiony podział na sesje 45–120 minut i dzienne paczki pracy.
12. Minimalny zakres MVP oraz elementy, które należy świadomie odłożyć.
13. Konkretne kryteria akceptacji i brakujące testy, w tym testy z prawdziwym Bielikiem 11B.

Zwróć szczególną uwagę na następujące pytania:

- Czy najpierw wprowadzić nowe nazwy na poziomie domeny/API i mapować je na stare kolumny ORM, a fizyczne rename'y wykonać później?
- Czy filtry można bezpiecznie zastosować przed limitem w zapytaniu pgvector bez utraty wykorzystania indeksu HNSW?
- Czy publisher powinien być osobną tabelą, czy można bezpiecznie wykorzystać istniejące `information_sources`?
- Czy `project` powinien zostać pojedynczym `collection_id`, czy relacją M:N?
- Jak rozwiązać autorów, kiedy `web_documents.author` jest tekstowym cache'em, a `document_persons` może mieć niepełne pokrycie?
- Czy API Sherlock faktycznie obsługuje structured output dla używanego Bielika? Jeśli kod tego nie dowodzi, oznacz to jako wymagający testu integracyjnego, a nie jako fakt.
- Jak mierzyć jakość parsera bez polegania na samoocenie confidence generowanej przez model?
- Które dane trzeba zapisać, aby odtworzyć błędną interpretację, ale nie gromadzić niepotrzebnie prywatnych danych?
- Czy plan poprawnie liczy koszt Bielika osobno dla tokenów wejściowych i wyjściowych według stawki 0,56 EUR / 1 mln oraz zachowuje wystarczającą precyzję dla krótkich wywołań?
- Czy koszt powinien być zapisany jako raportowany, estymowany, alokowany lub nieznany, zamiast zawsze wymuszać kwotę per call?
- Jak uniknąć podwójnego naliczania kosztu między centralnym wrapperem LLM a modułami domenowymi, które już próbują odczytywać `cost_usd`/`cost`/`credits_used` z obiektu odpowiedzi (np. `_response_usage` w `timeline_events.py`)?
- Czy rejestr usage obejmuje wywołania embeddingów (`sherlock_embedding.py`, batche po 32 fragmenty), a agregaty poprawnie rozdzielają waluty EUR (Bielik), PLN (embedding) i USD (`TranscriptionLog`)?

Forma odpowiedzi:

- Zacznij od najpoważniejszych problemów.
- Oddziel problemy blokujące, ważne i opcjonalne ulepszenia.
- Każdy problem poprzyj dowodem z kodu albo zaznacz, że jest hipotezą.
- Na końcu przedstaw poprawioną kolejność etapów w tabeli: etap, zakres, zależności, estymata, test końcowy i bezpieczny punkt przerwania.
- Nie chwal planu ogólnie; skup się na wykryciu miejsc, które mogą prowadzić do błędnej implementacji lub niepotrzebnej pracy.

---

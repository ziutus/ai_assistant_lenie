# Plan implementacji wspólnych grup i priorytetów materiałów

## Cel

Dodać zarządzalne grupy wspólne dla kandydatów z feedu i dokumentów, tak aby:

- jeden materiał mógł należeć do kilku tematów, np. `Geopolityka` i `Informatyka`;
- materiał miał najwyżej jeden priorytet pracy, np. `Praca`, `Hobby` albo `Może kiedyś`;
- użytkownik mógł tworzyć, zmieniać i usuwać grupy;
- instalacja zawsze startowała z priorytetem `Może kiedyś`;
- grupy były widoczne i edytowalne w kolejce oraz na stronie dokumentu;
- lista dokumentów pokazywała grupy oraz pozwalała niezależnie filtrować tematy i priorytet;
- filtr tematów pozwalał wybrać wiele wartości i określić `dowolny` albo `wszystkie`;
- Bielik automatycznie sugerował pasujące istniejące tematy, bez zgadywania priorytetu;
- sugestię można było zaakceptować, odrzucić albo cofnąć jej akceptację;
- dokument przejmował grupy wpisu feedowego podczas importu;
- pochodzenie z feedu pozostawało dostępne nawet po późniejszej zmianie grup dokumentu;
- dodanie tego samego materiału przez rozszerzenie Chrome zachowywało grupy dzięki spięciu po canonical URL.

Plan jest przeznaczony do sekwencyjnego wykonania przez mniejszy model. Nie rozszerzaj zakresu poza opisane etapy.

## Model pojęciowy

### Dwa rodzaje grup

1. `topic` — temat materiału; można przypisać wiele:
   - `Geopolityka`
   - `Informatyka`
   - `Bazy danych`

2. `priority` — kolejność pracy; można przypisać najwyżej jeden:
   - `Praca` z `priority_rank=10`
   - `Hobby` z `priority_rank=70`
   - `Może kiedyś` z `priority_rank=100`

Niższy `priority_rank` oznacza wcześniejszą pracę. Dozwolony zakres to 1–100.

Przykład:

```text
Dokument:
  tematy: Geopolityka, Informatyka
  priorytet: Praca (10)
```

Taki dokument pojawia się przed dokumentem:

```text
Dokument:
  tematy: Geopolityka
  priorytet: Hobby (70)
```

### Grupy a istniejące tagi dokumentu

Nie zastępuj `documents.tags` i nie migruj go w tej iteracji.

- `documents.tags` nadal opisuje treść i zasila istniejące wyszukiwanie, mapy oraz analizę;
- nowe grupy opisują organizację pracy użytkownika;
- ta sama nazwa może celowo wystąpić jako tag i grupa;
- `Może kiedyś` nie może automatycznie trafić do `documents.tags`.

### Bieżące przypisanie a pochodzenie

Potrzebne są dwa niezależne ślady:

1. członkostwa `feed_item` — zachowywane po imporcie jako provenance;
2. członkostwa `document` — bieżąca organizacja dokumentu, edytowalna po imporcie.

Podczas importu grupy wpisu feedowego są kopiowane do dokumentu. Późniejsza edycja grup dokumentu nie zmienia historycznych grup wpisu feedowego.

## Założenia produktowe

1. Grupy są wspólne dla obecnej domowej kolejki, nie prywatne per użytkownik.
2. Materiał może mieć wiele grup `topic`, ale najwyżej jedną aktywną grupę `priority`.
3. Dokument bez priorytetu jest sortowany za dokumentami z priorytetem.
4. Przy takim samym priorytecie dokumenty są sortowane po `ingested_at DESC`, następnie `id DESC`.
5. Backend zachowuje dotychczasowe domyślne sortowanie `newest`; frontend listy domyślnie wybiera `priority`, aby realizować nowy workflow.
6. Istniejące zapisane wpisy i dokumenty pozostają bez grup po migracji.
7. `Może kiedyś` jest zwykłą grupą `priority` utworzoną przez migrację z `priority_rank=100`. Nie koduj jej ID ani nie rozpoznawaj jej po nazwie.
8. Usunięcie grupy jest miękkie (`archived_at`), aby nie niszczyć provenance.
9. Nie można zarchiwizować grupy używanej przez:
   - wpis o statusie `saved_for_later`;
   - bieżące członkostwo dowolnego dokumentu.
10. Historyczne członkostwo zaimportowanego `feed_item` nie blokuje archiwizacji.
11. Zarchiwizowana grupa nie jest dostępna do nowych przypisań, ale pozostaje widoczna w endpointzie pochodzenia dokumentu.
12. Bielik wybiera wyłącznie spośród aktywnych grup `topic`; nigdy nie tworzy grup i nie sugeruje `priority`.
13. Sugestia LLM nigdy nie staje się członkostwem bez jawnej akceptacji użytkownika.
14. Odrzucona albo cofnięta sugestia nie pojawia się ponownie automatycznie dla tego samego materiału i niezmienionego katalogu tematów.

## Stan obecny, którego nie wolno zepsuć

- `feed_items.status = saved_for_later` oznacza wspólną kolejkę.
- `POST /feed_items/<id>/save-for-later` zapisuje `saved_at` i `saved_by_user_id`.
- `POST /feed_items/<id>/import` ustawia `feed_items.document_id`.
- `GET /feed_items?status=saved_for_later` sortuje po `saved_at`.
- Widok kolejki znajduje się w `web_interface_react/src/modules/shared/pages/feedReview.tsx`.
- Lista dokumentów używa `GET /website_list`, `DocumentRepository.get_list()` i `useList.ts`.
- Strony edycji dokumentów współdzielą `SharedInputs`, ale część stron blokuje swój formularz po wygenerowaniu danych pochodnych.
- Chrome używa `POST /url_add` i obecnie omija `feed_items`.
- Canonical URL jest wyliczany przez `library.url_normalization.canonicalize_url`.

## Docelowy model bazy danych

### `content_groups`

- `id SERIAL PRIMARY KEY`
- `name VARCHAR(80) NOT NULL`
- `kind VARCHAR(20) NOT NULL`
- `priority_rank INTEGER NULL`
- `archived_at TIMESTAMPTZ NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Constrainty:

```sql
CHECK (kind IN ('topic', 'priority'))
CHECK (
  (kind = 'topic' AND priority_rank IS NULL)
  OR
  (kind = 'priority' AND priority_rank BETWEEN 1 AND 100)
)
```

Dodaj częściowy unikalny indeks po `lower(name)` dla `archived_at IS NULL`. Aktywne `Praca` i `praca` nie mogą istnieć równocześnie. Po archiwizacji nazwa może być użyta ponownie.

### `feed_item_group_memberships`

- `feed_item_id INTEGER NOT NULL REFERENCES feed_items(id) ON DELETE CASCADE`
- `group_id INTEGER NOT NULL REFERENCES content_groups(id) ON DELETE RESTRICT`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `source VARCHAR(20) NOT NULL DEFAULT 'manual'`
- `source_suggestion_id INTEGER NULL`
- PRIMARY KEY (`feed_item_id`, `group_id`)
- indeks po `group_id`
- CHECK: `source IN ('manual', 'llm_suggestion')`

### `document_group_memberships`

- `document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE`
- `group_id INTEGER NOT NULL REFERENCES content_groups(id) ON DELETE RESTRICT`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `source VARCHAR(20) NOT NULL DEFAULT 'manual'`
- `source_suggestion_id INTEGER NULL`
- PRIMARY KEY (`document_id`, `group_id`)
- indeks po `group_id`
- CHECK: `source IN ('manual', 'feed_import', 'chrome_link', 'llm_suggestion')`

`source` opisuje pierwszą przyczynę utworzenia bieżącego członkostwa. Nie jest pełnym audytem zmian. Historyczne provenance pozostaje w tabeli członkostw feedu.

### `content_group_suggestion_runs`

- `id SERIAL PRIMARY KEY`
- dokładnie jedno z:
  - `feed_item_id INTEGER NULL REFERENCES feed_items(id) ON DELETE CASCADE`
  - `document_id INTEGER NULL REFERENCES documents(id) ON DELETE CASCADE`
- `job_id VARCHAR(32) NULL REFERENCES jobs(id) ON DELETE SET NULL`
- `status VARCHAR(20) NOT NULL`
- `model VARCHAR(100) NOT NULL`
- `prompt_version VARCHAR(30) NOT NULL`
- `input_hash VARCHAR(64) NOT NULL`
- `catalog_snapshot JSONB NOT NULL`
- `raw_result JSONB NULL`
- `error TEXT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `completed_at TIMESTAMPTZ NULL`

Constrainty:

- dokładnie jeden target: `feed_item_id` XOR `document_id`;
- `status IN ('queued', 'running', 'completed', 'error')`.

Dodaj dwa częściowe indeksy uniemożliwiające drugi aktywny run dla tego samego targetu, gdy status jest `queued` albo `running`.

### `content_group_suggestions`

- `id SERIAL PRIMARY KEY`
- `run_id INTEGER NOT NULL REFERENCES content_group_suggestion_runs(id) ON DELETE CASCADE`
- `group_id INTEGER NOT NULL REFERENCES content_groups(id) ON DELETE RESTRICT`
- `confidence NUMERIC(4,3) NOT NULL`
- `reason VARCHAR(300) NULL`
- `status VARCHAR(20) NOT NULL DEFAULT 'pending'`
- `membership_created BOOLEAN NOT NULL DEFAULT false`
- `decided_by_user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL`
- `decided_at TIMESTAMPTZ NULL`
- UNIQUE (`run_id`, `group_id`)
- CHECK: `confidence BETWEEN 0 AND 1`
- CHECK: `status IN ('pending', 'accepted', 'dismissed', 'reverted')`

Po utworzeniu `content_group_suggestions` dodaj FK z obu kolumn `source_suggestion_id` tabel członkostw do `content_group_suggestions.id` z `ON DELETE SET NULL`.

Jeżeli `source='llm_suggestion'`, `source_suggestion_id` musi być ustawione. Dla pozostałych źródeł ma być `NULL`.

### Invariant jednego priorytetu

Rodzaj grupy znajduje się w `content_groups`, dlatego prosty częściowy indeks na tabeli członkostw nie wystarczy. Egzekwuj invariant w serwisie:

1. zablokuj edytowany `FeedItem` albo `Document` przez `SELECT ... FOR UPDATE`;
2. pobierz wszystkie wskazane aktywne grupy;
3. odrzuć zbiór zawierający więcej niż jedną grupę `priority`;
4. zastąp członkostwa w tej samej transakcji.

Nie polegaj wyłącznie na walidacji frontendu.

## Kontrakt REST

Wszystkie endpointy wymagają klucza użytkownika, tak jak obecna kuracja feedu i edycja dokumentów.

### Zarządzanie grupami

`GET /content_groups`

Parametry:

- domyślnie tylko aktywne;
- `include_archived=1` — także zarchiwizowane.

Odpowiedź:

```json
{
  "content_groups": [
    {
      "id": 1,
      "name": "Może kiedyś",
      "kind": "priority",
      "priority_rank": 100,
      "archived_at": null,
      "saved_item_count": 4,
      "document_count": 2,
      "provenance_item_count": 7
    }
  ]
}
```

`POST /content_groups`

Body tematu:

```json
{"name": "Geopolityka", "kind": "topic"}
```

Body priorytetu:

```json
{"name": "Praca", "kind": "priority", "priority_rank": 10}
```

Walidacja:

- nazwa po trim ma 1–80 znaków;
- `kind` ma dozwoloną wartość;
- `topic` wymaga `priority_rank=null` albo braku pola;
- `priority` wymaga liczby całkowitej 1–100;
- duplikat aktywnej nazwy zwraca `409`;
- sukces zwraca `201`.

`PATCH /content_groups/<id>`

Pozwala zmienić `name`, `kind` i `priority_rank`, ale:

- stosuje pełną walidację stanu wynikowego;
- nie edytuje zarchiwizowanej grupy (`409`);
- zmiana `topic -> priority` jest niedozwolona, jeśli jakikolwiek wpis lub dokument miałby przez to dwa priorytety (`409`);
- zmiana `priority -> topic` jest dozwolona.

`DELETE /content_groups/<id>`

- nie wykonuje fizycznego DELETE;
- jeżeli grupa ma aktywne użycia, zwraca `409` z `saved_item_count` i `document_count`;
- w przeciwnym razie ustawia `archived_at` i `updated_at`;
- historyczne członkostwa feedowe pozostają;
- sukces zwraca `200`.

Do obsługi naruszeń unikalności łap tylko `IntegrityError`, wykonaj rollback i zwróć `409`. Nie mapuj każdego wyjątku bazy na duplikat.

### Grupy wpisu feedowego

`PATCH /feed_items/<id>/groups`

Body:

```json
{"group_ids": [1, 2, 3]}
```

Zasady:

- `group_ids` jest tablicą unikalnych liczb całkowitych;
- pusta tablica usuwa wszystkie bieżące przypisania;
- wszystkie ID muszą wskazywać aktywne grupy;
- najwyżej jedna wskazana grupa może mieć `kind=priority`;
- edycja jest dozwolona tylko dla `saved_for_later`, inaczej `409`;
- operacja zastępuje cały zbiór w jednej transakcji;
- odpowiedź zawiera pełny wpis z grupami.

Rozszerz `POST /feed_items/<id>/save-for-later` o opcjonalny body:

```json
{"group_ids": [1, 3]}
```

Wywołanie bez body pozostaje kompatybilne. Zmiana statusu i członkostw kończy się jednym commit.

Rozszerz `GET /feed_items`:

- `topic_group_ids=1,2` — lista aktywnych tematów;
- `topic_match=any|all` — domyślnie `any`;
- `priority_group_id=<id>` — dokładnie jeden priorytet;
- `without_topics=1` — brak aktywnych tematów;
- `without_priority=1` — brak aktywnej grupy `priority`;
- `topic_group_ids` i `without_topics=1` razem zwracają `400`;
- `priority_group_id` i `without_priority=1` razem zwracają `400`;
- nieistniejący temat, temat użyty jako priorytet albo priorytet użyty jako temat zwraca `400`;
- filtry tematów oraz priorytetu można stosować osobno albo łącznie;
- wszystkie filtry łączą się przez AND z `status` i `feed_source_id`.

Każdy `_item_dict` otrzymuje posortowane `groups`.

### Grupy dokumentu

`GET /document/<document_id>/groups`

Zwraca aktywne bieżące grupy dokumentu:

```json
{
  "document_id": 123,
  "groups": [
    {
      "id": 2,
      "name": "Geopolityka",
      "kind": "topic",
      "priority_rank": null,
      "source": "feed_import"
    },
    {
      "id": 5,
      "name": "Praca",
      "kind": "priority",
      "priority_rank": 10,
      "source": "manual"
    }
  ]
}
```

`PATCH /document/<document_id>/groups`

Body:

```json
{"group_ids": [2, 5]}
```

Zasady są takie jak dla wpisu feedowego, z różnicami:

- można edytować każdy istniejący dokument;
- nie blokuj tej operacji przez `content_locked`, ponieważ grupy są metadanymi organizacyjnymi i nie unieważniają embeddingów ani analizy;
- nowe członkostwa mają `source=manual`;
- zachowane członkostwa zachowują dotychczasowe `source`;
- usunięte członkostwa znikają tylko z dokumentu, nie z provenance `feed_item`.

### Pochodzenie dokumentu

`GET /document/<document_id>/origin-feed-groups`

Zwraca pasujące wpisy feedowe oraz ich grupy, także zarchiwizowane. Dokument bez pochodzenia feedowego zwraca `200` i puste tablice.

Nie zmieniaj przez to kontraktu `Document.dict()`.

### Lista dokumentów

Rozszerz `GET /website_list`:

- `topic_group_ids=1,2` — dokument pasuje do wybranych tematów;
- `topic_match=any|all` — domyślnie `any`;
- `priority_group_id=<id>` — dokument ma wskazany priorytet;
- `without_topics=1` — dokument nie ma aktywnych tematów;
- `without_priority=1` — dokument nie ma aktywnej grupy `priority`;
- `sort=newest|priority`;
- domyślne `sort=newest` dla kompatybilności API.

Semantyka:

- `topic_match=any`: dokument ma co najmniej jeden z wybranych tematów;
- `topic_match=all`: dokument ma wszystkie wybrane tematy;
- temat i priorytet można filtrować niezależnie;
- po podaniu obu rodzajów filtrów dokument musi spełnić oba;
- sprzeczne albo pomylone rodzaje grup zwracają `400`.

Odpowiedź każdego elementu `websites` otrzymuje:

```json
"groups": [
  {
    "id": 2,
    "name": "Geopolityka",
    "kind": "topic",
    "priority_rank": null
  },
  {
    "id": 5,
    "name": "Praca",
    "kind": "priority",
    "priority_rank": 10
  }
],
"effective_priority_rank": 10
```

Sortowanie `priority`:

1. aktywny priorytet `priority_rank ASC`;
2. dokument bez priorytetu na końcu (`NULLS LAST`);
3. `Document.ingested_at DESC`;
4. `Document.id DESC`.

Ten sam filtr grup musi trafić zarówno do zapytania wyników, jak i zapytania `count`, żeby paginacja była poprawna.

Nie wykonuj zapytania o grupy osobno dla każdego dokumentu. Pobierz członkostwa dla wszystkich `doc_ids` z bieżącej strony jednym dodatkowym zapytaniem i zbuduj mapę w Pythonie albo użyj równoważnego eager loading.

## Sugestie tematów przez Bielika

### Zasady klasyfikacji

Sugestie są klasyfikacją do zamkniętego, zarządzanego przez użytkownika katalogu:

1. Kandydatami są wyłącznie aktywne `content_groups.kind='topic'`.
2. Bielik zwraca ID istniejących grup; nie może zwrócić nowej nazwy.
3. Priorytety `Praca`, `Hobby`, `Może kiedyś` nigdy nie są wejściem klasyfikatora. Zależą od intencji użytkownika, nie od treści.
4. Jeżeli nie ma aktywnych tematów, zakończ bez wywołania LLM.
5. Maksymalnie zapisz pięć sugestii.
6. Domyślny próg wyświetlania to `confidence >= 0.60`, konfigurowalny przez `CONTENT_GROUP_SUGGESTION_MIN_CONFIDENCE`.
7. Odpowiedź spoza listy kandydatów, z błędnym ID albo błędnym formatem jest ignorowana i zapisywana w runie do diagnostyki.

Można wykorzystać wzorzec wywołania z `library/article_tagging.py`, ale nie jego statyczną stałą `THEMATIC_TAGS`. Źródłem kandydatów zawsze jest baza `content_groups`, dzięki czemu dodanie lub zmiana nazwy tematu działa bez wdrożenia kodu.

Model:

- `CONTENT_GROUP_SUGGESTION_MODEL`;
- fallback do istniejącego `TAGGING_MODEL`;
- ostateczny fallback `Bielik-11B-v3.0-Instruct`.

Wywołuj `ai_ask` z:

- `temperature=0`;
- `operation='content_group_suggestion'`;
- `document_id` dla dokumentu;
- `analysis_job_id` z kolejki;
- osobnym `system_prompt`, który nakazuje klasyfikację i ignorowanie instrukcji zawartych w materiale;
- `response_format` jako JSON Schema obsługiwany przez Sherlock/Bielika.

Oczekiwany JSON:

```json
{
  "suggestions": [
    {
      "group_id": 2,
      "confidence": 0.91,
      "reason": "Materiał omawia relacje państw i politykę bezpieczeństwa."
    }
  ]
}
```

Dynamiczny JSON Schema ma ograniczyć `group_id` przez `enum` do aktualnych ID tematów. Po odpowiedzi wykonaj jeszcze walidację serwerową.

### Tekst wejściowy

Dla `FeedItem`:

- tytuł;
- summary;
- tekstowy fragment bezpiecznych pól `raw_payload`, z limitem całego wejścia;
- nie pobieraj strony z Internetu w zadaniu sugestii.

Dla `Document`:

1. preferuj syntezę ostatniego niesuperseded runu analizy, jeśli istnieje;
2. w przeciwnym razie użyj title + summary + początek `text_md` albo `text`;
3. zastosuj jawny limit znaków, np. 6000.

`input_hash` obejmuje tekst wejściowy, wersję promptu i snapshot katalogu tematów. Dzięki temu ten sam materiał nie jest bez potrzeby ponownie analizowany, ale zmiana treści albo katalogu może utworzyć nowy run.

### Kolejka w tle

Rozszerz istniejącą tabelę i worker `jobs` o typ:

`content_group_suggest`

Parametry zawierają dokładnie jeden target:

```json
{"feed_item_id": 123}
```

albo:

```json
{"document_id": 456}
```

Zmień:

- check constraint typów joba w migracji i fresh install;
- `library.job_queue.JOB_TYPES`;
- walidację `POST /jobs`;
- `backend/worker.py`.

Worker NAS ma te same sekrety co backend, więc może użyć istniejącego `ai_ask`. Zmień nieaktualny komentarz workera mówiący, że nigdy nie wykonuje LLM.

Klucz idempotencji:

```text
content_group_suggest:<target_type>:<target_id>:<input_hash>
```

Automatyczne wyzwalanie:

- po `save-for-later`, jeżeli istnieją aktywne tematy;
- po imporcie feed itemu do dokumentu;
- po późnym spięciu Chrome;
- po `website_save`, jeżeli zmienił się tekstowy fingerprint dokumentu.

Wyzwolenie jest best-effort po udanym zapisie domenowym: awaria enqueue nie może cofnąć zapisania materiału, ale ma być zalogowana i pokazana jako brak sugestii/możliwość ponowienia.

### REST sugestii

`GET /feed_items/<id>/group-suggestions`

`GET /document/<id>/group-suggestions`

Zwraca najnowsze sugestie oraz status aktywnego runu.

`POST /feed_items/<id>/group-suggestions`

`POST /document/<id>/group-suggestions`

Ręcznie zleca lub ponawia analizę i zwraca `202` z jobem. Domyślnie nie ponawia identycznego ukończonego runu. Body `{"force": true}` jawnie pozwala ponowić.

`POST /content_group_suggestions/<id>/accept`

- wymaga statusu `pending`;
- pod blokadą targetu sprawdza, czy grupa jest nadal aktywnym tematem;
- jeżeli członkostwa nie było, tworzy je z `source='llm_suggestion'` i `source_suggestion_id=<id>`;
- jeżeli temat był już przypisany, nie tworzy duplikatu i ustawia `membership_created=false`;
- ustawia `accepted`, użytkownika i czas;
- zwraca sugestię i aktualne grupy targetu.

`POST /content_group_suggestions/<id>/dismiss`

- zmienia `pending -> dismissed`;
- nie zmienia członkostw;
- sugestia nie wraca automatycznie dla tego samego fingerprintu.

`POST /content_group_suggestions/<id>/revert`

- wymaga `accepted`;
- usuwa członkostwo tylko wtedy, gdy nadal ma `source_suggestion_id` tej sugestii;
- nigdy nie usuwa członkostwa utworzonego wcześniej ręcznie ani przejętego przez późniejszą ręczną edycję;
- ustawia `reverted` i zwraca `membership_removed`.

Ręczny PATCH pełnego zestawu grup oznacza świadome potwierdzenie użytkownika. Dla zachowanych członkostw o `source='llm_suggestion'` zmień źródło na `manual` i wyczyść `source_suggestion_id`, aby późniejsze `revert` nie usunęło świadomie zachowanego tematu.

Nie dodawaj endpointu „automatycznie zaakceptuj wszystkie”. UI może udostępnić jawny przycisk `Akceptuj wszystkie`, który wywołuje accept dla widocznych sugestii.

## Dziedziczenie grup przy imporcie

Dodaj jeden współdzielony helper serwisowy:

```python
copy_feed_groups_to_document(session, feed_items, document, source) -> None
```

Zasady:

1. Wszystkie aktywne grupy `topic` wpisów są dodawane do dokumentu jako suma zbiorów.
2. Istniejące ręczne tematy dokumentu nie są usuwane.
3. Jeżeli dokument ma już priorytet, zachowaj go.
4. Jeżeli dokument nie ma priorytetu, wybierz spośród wpisów priorytet o najniższym `priority_rank`.
5. Użyj `source=feed_import` dla zwykłego importu i `source=chrome_link` dla późnego spięcia Chrome.
6. Operacja jest idempotentna i nie tworzy duplikatów.
7. Oryginalne członkostwa feedowe pozostają bez zmian.

Wywołaj helper w istniejącym `import_feed_item()` przed końcowym commit.

## Powiązanie importu przez Chrome

Dodaj helper:

```python
link_matching_feed_items_to_document(session, document) -> int
```

Zachowanie:

1. Szuka wszystkich `feed_items` o `canonical_url == document.canonical_url`.
2. Ustawia im `document_id`.
3. Statusy `new`, `llm_analysis_requested`, `saved_for_later` i `error` zmienia na `imported`.
4. `skipped` i `ignored` zachowują status, ale otrzymują `document_id`.
5. Nie usuwa członkostw feedu, `saved_at` ani `saved_by_user_id`.
6. Kopiuje grupy do dokumentu zgodnie z regułami powyżej.
7. Aktualizuje `updated_at`.
8. Zwraca liczbę spiętych wpisów.

Wywołaj helper w `POST /url_add`:

- po poprawnym `create_document`;
- po `fill_missing_html`;
- w obsłudze `ExistingDocumentError`.

Zachowaj dotychczasowe kody odpowiedzi `/url_add`, w tym `409 already_exists`. Ponowienie requestu ma naprawić ewentualne niedokończone spięcie.

## Kolejność implementacji dla mniejszego modelu

### Etap 1 — migracja i ORM

Pliki:

- nowa migracja `backend/alembic/versions/` oparta na aktualnym headzie `f1e2d3c4b5a6`;
- `backend/database/init/35-create-feed-monitor-and-jobs.sql`;
- `backend/library/db/models.py`.

Zadania:

1. Dodaj `content_groups` i obie tabele członkostw.
2. Dodaj tabele runów i sugestii LLM.
3. Dodaj `source`/`source_suggestion_id`, constrainty i indeksy.
4. Rozszerz check constraint typów `jobs` o `content_group_suggest`.
5. W migracji i skrypcie fresh install utwórz `Może kiedyś` jako `priority`, rank 100.
6. Dodaj modele i relacje SQLAlchemy:
   - `FeedItem.groups`;
   - `Document.groups`;
   - jawne modele członkostw, ponieważ `source` i `source_suggestion_id` są potrzebne w API;
   - runy oraz sugestie.
7. Ustaw stabilne sortowanie: priorytety po rank, potem tematy po nazwie.
8. Downgrade usuwa FK do sugestii, członkostwa, sugestie/runy, a na końcu grupy.
9. Nie zmieniaj istniejących statusów feedu ani `documents.tags`.

Testy:

- kolumny, PK, FK, checki i indeksy;
- relacje obu encji;
- dozwolone wartości `source`;
- XOR targetu runu;
- statusy runów i sugestii;
- seed sprawdzony w źródle migracji/fresh install.

### Etap 2 — serwis grup

Pliki:

- nowy `backend/library/content_group_service.py`;
- `backend/library/feed_monitor_service.py`.

Zadania:

1. Scentralizuj walidację nazw, rodzaju, rank i list ID.
2. Zaimplementuj CRUD i liczniki grup.
3. Zaimplementuj atomowe zastępowanie grup `FeedItem`.
4. Zaimplementuj atomowe zastępowanie grup `Document`.
5. Egzekwuj jeden priorytet pod blokadą rekordu.
6. Rozszerz `transition_item` o opcjonalne `group_ids` bez dodatkowego commit.
7. Dodaj kopiowanie grup podczas `import_feed_item`.
8. Nie usuwaj provenance po imporcie, restore, skip ani ignore.

Testy:

- walidacja trim/długość/kind/rank;
- nazwa unikalna case-insensitive;
- odrzucenie nieistniejących i zarchiwizowanych ID;
- odrzucenie dwóch priorytetów;
- wiele tematów jest dozwolone;
- pełne zastąpienie i opróżnienie;
- zachowanie `source` dla niezmienionych członkostw dokumentu;
- archiwizacja wolnej grupy;
- `409` przy aktywnym użyciu;
- provenance nie blokuje archiwizacji;
- import kopiuje tematy i wybiera najwyższy priorytet;
- ręczny priorytet dokumentu wygrywa z importowanym.

### Etap 3 — endpointy

Pliki:

- `backend/library/feed_routes.py` albo nowy blueprint `content_group_routes.py`;
- rejestracja blueprintu w `backend/server.py`, jeżeli powstanie nowy moduł;
- nowy `backend/tests/unit/test_content_groups.py`;
- rozszerzenie `backend/tests/unit/test_feed_saved_for_later.py`.

Zadania:

1. Dodaj CRUD `content_groups`.
2. Dodaj GET/PATCH grup feed itemu i dokumentu.
3. Obsłuż `group_ids` w save-for-later.
4. Dodaj grupy do `_item_dict`.
5. Dodaj filtry kolejki.
6. Dodaj endpoint provenance.
7. Zapewnij eager loading/batch loading.
8. Stosuj kody: walidacja `400`, brak `404`, konflikt `409`.

### Etap 4 — lista dokumentów

Pliki:

- `backend/server.py`;
- `backend/library/document_repository.py`;
- `backend/tests/unit/test_get_list_query.py`;
- ewentualnie osobny test `test_document_group_list.py`.

Zadania:

1. Dodaj parametry filtrów i sortowania do `/website_list`.
2. Przekaż identyczne filtry do zapytania listy i count.
3. Dodaj osobne warunki tematów i priorytetu przez `EXISTS`, aby uniknąć duplikowania dokumentów.
4. Dla `topic_match=any` użyj jednego `EXISTS ... group_id IN (...)`.
5. Dla `topic_match=all` wymagaj obecności każdego ID albo użyj podzapytania `HAVING count(distinct group_id) = N`.
6. Dodaj sortowanie po skorelowanym priorytecie albo równoważnym podzapytaniu.
7. Pobierz grupy całej strony jednym zapytaniem.
8. Dodaj `groups` i `effective_priority_rank` do wyniku.
9. Zachowaj stare sortowanie, gdy `sort` nie podano.

Testy:

- każdy filtr tworzy właściwy SQL;
- filtry tematów `any/all` i priorytetu pojawiają się przed LIMIT;
- temat i priorytet działają samodzielnie oraz razem;
- count ma te same WHERE;
- `priority` daje rank ASC, NULLS LAST, ingested/id tiebreaker;
- `newest` zachowuje dotychczasowy ORDER BY;
- batch grup nie jest N+1;
- wynik ma poprawny kształt.

### Etap 5 — Chrome late-link

Pliki:

- `backend/library/feed_monitor_service.py` lub osobny moduł bez cyklu importów;
- `backend/server.py`;
- test helpera i testy `/url_add`.

Przypadki:

- nowy dokument z Chrome spina feed item i kopiuje grupy;
- `409 already_exists` także wykonuje spięcie;
- warianty URL trafiają dzięki canonical URL;
- kilka źródeł tego samego URL zostaje spiętych;
- `skipped`/`ignored` zachowują status;
- ręczny priorytet dokumentu nie jest nadpisany;
- drugie wywołanie jest idempotentne.

### Etap 6 — sugestie Bielika i worker

Pliki:

- nowy `backend/library/content_group_suggestion_service.py`;
- `backend/library/job_queue.py`;
- `backend/worker.py`;
- endpointy grup/sugestii;
- `backend/tests/unit/test_content_group_suggestions.py`;
- testy workera i job queue.

Zadania:

1. Zbuduj fingerprint i snapshot aktywnych tematów.
2. Zbuduj bezpieczny prompt i JSON Schema.
3. Wywołaj Bielika przez `ai_ask` z pełnym kontekstem usage.
4. Zapisz run oraz przefiltrowane sugestie.
5. Dodaj idempotentne enqueue i wykonanie joba.
6. Podepnij automatyczne wyzwalanie do czterech wskazanych ścieżek.
7. Dodaj GET/request/accept/dismiss/revert.
8. Zapewnij bezpieczne cofanie tylko członkostwa utworzonego przez sugestię.
9. Nie dotykaj istniejącej ręcznej kolejki `feed_item_llm_analyses`; ma inne przeznaczenie.

Testy:

- zero tematów pomija LLM;
- prompt zawiera tylko aktywne tematy;
- JSON Schema ogranicza ID;
- nieznane/archiwalne ID są ignorowane;
- wynik jest ograniczony do pięciu i progu confidence;
- priority nigdy nie jest sugerowany;
- input jest ograniczony długością;
- identyczny fingerprint nie tworzy drugiego joba;
- zmiana katalogu lub treści pozwala na nowy run;
- accept tworzy członkostwo raz;
- accept istniejącego ręcznego tematu nie przejmuje jego własności;
- dismiss niczego nie przypisuje;
- revert usuwa tylko członkostwo tej sugestii;
- ręczny PATCH chroni członkostwo przed późniejszym revert;
- wyjątek LLM kończy run jako error i jest widoczny do ponowienia;
- `llm_usage_logs.operation == content_group_suggestion`.

### Etap 7 — wspólne komponenty React

Dodaj:

- `ContentGroup` do `shared/types/documents.ts`;
- `ContentGroupSuggestion` i status runu sugestii;
- rozszerzenie `ListItem.groups` i `effective_priority_rank`;
- klient/hook grup, np. `useContentGroups`;
- komponent wielokrotnego wyboru tematów;
- komponent pojedynczego wyboru priorytetu;
- panel zarządzania grupami.

Nie implementuj priorytetu jako zwykłego multi-select. UI ma uniemożliwiać wybór dwóch priorytetów, ale backend nadal musi to walidować.

Dodaj także komponent sugestii:

- chip z przerywaną obwódką;
- confidence i reason w tooltipie;
- `Akceptuj`, `Odrzuć`, `Cofnij`;
- `Akceptuj wszystkie` jako seria jawnych acceptów;
- wskaźnik queued/running/error;
- przycisk `Zaproponuj ponownie`.

### Etap 8 — kolejka feedów

Pliki:

- `web_interface_react/src/modules/shared/pages/feedReview.tsx`;
- nowe komponenty grup;
- testy strony/komponentów.

Zadania:

1. Ładuj grupy równolegle ze źródłami i wpisami.
2. Na nowej karcie pozwól wybrać wiele tematów i jeden priorytet przed save-for-later.
3. Na zapisanej karcie pozwól edytować przypisania jednym PATCH.
4. Dodaj niezależny multi-select tematów, tryb `dowolny/wszystkie` i selector priorytetu.
5. Dodaj `Bez tematów` i `Bez priorytetu`.
6. Zachowuj filtry `view`, `feed_source_id`, `topic_group_ids`, `topic_match`, `priority_group_id`, `without_topics` i `without_priority` w URL.
7. Pokaż oczekujące sugestie i decyzje bez przeładowania całej strony.
8. Dodaj panel create/edit/archive z czytelnym komunikatem po `409`.
9. Nie rozpoznawaj `Może kiedyś` po ID ani nazwie.
10. Nie zmieniaj detekcji do przeczytania/do obejrzenia.

### Etap 9 — strona dokumentu

Dodaj komponent:

`web_interface_react/src/modules/shared/components/DocumentGroupsPanel/DocumentGroupsPanel.tsx`

Zachowanie:

1. Otrzymuje `documentId`.
2. Ładuje `GET /document/<id>/groups` i aktywne `content_groups`.
3. Pokazuje:
   - priorytet jako wyróżniony chip;
   - tematy jako pozostałe chipy;
   - `Brak priorytetu`, jeśli nie wybrano.
4. Tryb edycji pozwala wybrać jeden priorytet i wiele tematów.
5. Zapis wysyła pełny zbiór do PATCH.
6. Panel działa niezależnie od `website_save`.
7. Panel nie jest blokowany przez `content_locked`.
8. Panel pokazuje sugestie Bielika i pozwala accept/dismiss/revert.
9. Po zaakceptowaniu pokaż toast z natychmiastowym `Cofnij`.

Umieść panel nad formularzem na wszystkich stronach edycji dokumentu:

- `link.tsx`;
- `webpage.tsx`;
- `youtube.tsx`;
- `movie.tsx`;
- `email.tsx`, jeżeli route nadal jest aktywny.

Nie wkładaj panelu do zablokowanego `fieldset` w `webpage.tsx`. Dzięki oddzielnemu endpointowi zmiana organizacji nie powoduje przebudowy embeddingów.

Opcjonalny przycisk `Pokaż pochodzenie` może rozwinąć dane z `origin-feed-groups`, ale nie jest wymagany do podstawowej edycji.

### Etap 10 — lista dokumentów w React

Pliki:

- `web_interface_react/src/modules/shared/pages/list.tsx`;
- `web_interface_react/src/modules/shared/hooks/useList.ts`;
- `web_interface_react/src/modules/shared/services/storage.ts`;
- test listy.

Zadania:

1. Dodaj wielokrotny filtr tematów.
2. Dodaj przełącznik dopasowania `Dowolny temat` / `Wszystkie tematy`.
3. Dodaj niezależny filtr jednego priorytetu.
4. Dodaj `Bez tematów` i `Bez priorytetu`.
5. Dodaj sortowanie:
   - `Według priorytetu` — domyślne w UI;
   - `Najnowsze`.
6. Zapisuj wybór w URL i `ListFilters`.
7. Zeruj stronę do 1 po zmianie filtra lub sortowania.
8. Przekazuj filtry do `useList`.
9. Pokazuj priorytet i tematy jako chipy przy każdym dokumencie.
10. Pokazuj oczekujące sugestie tematów z szybkim accept/dismiss oraz cofnięciem.
11. Kolor priorytetu może zależeć od rank:
   - 1–33 — wysoki;
   - 34–66 — średni;
   - 67–100 — niski.
12. Nie opieraj logiki na nazwach `Praca`, `Hobby` ani `Może kiedyś`.
13. Filtry grup mają współdziałać z typem, stanem, tekstem, Obsidianem, embeddingami i paginacją.
14. Link `Kopiuj link` ma zachować nowe parametry.

Minimalne testy UI:

- wiele tematów i jeden priorytet na karcie;
- próba wybrania drugiego priorytetu zastępuje pierwszy;
- PATCH dokumentu zawiera pełny zbiór;
- panel działa dla dokumentu z `content_locked`;
- lista pokazuje chipy;
- filtr i sort trafiają do URL/requestu;
- `any/all` zmienia semantykę requestu;
- temat i priorytet można filtrować osobno oraz razem;
- zmiana filtra resetuje page;
- accept/dismiss działa bez otwierania dokumentu;
- cofnięcie nie usuwa ręcznie dodanego tematu;
- filtr źródła kolejki nie ginie po zmianie grupy;
- konflikt archiwizacji pokazuje liczniki użyć.

### Etap 11 — dokumentacja i weryfikacja

Zaktualizuj:

- `backend/library/CLAUDE.md`;
- `backend/database/CLAUDE.md`;
- `backend/CLAUDE.md` — nowe endpointy;
- `web_interface_react/CLAUDE.md`;
- `shared/types/documents.ts`;
- wersję frontendu tylko jeżeli repozytorium wymaga bumpa dla każdej funkcji.

Uruchom z katalogu repo:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest tests/unit/test_feed_saved_for_later.py tests/unit/test_content_groups.py tests/unit/test_content_group_suggestions.py tests/unit/test_get_list_query.py tests/unit/test_document_service.py -q
Set-Location ..\web_interface_react
npm test -- --run
npm run lint
npm run build
```

Jeżeli pełny zestaw testów backendu działa bez zewnętrznej bazy:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest tests/unit -q
```

Nie uruchamiaj testów integracyjnych PostgreSQL bez skonfigurowanego środowiska.

## Kryteria akceptacji

1. Wpis i dokument mogą mieć jednocześnie `Geopolityka`, `Informatyka` oraz jeden priorytet.
2. API odrzuca dwa priorytety na jednym wpisie lub dokumencie.
3. `Może kiedyś` istnieje po migracji i fresh install z rank 100.
4. Można utworzyć, edytować i zarchiwizować grupę.
5. Nie można zarchiwizować grupy używanej przez kolejkę lub dokumenty.
6. Stare wpisy i dokumenty pozostają dostępne jako `Bez tematów` / `Bez priorytetu`.
7. Import z feedu kopiuje grupy do dokumentu i zachowuje provenance.
8. Późniejsza edycja dokumentu nie zmienia historycznych grup feed itemu.
9. Dodanie tego samego URL przez Chrome także kopiuje grupy i ustawia `document_id`.
10. Grupy są widoczne i edytowalne na wszystkich stronach dokumentu.
11. Grupy są widoczne na liście dokumentów.
12. Lista pozwala wybrać tylko tematy, tylko priorytet albo oba rodzaje filtrów.
13. Wiele tematów działa jako `dowolny` albo `wszystkie`.
14. Lista filtruje po braku tematów i braku priorytetu.
15. Sortowanie priorytetowe pokazuje `Praca (10)` przed `Hobby (70)` i `Może kiedyś (100)`, a dokumenty bez priorytetu na końcu.
16. Bielik sugeruje wyłącznie aktywne tematy z zamkniętej listy.
17. Bielik nigdy nie sugeruje priorytetu ani nie tworzy nowej grupy.
18. Sugestia nie zmienia grup przed akceptacją.
19. Akceptację można cofnąć bez usunięcia ręcznie przypisanego tematu.
20. Odrzucona sugestia nie wraca automatycznie dla tego samego fingerprintu.
21. Automatyczne wyzwolenie nie blokuje zapisu materiału i jest idempotentne.
22. Count i paginacja odpowiadają filtrom.
23. Nie ma zapytań N+1.
24. `Może kiedyś` nie trafia do `documents.tags`.
25. Stare save-for-later bez body pozostaje kompatybilne.
26. Zmiana grup dokumentu nie unieważnia embeddingów ani analizy.

## Poza zakresem

- prywatne grupy per użytkownik;
- pełny dziennik historii każdej zmiany członkostwa;
- automatyczne akceptowanie sugestii LLM;
- sugerowanie priorytetów przez LLM;
- tworzenie nowych grup na podstawie swobodnej odpowiedzi LLM;
- kopiowanie grup do `documents.tags`;
- zagnieżdżone grupy;
- drag-and-drop; rank edytuje się liczbowo;
- edycja manifestu lub UI rozszerzenia Chrome;
- migracja tekstowego `documents.tags` do osobnych tabel;
- grupy jako filtr nowego hybrydowego `POST /search` — ta iteracja dotyczy `/website_list`.

## Instrukcja wykonawcza dla mniejszego modelu

Wykonuj etapy 1–11 w kolejności. Po każdym etapie uruchom testy dotyczące zmienionej warstwy i napraw regresje przed przejściem dalej. Nie używaj JSON do przechowywania członkostw. Nie zastępuj wielu tematów pojedynczym FK. Nie pozwalaj na dwa priorytety. Nie usuwaj provenance po imporcie. Nie kopiuj `Może kiedyś` do tagów dokumentu. Nie pozwalaj Bielikowi tworzyć grup ani sugerować priorytetów. Nie przypisuj sugestii przed akceptacją. Nie zmieniaj kontraktu odpowiedzi `/url_add`. Zachowaj wszystkie niezwiązane zmiany worktree.

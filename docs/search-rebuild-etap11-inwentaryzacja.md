# Etap 11 — inwentaryzacja fizycznych rename'ów schematu

Data pomiaru: 2026-07-19 (main = `e5f5ad1`). Plan: [search-rebuild-implementation-plan.md](search-rebuild-implementation-plan.md), sekcja 3 i 7 (Etap 11). Decyzje nazewnicze: [ADR-017](adr/adr-017-search-rebuild-scope-decisions.md).

Wszystkie liczby zmierzone ripgrepem na czystym repo (z poszanowaniem `.gitignore` — wcześniejsze
pomiary „79 plików" łapały venvy). Fizyczny schemat potwierdzony przez `\d web_documents`
na bazie NAS (192.168.200.7:5434) 2026-07-19.

## Kluczowe ustalenie: podział podetap 1 vs 2

Plan grupuje `date_from/author/project/source` w jeden podetap 1 („proste rename'y").
Stan fizyczny bazy NAS rozstrzyga inaczej:

| Pole | Stan fizyczny (NAS) | Wniosek |
|---|---|---|
| `date_from` (date) + `date_from_source` (varchar 10, CHECK manual/llm) | zwykłe kolumny + indeks `idx_web_documents_date_from` + CHECK `ck_web_documents_date_from_source` | **prosty rename** — podetap 1 |
| `author` (text) + `author_source` (varchar 10, CHECK manual/llm/html) | zwykłe kolumny + CHECK `ck_web_documents_author_source` | **prosty rename** — podetap 1 |
| `project` (varchar 100) | zwykła kolumna + indeks `idx_web_documents_project`; **100% NULL** (9220 dok., ADR-017); brak tabeli `collections` | docelowe `collection_id` wymaga NOWEJ tabeli + FK → **podetap 2** (normalizacja), nie prosty rename |
| `source` (text) | **ma już FK** `fk_source` → `sources(name)` ON UPDATE CASCADE + indeks `idx_web_documents_source`; tabela `sources` ma kolumnę `id` | docelowe `discovery_source_id` = przejście z klucza po nazwie na klucz po id → **podetap 2** (migracja danych name→id + zmiana API `/sources` + wtyczka Chrome) |

Podetap 1 zostaje więc zawężony do dwóch par: `date_from`→`published_on` (+`date_from_source`→`published_on_method`)
oraz `author`→`byline` (+`author_source`→`byline_method`).

## 1. `date_from` → `published_on`, `date_from_source` → `published_on_method`

Obiekty DB: kolumny `web_documents.date_from`, `web_documents.date_from_source`,
indeks `idx_web_documents_date_from`, constraint `ck_web_documents_date_from_source`.

Backend — 23 pliki / 99 wystąpień, z czego aktywne:

| Warstwa | Pliki | Charakter |
|---|---|---|
| ORM | `library/db/models.py` | definicje `Mapped`, komentarze, `to_dict()` (klucze JSON) |
| API /chunks + dokument | `library/chunk_review_routes.py` (22) | odpowiedzi GET (klucze `date_from`, `date_from_source`), **endpoint `POST /document/<id>/date_from`** (ścieżka URL!), `POST /analysis_run/<id>/extract_publication_date` (klucze odpowiedzi) |
| Repozytorium | `library/stalker_web_documents_db_postgresql.py` (8) | `get_last_by_source()`, select w `get_similar()`/`search_text()`, mapy sortowania `SearchSort.PUBLISHED_*`, klucze dictów odpowiedzi |
| Serwis wyszukiwania | `library/search_service.py` (4) | klucze sortowania scalonych wyników (payload `/website_similar` i `/search`) |
| Filtry SQL | `library/search/sql_filters.py` (2) | mapowanie `filters.published_on_*` → `WebDocument.date_from` (docelowe nazwy filtrów JUŻ istnieją) |
| `library/search/types.py` (4) | tylko lokalne nazwy zmiennych w `normalize_date_range()` — kosmetyka, nie kontrakt |
| Serwis dokumentów | `library/document_service.py` (1) | docstring `**metadata` |
| Importy | `imports/feed_monitor.py` (4) | ustawianie `doc.date_from` z pub_date, `metadata["date_from"]` |
| Testy | `test_unknown_news_import_orm` (9), `test_list_by_filters` (8), `test_orm_crud` (4), `test_db_models` (4), `test_search_service` (3), `test_similarity_search_orm` (2), `test_document_analysis_book_mode` (2), `test_search_sql_filters` (1), `test_document_service` (1), `test_flask_endpoints_orm` (1) | atrybuty ORM + klucze JSON |
| Init SQL | `database/init/03-create-table.sql` (2) | kolumna + indeks |
| Dokumentacja | `backend/database/CLAUDE.md` (3), `backend/library/CLAUDE.md` (1), `docs/data-models-backend.md`, `docs/api-type-sync-strategy.md` | opisy |
| NIE ruszać | `alembic/versions/b1c2d3e4f5a6_*` (historia migracji), `test_code/gcloud_firestore_example.py` (eksperyment) | — |

Klienci:

| Klient | Pliki | Charakter |
|---|---|---|
| `web_interface_react` | `utils.tsx` (3: typ elementu listy + wyświetlanie 📅), `read.tsx` (1), `chunks.tsx` (20: stany, fetch `POST /document/<id>/date_from`, obsługa `extract_publication_date`) | klucze JSON + ścieżka endpointu |
| `shared/` | **0** — `WebDocument` w `types/documents.ts` nie ma `date_from` | brak zmian |
| `web_interface_app2` | **0** (potwierdzone ponownie: trafienia to style SCSS/fontawesome, nie pole) | brak zmian |
| Wtyczka Chrome | **0** | brak zmian |
| AWS Lambda (`infra/aws/serverless`) | **0** | brak zmian |
| slack_bot | **0** | brak zmian |

Rozmiar: **1 sesja** (migracja + backend + 3 pliki reacta + docs + deploy NAS). Dotyka
API (ścieżka `POST /document/<id>/date_from` i klucze JSON w `/website_list`, `/website_similar`,
`/search`, `/chunks`), więc backend i frontend muszą wejść w jednym PR.

## 2. `author` → `byline`, `author_source` → `byline_method`

Obiekty DB: kolumny `web_documents.author`, `web_documents.author_source`,
constraint `ck_web_documents_author_source`. (Bez indeksu.)

Backend — grep zawężony (`\.author\b|"author"|author=`): 39 plików / 139 wystąpień, ale duża
część to **inne pojęcia**, których NIE wolno przemianować:

- `document_persons.role='author'` — relacyjny model autorów (zostaje, to docelowy model);
- `ner_exclusions.author` + `scope='author'` (`server.py`, `entity_service.py`, init `24-create-ner-exclusions.sql`) — przechowuje nazwę autora dokumentu jako klucz reguły; **decyzja do podjęcia**: zostawić (rekomendacja: tak, osobna tabela, osobny kontrakt API) czy przemianować w podetapie 5/6;
- `author_service.py` / `article_metadata.py` / `author_biography.py` — logika wykrywania autora: zmienia się tylko tam, gdzie dotyka `doc.author`/`author_source` i kluczy JSON;
- `information_sources` role author — inne pojęcie (proweniencja), zostaje.

Realnie dotknięte warstwy: `db/models.py`, `chunk_review_routes.py` (6: odpowiedzi + **endpoint
`POST /document/<id>/author`** + `POST /analysis_run/<id>/extract_author`), `author_service.py`
(`set_document_authors(..., source=...)` ustawia `doc.author`/`author_source`),
`stalker_web_documents_db_postgresql.py` (select + dicty), `server.py` (`/website_save`/`/website_get`),
`search/sql_filters.py` (fallback byline w filtrze autora — nazwa docelowa już w komentarzach),
importy: `dynamodb_sync.py`, `youtube_backfill_author.py`, `article_browser.py`,
`youtube_processing.py`, `stalker_youtube_file.py`, `document_analysis_service.py`; testy:
`test_author_service`, `test_article_metadata`, `test_orm_crud`, `test_db_models`,
`test_flask_endpoints_orm`, `test_list_by_filters`, `test_repository_queries`; init SQL
`03-create-table.sql`; docs (CLAUDE.md x2, `data-models-backend.md`).

Klienci: `shared/types/documents.ts` (pole `author` w `WebDocument` + `emptyDocument`) → oba
frontendy; react: `sharedInputs.tsx` (7 — pole formularza editorów link/webpage/youtube/movie/email),
`chunks.tsx` (15 — panel autora), `list.tsx`, `useManageLLM.ts`; wtyczka Chrome: **0** (nie wysyła
author); Lambda `app-server-db/lambda_function.py` (2 — `web_document.author` z parsera; lambdy
zdekomisjonowane 2026-07-02, zmiana tylko dla spójności, bez deployu).

Rozmiar: **1 sesja** (większy zasięg frontendowy niż `date_from` przez `shared/` + editory,
ale zero pracy w wtyczce i mniejsza liczba miejsc w repozytorium).

## 3. `project` → `collection_id` (podetap 2 — normalizacja)

Stan: kolumna 100% NULL, indeks `idx_web_documents_project`, brak tabeli `collections`.
Wymaga: utworzenia `collections` (id, name, …), dodania `collection_id` FK, usunięcia `project`
(bez migracji danych — pusta), aktualizacji API (`/website_list?project=`, `get_similar(project=)`,
`search_text(project=)` — parametr publiczny!).

Backend (grep zawężony): 21 plików / 69 wystąpień; aktywne głównie:
`stalker_web_documents_db_postgresql.py` (12: parametry `project=` w `get_list`/`get_similar`/`search_text` + where + dicty),
`db/models.py`, `document_service.py` (metadata), `search_service.py` (parametr `project`),
`search/sql_filters.py`, `server.py` (parametry requestów), testy (10 plików).
UWAGA na fałszywe trafienia: `imports/dynamodb_sync.py` `--project` = kod projektu SSM (`lenie`),
NIE kolumna; `PROJECT_CODE` w configu — nie dotykać.
Klienci: brak w shared/ i react (pole nie jest edytowane w UI); wtyczka: 0.

## 4. `source` → `discovery_source_id` (podetap 2 — normalizacja)

Stan: `source` text z FK po **nazwie** do `sources(name)` (ON UPDATE CASCADE, PR #247),
tabela `sources` ma już `id`. Wymaga: dodania `discovery_source_id` FK→`sources.id`, migracji
danych `UPDATE ... SET discovery_source_id = s.id FROM sources s WHERE source=s.name`,
usunięcia starej kolumny i `fk_source`, przebudowy hooka `before_flush` (auto-create źródła)
i API `/sources` (cascade rename przestaje być potrzebny po przejściu na id).

Backend (grep zawężony): 36 plików / 114 wystąpień; duży szum od innych pojęć — **NIE ruszać**:
`information_sources` (proweniencja, `server.py` ~15 trafień), `DocumentRemovedLine.source`
(manual/szum_chunk), `date_from_source`/`author_source` (osobne rename'y),
`set_document_authors(source=)` (metoda ustalenia), `SearchFilters.discovery_source` (już docelowe).
Realnie dotknięte: `db/models.py` (kolumna + hook + relacja), `server.py` (`/sources` CRUD,
`/url_add` default `"own"`, `_source_doc_count`), `stalker...` (`get_last_by_source`),
`search/sql_filters.py` (filtr discovery source), importy (`feed_monitor`, `dynamodb_sync`
`metadata["source"]`, `youtube_add`, `article_browser`, `email_import`), `mcp_server/tools/lenie.py`,
testy (`test_flask_endpoints_sources_crud` 10, `test_flask_endpoints_tags_sources`, inne),
init SQL `28-create-sources.sql` + `03-create-table.sql`.
Klienci: **wtyczka Chrome `popup.js`** (~35: dropdown źródła, `GET /sources?active=1`, payload
`source` w `/url_add`, cache lokalny) — największy klient tego pola; `shared/types/documents.ts`
(`source` w `WebDocument`, interfejs `Source`); react `sources.tsx` (strona zarządzania) i editory;
Lambda `url-add` (DynamoDB, pole `source` w itemach — dane historyczne w DynamoDB zachowują
starą nazwę pola, `dynamodb_sync.py` musi mapować).

## 5. `website_id` → `document_id` (podetap 3)

`websites_embeddings.website_id` FK. Backend: 20 aktywnych plików (m.in. `db/models.py`,
`stalker...` 13, `search_service.py` 5, `server.py`, `document_analysis_service.py`, batch
`web_documents_do_the_needful_new.py` 17, testy ~8 plików). Klienci: `shared/types` (`SearchResult.website_id`),
react (`utils.tsx`, `search.tsx`, `useManageLLM.ts` 9), slack_bot (`test_search_formatter.py` —
sprawdzić też src), Lambda `app-server-db`. Zależny od decyzji czy robić razem z rename tabeli
`websites_embeddings` → `document_embeddings` (rekomendacja: tak, jedna migracja).

## 6. `web_documents` → `documents` (podetap 4 — największy)

92 pliki / 300 wystąpień w backendzie, z czego ~30 to historia Alembic (**nie ruszać** —
migracje historyczne odwołują się do nazwy tabeli z czasu ich powstania) i ~25 init SQL
(FK w `REFERENCES web_documents(id)` w 15+ plikach init). Aktywny kod: `db/models.py`
(`__tablename__` + 15 FK w innych modelach), testy, `alembic/env.py`. Wymaga jednej migracji
`ALTER TABLE ... RENAME` (FK w PostgreSQL podążają za rename automatycznie, ale nazwy
constraintów zostają stare — decyzja: przemianować constrainty czy zostawić). Dotyka też
`documents ts`/dokumentacji szeroko. **Osobna sesja wyłącznie na to.**

## 7. Pozostałe (podetap 5): `document_state`/`document_state_error`/`created_at`/`uuid`

Nie mierzone szczegółowo w tej inwentaryzacji (poza skalą: `document_state` jest w shared/,
obu frontendach, wtyczce i większości backendu). Zmierzyć przed właściwą sesją.

## Rekomendowana kolejność sesji Etapu 11

1. **11a**: `date_from`→`published_on` + `date_from_source`→`published_on_method` — **WYKONANE w tej samej sesji** (migracja `a2b3c4d5e6f7`, wdrożone na NAS; szczegóły we wpisie 2026-07-19 w [dzienniku](search-rebuild-progress.md)).
2. **11b**: `author`→`byline` + `author_source`→`byline_method` — **WYKONANE** (migracja `b3c4d5e6f7a8`, wdrożone na NAS; `ner_exclusions.author` zostaje bez zmian — osobna tabela z własnym kontraktem).
3. **11c**: `project`→`collection_id` — **WYKONANE** (migracja `c4d5e6f7a8b9`: tabela `collections` + FK, kolumna `project` usunięta; legacy kwarg `project` usunięty z repozytorium — żaden endpoint HTTP go nie przyjmował).
4. **11d**: `source`→`discovery_source_id` + `sources`→`discovery_sources` — **WYKONANE** (migracja `d5e6f7a8b9c0` z bezstratną migracją danych 9110 dokumentów; format wire zachowuje NAZWĘ pod `source` — wtyczka Chrome bez zmian; hook `before_flush` zastąpiony jawnym `WebDocument.set_discovery_source()`).
5. **11e**: `websites_embeddings`→`document_embeddings` + `website_id`→`document_id` — **WYKONANE** (migracja `e6f7a8b9c0d1`: tabela+kolumna+indeksy+constrainty; klucze API `document_id` w wynikach wyszukiwania; `shared/types.SearchResult`, react, slack_bot fixture).
6. **11f**: `web_documents`→`documents` + FK — **WYKONANE** (migracja `f7a8b9c0d1e2`; klasa `WebDocument`→`Document` w ORM i TS; historia Alembic i nazwy plików skryptów batch celowo nietknięte; moduł `stalker_web_documents_db_postgresql`/klasa `WebsitesDBPostgreSQL` przeniesione do 11g).
7. **11g**: `document_state`→`processing_status`, `created_at`→`ingested_at`, `uuid`→`public_id`, `website_similar`→usunięcie (po Etapie 12?), usunięcie aliasów zgodności.

Każda sesja: migracja Alembic (upgrade→psql→downgrade→upgrade na NAS), pełna suita unit,
ruff, deploy NAS bezpośrednio po migracji, E2E `/search` + frontend, wpis w dzienniku.

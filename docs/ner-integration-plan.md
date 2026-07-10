# Integracja NER z backendem i UI — plan wdrożenia

> Plan integracji istniejącego mikroserwisu NER ([`ner_service/`](../ner_service/README.md),
> spaCy `pl_core_news_lg`) z backendem, bazą danych i interfejsem React tak, aby **przy
> notatce (dokumencie) było widać wykryte osoby i miejsca**. Spina w całość dwa istniejące
> plany: [`geo-place-ner-plan.md`](geo-place-ner-plan.md) (miejsca) i
> [`person-ner-plan.md`](person-ner-plan.md) (osoby), dodając brakującą warstwę
> integracyjną i przyrostową kolejność wdrożenia.
>
> **Status:** WSZYSTKIE ETAPY 1-4 ZAIMPLEMENTOWANE (2026-07-10).
> **Ostatnia aktualizacja:** 2026-07-10

## Punkt wyjścia (stan na 2026-07-10)

Zaimplementowany był wyłącznie sam silnik NER:

- [`ner_service/`](../ner_service/README.md) — mikroserwis HTTP (`POST /ner`) opakowujący
  spaCy `pl_core_news_lg`, zwraca encje `persName` / `geogName` / `placeName` / `orgName`
  z pozycjami w tekście. Wdrożony na NAS (`infra/docker/compose.nas.yaml`, kontener
  `lenie-ner-service:8090`, tylko sieć `lenie-net`, bez portu na hoście) i w lokalnym
  compose pod profilem `ner`.

Backend nie miał żadnej integracji: nic nie wołało serwisu, nie było tabel na encje,
tagów `miejsce-*` ani niczego w UI.

## Strategia: najpierw widoczna wartość, potem weryfikacja

Pełne pipeline'y z obu planów (weryfikacja Nominatim/LocationIQ dla miejsc,
disambiguacja Wikidata + rejestr osób) są duże i wymagają decyzji zewnętrznych
(konto LocationIQ, model danych osób). Zamiast czekać na nie, wdrażamy przyrostowo:

1. **Etap 1-2 (MVP)** — surowe encje NER zapisane w bazie i widoczne przy dokumencie.
2. **Etap 3** — miejsca: weryfikacja + tagi `miejsce-*` + współrzędne pod mapę.
3. **Etap 4** — osoby: pełny model relacyjny (`persons`/`person_aliases`/`document_persons`).

## Etap 1 — klient NER w backendzie ✅ (2026-07-10)

- [`backend/library/ner_client.py`](../backend/library/ner_client.py) —
  `extract_entities(text)` woła `POST {NER_SERVICE_URL}/ner`;
  `aggregate_entities(entities)` grupuje wzmianki po lemacie (odmiana „Tuska" →
  „Tusk") i typie, zliczając wystąpienia.
- Konfiguracja: `NER_SERVICE_URL` przez config_loader (domyślnie
  `http://lenie-ner-service:8090`), wpis w
  [`scripts/vars-classification.yaml`](../scripts/vars-classification.yaml).
- Graceful degradation: serwis niedostępny → pusta lista + warning w logu,
  pipeline analizy działa dalej.
- Timeout 120 s — pierwsze wywołanie po restarcie kontenera ładuje model
  (do ~90 s na NAS), kolejne są sub-sekundowe.
- `ner_service` rozszerzony o pole `lemma` w odpowiedzi (`ent.lemma_`) — kluczowe
  dla polskiej odmiany przy grupowaniu wzmianek.

## Etap 2 — MVP: encje w bazie i przy notatce ✅ (2026-07-10)

- Tabela **`document_entities`** (init
  [`21-create-document-entities.sql`](../backend/database/init/21-create-document-entities.sql),
  migracja Alembic, model ORM `DocumentEntity`): `document_id` FK, `entity_type`
  (`persName`/`geogName`/`placeName`), `entity_text` (forma bazowa/lemat),
  `mention_count`, `created_at`, UNIQUE na `(document_id, entity_type, entity_text)`.
  Świadomie **bez disambiguacji** — to poczekalnia przed modelami z etapów 3-4.
- [`backend/library/entity_service.py`](../backend/library/entity_service.py) —
  `refresh_document_entities(session, doc, text)`: NER → agregacja → zastąpienie
  wierszy dokumentu (encje to dane pochodne, refresh = replace).
- Zasilanie z tych samych punktów co tagowanie krajów:
  - `document_analysis_service.create_run()` — po `_apply_tags()`,
  - `imports/article_browser.py` — przy `[w]rite to db` oraz nowa akcja `[e]ncje`.
- API (`server.py`):
  - `GET /website_entities?id=<doc_id>` — encje z bazy, pogrupowane po typie,
  - `POST /website_entities` (`id=<doc_id>`) — odśwież na żądanie (woła NER) i zwróć.
- UI (`web_interface_react`): komponent `EntitiesPanel` w edytorach dokumentów
  (webpage/youtube/movie) — chipy „Osoby" (`persName`) i „Miejsca"
  (`geogName`+`placeName`) z licznikiem wystąpień + przycisk „Wykryj osoby i miejsca".

Ograniczenia MVP (świadome):

- Grupowanie po lemacie spaCy nie jest doskonałe (rzadkie nazwiska mogą się nie
  zlemmatyzować — wtedy warianty odmiany zostają osobno).
- Brak rozróżnienia dwóch osób o tym samym nazwisku (rozwiązuje etap 4).
- Brak weryfikacji, czy `geogName` to realne miejsce (rozwiązuje etap 3).

## Etap 3 — miejsca: weryfikacja, tagi `miejsce-*`, mapa ✅ (2026-07-10)

Zgodnie z [`geo-place-ner-plan.md`](geo-place-ner-plan.md):

- [`backend/library/locationiq_client.py`](../backend/library/locationiq_client.py) —
  klient LocationIQ (klucz `LOCATIONIQ_API_KEY` z Vault, rate limit 2 zap./s,
  graceful degradation, `accept-language=pl,en` — bez tego `display_name` wraca
  po angielsku i podobieństwo nazw odrzucało „Kijów" vs „Kyiv") z **kontrolą
  jakości dopasowania** `is_plausible_match()`: fuzzy-podobieństwo zapytania do
  części `display_name` (bez diakrytyków, próg 0.75) **+ allowlista klas OSM**
  (natural/water/waterway/place/boundary/landuse — odrzuca np. stację kolejową
  „Shahed" w Szirazie dopasowaną do nazwy drona) — patrz „Ustalenie z testu
  klucza" niżej, dlaczego HTTP 200 nie wystarcza.
- Tabela **`geocode_cache`** (init `22-create-geocode-cache.sql`, Alembic
  `a3b4c5d6e7f8`, ORM `GeocodeCache`) — jedna próba geokodowania per unikalny
  string, cache'owane też wyniki negatywne; kolumna `document_entities.geocode_id`.
- [`backend/library/place_verification.py`](../backend/library/place_verification.py) —
  `verify_document_places()`: kandydaci `geogName`/`placeName` → geokoder (przez
  cache) → LLM potwierdza istotność (`article_tagging.confirm_places_with_llm`,
  wzorzec `extract_countries_hybrid`) → tagi **`miejsce-<slug>`** w `doc.tags`.
  **Kraje są pomijane** (mają własny pipeline `kraj-*`; geokodowanie ich paliłoby
  limit API bez pożytku) — filtr przez `country_gazetteer.detect_countries()`.
- Wpięcie: `document_analysis_service.create_run()` (krok 11d),
  `article_browser.py` (`[w]` krok 2c i `[e]ncje` z ✓ przy zweryfikowanych),
  `POST /website_entities` (weryfikacja po odświeżeniu, zwraca `place_tags`).
- UI: `EntitiesPanel` — zielony chip z ✓ i tooltipem `display_name` dla
  zweryfikowanych, wyszarzenie dla odrzuconych przez geokoder; `CountryMap`
  (widok `/read/:id`) — pomarańczowe markery punktowe zweryfikowanych miejsc
  (`GET /website_entities` → `lat`/`lon`).

**Ustalenie z testu klucza (2026-07-10):** popularne polskie egzonimy
rozwiązują się poprawnie („Kijów" → Kyiv, „Morze Czerwone" → Red Sea), ale
rzadsze dają **fałszywe dopasowania fuzzy** zamiast braku wyniku — „Cieśnina
Ormuz" zwróciła „Płytka Cieśnina" k. Iławy. Weryfikacja w etapie 3 nie może
więc traktować samego HTTP 200 jako potwierdzenia: trzeba sprawdzić jakość
dopasowania (podobieństwo zwróconej nazwy do zapytania, `importance`,
`class`/`type` — np. water/strait/sea dla `geogName`) i/lub odpytywać
angielską nazwą (LLM i tak uczestniczy w kroku oceny istotności — może przy
okazji tłumaczyć nazwę).

## Etap 4 — osoby: model relacyjny ✅ (2026-07-10)

Zgodnie z [`person-ner-plan.md`](person-ner-plan.md):

- Tabele **`persons` / `person_aliases` / `document_persons`** (init
  `23-create-persons-tables.sql`, Alembic `b4c5d6e7f8a9`, ORM `Person`/
  `PersonAlias`/`DocumentPerson`; indeksy pg_trgm na nazwach/aliasach).
- [`backend/library/wikidata_client.py`](../backend/library/wikidata_client.py) —
  `search_persons(name)`: wbsearchentities + wbgetentities, **tylko encje-ludzie
  (P31=Q5)** — dron „Shahed" czy „Starlinek" nie przejdą; opisy kandydatów są
  kontekstem do disambiguacji.
- [`backend/library/person_registry.py`](../backend/library/person_registry.py) —
  `resolve_document_persons()`: kaskada per wzmianka `persName`:
  1. dokładny alias/nazwa kanoniczna → `alias_matched` (bez sieci),
  2. Wikidata + `article_tagging.confirm_person_with_llm()` (LLM wybiera QID z
     zamkniętej listy kandydatów po opisach, może odpowiedzieć NONE — np.
     Donald Tusk polityk Q946 vs jego ojciec Q17278182) → `wikidata_matched`,
  3. **junk guard**: jednowyrazowa wzmianka bez człowieka w Wikidacie jest
     pomijana (szum spaCy: „Hornet", „Starlinek"),
  4. fuzzy pg_trgm po rejestrze (próg 0.5) → `manual_review` (nigdy auto-merge),
  5. nowa osoba bez wpisu w Wikidacie → `persons` bez QID + `manual_review`.
- Wpięcie: `create_run()` krok 11e, `article_browser.py` (`[w]` krok 2d, `[e]`,
  v0.6.0), `POST /website_entities` (zwraca `persons_linked`).
- API: `GET /persons?q=` (fuzzy szukanie w rejestrze), `GET /person_documents?id=`
  („wszystkie artykuły o osobie X" — cel użytkownika), elementy `persName` w
  `GET /website_entities` niosą `person_id`/`canonical_name`/`person_description`/
  `wikidata_qid`/`confidence`.
- UI: `EntitiesPanel` — niebieskie chipy rozpoznanych osób (✓ lub „?" przy
  `manual_review`), tooltip: nazwa kanoniczna | opis | QID | confidence.
- Surowe wiersze `persName` w `document_entities` pozostają (wejście do
  ponownej disambiguacji przy refreshu) — plan zakładał ich usunięcie, ale są
  potrzebne jako kandydaci przy każdym kolejnym `resolve`.

## Kolejność i zależności

| Etap | Zależy od | Decyzje zewnętrzne | Status |
|---|---|---|---|
| 1. Klient NER | działający `ner_service` | — | ✅ 2026-07-10 |
| 2. MVP `document_entities` + UI | etap 1 | — | ✅ 2026-07-10 |
| 3. Miejsca (LocationIQ + tagi + mapa) | etap 2 | konto LocationIQ ✅, namespace: `miejsce-*` | ✅ 2026-07-10 |
| 4. Osoby (model relacyjny) | etap 2 | confidence: enum 4 wartości; Wikidata REST API | ✅ 2026-07-10 |

## Kontynuacja: UI osób (2026-07-10, po zamknięciu planu)

- **Kolejka `manual_review`**: `GET /persons_review` (wpisy z kontekstem
  dokumentu) + `PATCH /persons_review/<link_id>` z akcjami `approve`
  (→ `manual_confirmed`), `reject` (usuwa link; osierocona osoba znika
  z rejestru) i `merge` (przepięcie linku na wskazane `target_person_id`
  + aliasy: surowa wzmianka i nazwa kanoniczna źródła; duplikat linku w tym
  samym dokumencie jest usuwany). Logika:
  [`backend/library/person_registry.py`](../backend/library/person_registry.py)
  (`list_manual_review`, `approve/reject/merge_review_link`).
- **Frontend** (`web_interface_react`): strona `/persons-review` (lista wpisów,
  przyciski Zatwierdź / Odrzuć / Scal z wyszukiwarką osoby docelowej) oraz
  `/persons/:id?` (wyszukiwarka rejestru + lista artykułów osoby z linkami do
  edytora i widoku `/read/:id`); obie pozycje w nawigacji Layoutu.

Możliwe dalsze kroki (poza zakresem planu): self-hosted geokoder (Photon)
gdyby limit LocationIQ przestał wystarczać.

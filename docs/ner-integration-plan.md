# Integracja NER z backendem i UI — plan wdrożenia

> Plan integracji istniejącego mikroserwisu NER ([`ner_service/`](../ner_service/README.md),
> spaCy `pl_core_news_lg`) z backendem, bazą danych i interfejsem React tak, aby **przy
> notatce (dokumencie) było widać wykryte osoby i miejsca**. Spina w całość dwa istniejące
> plany: [`geo-place-ner-plan.md`](geo-place-ner-plan.md) (miejsca) i
> [`person-ner-plan.md`](person-ner-plan.md) (osoby), dodając brakującą warstwę
> integracyjną i przyrostową kolejność wdrożenia.
>
> **Status:** etapy 1-2 ZAIMPLEMENTOWANE (2026-07-10), etapy 3-4 do zrobienia.
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

## Etap 3 — miejsca: weryfikacja, tagi `miejsce-*`, mapa (do zrobienia)

Zgodnie z [`geo-place-ner-plan.md`](geo-place-ner-plan.md):

- Weryfikacja kandydatów `geogName`/`placeName` przez **LocationIQ free tier**
  (5 000 zapytań/dzień) z cache'em wyników w bazie (nazwa → istnieje/nie +
  współrzędne), potem LLM potwierdza istotność (wzorzec `extract_countries_hybrid`).
- Zweryfikowane miejsca → tagi `miejsce-*` w `doc.tags` + zapis współrzędnych.
- UI: frontend ma już `CountryMap` (mapa z tagów `kraj-*`) — punkty miejsc ze
  współrzędnymi nanosimy na tę samą mapę.

Wymaga: konto LocationIQ (weryfikacja cennika), decyzja o namespace tagów
(`miejsce-*` vs `geo-*`), tabela cache geokodowania.

## Etap 4 — osoby: model relacyjny (do zrobienia)

Zgodnie z [`person-ner-plan.md`](person-ner-plan.md):

- Tabele `persons` / `person_aliases` / `document_persons` (pg_trgm już w bazie),
  disambiguacja przez Wikidata QID, fallback na wewnętrzny rejestr, LLM rozstrzyga
  niejednoznaczności, kolejka `manual_review`.
- Migracja danych: wiersze `document_entities` z `entity_type='persName'`
  stają się wejściem do disambiguacji i zasilają `document_persons`;
  po migracji `persName` znika z `document_entities` (miejsca zostają do etapu 3).
- UI panelu osób przełącza się z surowych stringów na linki do encji `persons`
  („wszystkie artykuły o osobie X").

## Kolejność i zależności

| Etap | Zależy od | Decyzje zewnętrzne | Status |
|---|---|---|---|
| 1. Klient NER | działający `ner_service` | — | ✅ 2026-07-10 |
| 2. MVP `document_entities` + UI | etap 1 | — | ✅ 2026-07-10 |
| 3. Miejsca (LocationIQ + tagi + mapa) | etap 2 | konto LocationIQ, namespace tagów | do zrobienia |
| 4. Osoby (model relacyjny) | etap 2 | format `confidence`, klient Wikidata | do zrobienia |

Etapy 3 i 4 są od siebie niezależne — można je robić w dowolnej kolejności.
Brak wpisu w backlogu (`_bmad-output/planning-artifacts/epics/backlog.md`) —
dodać etapy 3-4 jako osobne zadania przy gotowości do implementacji.

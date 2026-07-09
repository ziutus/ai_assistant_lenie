# Rozpoznawanie osób w tekstach (NER) i przeprojektowanie bazy pod wyszukiwanie po osobach — plan na przyszłość

> Plan techniczny: jak wykrywać w treści artykułów imiona i nazwiska osób,
> łączyć wzmianki tej samej osoby między artykułami (entity resolution) i
> jak w tym celu przeprojektować bazę danych, żeby dało się wyszukiwać
> "wszystkie artykuły o osobie X" — analogicznie do istniejącego planu dla
> miejsc geograficznych ([`docs/geo-place-ner-plan.md`](geo-place-ner-plan.md)),
> ale z dodatkowym, trudniejszym problemem: identyfikacja osoby nie jest
> faktem deterministycznym (istnieje/nie istnieje), tylko wymaga disambiguacji.
>
> **Status:** plan / do przemyślenia — nieprzypisane do backlogu, nic nie zaimplementowane.
> **Ostatnia aktualizacja:** 2026-07-09

## Problem

Obecnie `web_documents.tags` to pojedyncza kolumna `text` z tagami
oddzielonymi przecinkami (patrz [`backend/database/CLAUDE.md`](../backend/database/CLAUDE.md)),
zasilana przez `article_tagging.py` (kategorie tematyczne, `kraj-*` przez
`extract_countries_hybrid()`). Nie ma dziś żadnej struktury reprezentującej
**osobę** jako encję — nie da się zapytać "pokaż wszystkie artykuły, w
których występuje Jan Kowalski" inaczej niż przez `LIKE '%kowalski%'` na
tekście artykułu, co nie rozróżnia różnych osób o tym samym nazwisku, nie
łapie wariantów zapisu (odmiana, inicjały) i nie skaluje się do sensownych
zapytań analitycznych (np. "które osoby pojawiają się najczęściej razem w
jednym temacie").

## Dlaczego namespace w `tags` (jak `kraj-*`) tu nie wystarczy

Dla krajów wzorzec `kraj-<slug>` w płaskiej kolumnie `tags` działa dobrze,
bo kraje są zamkniętą listą ~190 elementów ze stabilnymi, jednoznacznymi
slugami (`country_gazetteer.py`). Dla osób ten sam wzorzec (`osoba-jan-kowalski`)
ma dwie fundamentalne wady:

1. **Kolizje nazwisk.** Dwóch różnych "Jan Kowalski" (polityk lokalny i
   inny polityk lokalny) dostałyby ten sam slug — tagowanie po stringu
   nazwiska łączy ich w jedną (fałszywą) tożsamość.
2. **Brak miejsca na metadane potrzebne do wyszukiwania.** Nie da się
   przechować aliasów ("J. Kowalski", odmiana "Kowalskiego"), identyfikatora
   zewnętrznego (Wikidata QID) ani poziomu pewności dopasowania w płaskiej
   kolumnie tekstowej bez re-parsowania jej za każdym razem.

Innymi słowy: dla krajów `tags` wystarcza, bo problem sprowadza się do
*klasyfikacji* (czy dany, znany z góry kraj jest omawiany). Dla osób problem
to *identyfikacja encji* (która to dokładnie osoba) — to wymaga osobnej
tabeli z kluczem obcym, nie stringa w tekście.

## Proponowany pipeline: NER → disambiguacja → LLM ocenia trafność

Ten sam trzystopniowy wzorzec co dla miejsc, z inną metodą weryfikacji w
kroku 2 (dla osób nie ma odpowiednika "sprawdź w OSM, czy istnieje" —
zamiast tego jest disambiguacja do konkretnej encji):

1. **NER** — `spaCy pl_core_news_lg` już wykrywa `persName` (ten sam model,
   który plan geograficzny rekomenduje dla `geogName`/`placeName` — jeśli
   zostanie wdrożony, ekstrakcja osób jest "przy okazji", bez nowego modelu).
   Tani, offline, kandydaci na wzmianki osób w tekście.
2. **Disambiguacja** — dla każdego kandydata:
   - Najpierw próba dopasowania do **Wikidata** (REST/SPARQL, darmowe) —
     encje osób mają tam ustrukturyzowane atrybuty (zawód, daty, powiązane
     organizacje) i stabilny identyfikator **QID**, naturalny odpowiednik
     roli Nominatim dla miejsc.
   - Gdy Wikidata nie zwraca trafienia (osoba nieobecna w Wikipedii/Wikidata —
     częsty przypadek dla lokalnych/mniej znanych postaci): fallback na
     **wewnętrzny rejestr osób** (patrz niżej) — fuzzy match po istniejących
     rekordach (`pg_trgm`, już zainstalowany w bazie — patrz
     `02-create-extension.sql`) jako generator kandydatów.
3. **LLM ocenia trafność** — rozstrzyga, który kandydat (z Wikidaty lub
   wewnętrznego rejestru) pasuje do kontekstu artykułu, gdy nazwa jest
   niejednoznaczna (porównanie zawodu/funkcji/organizacji wymienionych w
   tekście z opisem kandydata). Analogicznie do `extract_countries_hybrid()`
   w [`article_tagging.py`](../backend/library/article_tagging.py) — LLM
   dostaje zamkniętą listę kandydatów do potwierdzenia, nie generuje
   odpowiedzi open-ended.

Dopasowania o niskiej pewności LLM **nie powinny być łączone automatycznie**
— trafiają do kolejki ręcznej weryfikacji, tym samym wzorcem co istniejący
manualny review w `imports/article_browser.py` i workflow `status` na
`document_chunks`/`document_analysis_runs` (`created` → `in_review` →
`reviewed`).

## Przeprojektowanie bazy: dedykowane tabele zamiast `tags`

Trzy nowe tabele, w stylu istniejącego wzorca `document_chunks` /
`document_analysis_runs` (serial PK, FK z `ON DELETE CASCADE`, `created_at`),
kolejny numerowany skrypt init (`21-create-persons-tables.sql`, po
`20-create-api-keys.sql` — patrz [`backend/database/CLAUDE.md`](../backend/database/CLAUDE.md)):

```sql
-- persons: kanoniczna encja osoby, jeden wiersz na realną osobę
CREATE TABLE persons (
    id serial PRIMARY KEY,
    uuid varchar(100) NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    canonical_name text NOT NULL,
    wikidata_qid varchar(20) UNIQUE,     -- NULL, gdy brak wpisu w Wikidata
    description text,                     -- zawód/funkcja — kontekst do disambiguacji
    created_at timestamp NOT NULL DEFAULT now()
);
CREATE INDEX idx_persons_canonical_name_trgm ON persons USING gin (canonical_name gin_trgm_ops);

-- person_aliases: warianty zapisu nazwiska/imienia prowadzące do tej samej osoby
-- (odmiana, inicjały, pseudonimy) — rosnąca w miarę napotykania kolejnych wzmianek
CREATE TABLE person_aliases (
    id serial PRIMARY KEY,
    person_id integer NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    alias text NOT NULL,
    UNIQUE (person_id, alias)
);
CREATE INDEX idx_person_aliases_alias_trgm ON person_aliases USING gin (alias gin_trgm_ops);

-- document_persons: powiązanie artykułu z osobą (many-to-many) + metadane ekstrakcji
CREATE TABLE document_persons (
    id serial PRIMARY KEY,
    document_id integer NOT NULL REFERENCES web_documents(id) ON DELETE CASCADE,
    person_id integer NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    raw_mention text NOT NULL,           -- dokładny string wykryty przez NER w tym artykule
    confidence varchar(20) NOT NULL,     -- wikidata_matched / llm_confirmed / manual_review / manual_confirmed
    created_at timestamp NOT NULL DEFAULT now(),
    UNIQUE (document_id, person_id)
);
CREATE INDEX idx_document_persons_document_id ON document_persons(document_id);
CREATE INDEX idx_document_persons_person_id ON document_persons(person_id);
```

Dzięki temu wyszukiwanie po osobie to zwykły JOIN, nie parsowanie tekstu:

```sql
-- wszystkie artykuły o danej osobie
SELECT wd.* FROM web_documents wd
JOIN document_persons dp ON dp.document_id = wd.id
WHERE dp.person_id = :person_id;

-- znajdź kandydatów na osobę po (fragmencie) nazwiska, z uwzględnieniem aliasów
SELECT DISTINCT p.* FROM persons p
LEFT JOIN person_aliases pa ON pa.person_id = p.id
WHERE p.canonical_name % :query OR pa.alias % :query;   -- operator pg_trgm
```

### Integracja z istniejącym kodem

- **ORM** (`backend/library/db/models.py`) — nowe klasy `Person`,
  `PersonAlias`, `DocumentPerson`, w stylu istniejących `DocumentChunk`,
  `DocumentAnalysisRun`.
- **Query layer** — nowy moduł `library/person_registry.py` (analogicznie do
  `country_gazetteer.py` dla wykrywania i `stalker_web_documents_db_postgresql.py`
  dla zapytań), z funkcjami typu `find_candidates(name)`, `resolve_or_create(name, wikidata_qid)`,
  `link_document(document_id, person_id, raw_mention, confidence)`.
- **Ekstrakcja** — nowy moduł `library/article_person_tagging.py`, wzorowany
  na `extract_countries_hybrid()` w `article_tagging.py`, wywoływany z tych
  samych miejsc: `article_browser.py` (akcja ręczna) i
  `document_analysis_service.py` → `_apply_tags()` (automatycznie po
  analizie chunków).
- **Manualny review** — status `manual_review` w `document_persons.confidence`
  jako kolejka do przejrzenia, wzorem `document_chunks.status`.

## `tags` (`osoba-*`) vs dedykowane tabele — rekomendacja

| | Namespace w `tags` (`osoba-*`) | Dedykowane tabele (`persons`/`person_aliases`/`document_persons`) |
|---|---|---|
| Rozróżnienie dwóch osób o tym samym nazwisku | **Nie** — ten sam slug | Tak — osobne wiersze `persons`, disambiguacja przez `description`/`wikidata_qid` |
| Aliasy/warianty zapisu | Nie (musiałby być osobny slug per wariant, gubi powiązanie) | Tak — `person_aliases` |
| Wydajne "wszystkie artykuły o osobie X" | Słabo — skan tekstu kolumny `tags` | Tak — indeksowany JOIN |
| Fuzzy wyszukiwanie po nazwisku | Nie | Tak — `pg_trgm` na `canonical_name`/`alias` |
| Złożoność implementacji | Niska (już istniejący wzorzec) | Średnia — 3 nowe tabele, nowy moduł ORM |

**Rekomendacja:** dla samego tagowania tematycznego (szybki filtr w UI)
namespace w `tags` byłby wystarczający, ale **cel użytkownika — wyszukiwanie
po osobach — wymaga dedykowanych tabel**. Bez klucza obcego do encji `persons`
nie da się poprawnie odróżnić dwóch osób o tym samym nazwisku ani
zagregować wzmianek tej samej osoby pisanej różnymi wariantami. `tags` zostaje
tym, czym jest dziś — tagowaniem tematycznym i krajów — a osoby dostają
własny, relacyjny model.

## Otwarte pytania / dalsze kroki

- Dokładny format `confidence` w `document_persons` — enum czy dowolny tekst? Do ustalenia przy implementacji.
- Czy `persons.description` powinien być jednym polem tekstowym, czy strukturą (zawód, data urodzenia, kraj) pobieraną z Wikidata przy dopasowaniu?
- UI: gdzie w `web_interface_react`/`article_browser.py` pokazywać listę osób per artykuł i kolejkę `manual_review`? Osobny temat, analogiczny do chunk review UI.
- Czy `document_persons.raw_mention` powinien przechowywać też pozycję w tekście (offset), żeby dało się podświetlić wzmiankę — na razie poza zakresem tego planu.
- Wybór biblioteki klienta Wikidata (REST vs SPARQL query service) — do zweryfikowania przy implementacji.
- Brak wpisu w backlogu (`_bmad-output/planning-artifacts/epics/backlog.md`) — dodać jako osobne zadanie, gdy będzie gotowość do implementacji.

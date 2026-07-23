# Globalny rejestr organizacji i aliasów NER — plan implementacji

> **Status:** DO IMPLEMENTACJI
> **Adresat:** Claude Code
> **Data:** 2026-07-23
> **Środowisko docelowe:** NAS (`192.168.200.7`)
> **Zakres:** organizacje `orgName`; bez przebudowy rejestru osób i miejsc

## Cel

Jednorazowe ręczne połączenie dwóch nazw organizacji ma działać globalnie:
w bieżącym dokumencie, w już zapisanych dokumentach oraz podczas następnych
uruchomień NER.

Przypadek referencyjny, dokument `9267`:

| Obecny rekord | Liczba | Warianty |
|---|---:|---|
| `Interia` | 2 | `Interii`, `Interią` |
| `Interii` | 2 | `Interii` |

Oczekiwany wynik:

| Organizacja kanoniczna | Liczba | Warianty/aliasy |
|---|---:|---|
| `Interia` | 4 | `Interii`, `Interią`, docelowo także `Interię` |

Obecne zachowanie jest błędem agregacji: NER już przekazuje `Interii` jako
wariant `Interia`, ale równocześnie tworzy drugi rekord kanoniczny `Interii`.

## Ważne rozróżnienie domenowe

- `DocumentEntity(entity_type="orgName")` oznacza organizację wspomnianą w
  tekście.
- `InformationSource` oznacza wydawcę albo źródło informacji.
- `DiscoverySource` oznacza sposób, w jaki użytkownik znalazł dokument.

Nie należy automatycznie utożsamiać każdej organizacji ze źródłem informacji.
Przykładowo NATO jest organizacją, ale nie musi być źródłem artykułu.
Powiązanie organizacji z `InformationSource` może zostać dodane później jako
jawne, opcjonalne FK; nie jest wymagane w tym zadaniu.

## Proponowany model danych

Dodać trzy tabele analogiczne do rejestru osób:

### `organizations`

- `id` — PK;
- `uuid` — stabilny identyfikator;
- `canonical_name` — nazwa wyświetlana, np. `Interia`;
- `description` — opcjonalnie;
- `organization_type` — opcjonalnie, np. `media`, `agency`, `company`,
  `institution`, `other`;
- `information_source_id` — opcjonalne FK, ale tylko jeśli implementacja
  rzeczywiście potrzebuje jawnego połączenia; nie dopasowywać po nazwie
  automatycznie;
- `created_at`, `updated_at`.

Indeks unikalny nie powinien opierać się wyłącznie na `canonical_name`,
ponieważ w przyszłości mogą istnieć różne organizacje o tej samej nazwie.
Na obecnym etapie można zastosować unikalność znormalizowanej nazwy, ale
trzeba opisać to ograniczenie w modelu.

### `organization_aliases`

- `id` — PK;
- `organization_id` — FK `ON DELETE CASCADE`;
- `alias` — forma występująca w tekście;
- `normalized_alias` — wartość używana do dokładnego dopasowania;
- `alias_kind` — `inflection`, `abbreviation`, `former_name`, `manual`,
  `ner_observed`;
- `created_by` — `manual`, `migration`, `ner`;
- `created_at`.

Wymagany unikalny indeks na `normalized_alias`. Jeden alias nie może po cichu
wskazywać dwóch organizacji. Konflikt powinien zwracać `409` i wymagać decyzji
użytkownika.

Normalizacja:

1. `normalize_ner_text()`;
2. ujednolicenie białych znaków;
3. `casefold()`;
4. bez usuwania polskich znaków;
5. bez fuzzy match przy automatycznym scalaniu.

### `document_organizations`

- `id` — PK;
- `document_id` — FK `ON DELETE CASCADE`;
- `organization_id` — FK `ON DELETE CASCADE`;
- `document_entity_id` — opcjonalne FK `ON DELETE SET NULL`;
- `mention_count`;
- `variants` — tablica form powierzchniowych;
- `confidence` — np. `alias_matched`, `canonical_matched`, `manual_confirmed`,
  `needs_review`;
- `created_at`;
- unikalność `(document_id, organization_id)`.

`document_entities` pozostaje źródłem danych dla istniejących ekranów.
Po rozwiązaniu organizacji rekord `orgName` powinien jednak używać
`canonical_name`, aby `/webpage`, `/read` i filtrowanie rozdziałów nie
wyświetlały duplikatów.

## Pipeline NER

Zmienić `library/entity_service.py` i/lub `library/ner_client.py` w następującej
kolejności:

1. uruchomić NER i agregację jak obecnie;
2. wykonać **scalenie wewnątrz jednego wyniku**:
   - tylko w obrębie `orgName`;
   - jeśli nazwa kanoniczna jednej grupy występuje jako wariant drugiej grupy,
     połączyć grupy;
   - jako nazwę wynikową wybrać grupę, która ma bogatszy zestaw wariantów albo
     jest już znana w globalnym rejestrze;
   - zsumować `mention_count`;
   - zachować unikalną sumę wariantów;
3. rozwiązać każdą grupę przez dokładne dopasowanie:
   - najpierw `organization_aliases.normalized_alias`;
   - następnie nazwę kanoniczną organizacji;
   - bez LLM i bez fuzzy auto-merge;
4. zamienić nazwę grupy na nazwę kanoniczną z rejestru;
5. ponownie połączyć grupy wskazujące tę samą `organization_id`;
6. zapisać jeden `DocumentEntity(orgName)` i jeden
   `DocumentOrganization` na organizację;
7. zachować replace semantics obecnego odświeżania encji.

Nie tworzyć automatycznie globalnych aliasów z każdej formy zwróconej przez
NER. Błędne wyniki takie jak `Korea` rozpoznana jako `orgName` nie mogą
zatruwać rejestru. Automatycznie można zapisywać obserwowane warianty dopiero,
gdy grupa została dopasowana do istniejącej organizacji; nowe aliasy powinny
mieć `alias_kind="ner_observed"` i być możliwe do audytu/usunięcia.

## Ręczne scalanie w `/webpage`

W trybie edycji organizacji dodać akcję **„Połącz z…”**.

Przepływ:

1. użytkownik wybiera błędny/alternatywny rekord, np. `Interii`;
2. wskazuje organizację docelową:
   - spośród organizacji obecnych w dokumencie, np. `Interia`;
   - albo przez wyszukiwanie globalnego rejestru;
3. UI pokazuje potwierdzenie:
   - „Alias `Interii` będzie globalnie łączony z `Interia` również w następnych
     dokumentach”;
4. backend w jednej transakcji:
   - tworzy alias globalny;
   - scala bieżące `DocumentEntity`;
   - scala `DocumentOrganization`;
   - sumuje liczby wystąpień i warianty;
   - zapisuje audyt;
5. UI odświeża encje bez ponownego uruchamiania NER.

Przycisk i pozostałe mutacje muszą być zablokowane na czas operacji zgodnie
z istniejącą globalną blokadą formularza. Dokument z embeddingami wymaga
najpierw użycia „Otwórz ponownie do edycji”.

## API

Minimalny zestaw:

- `GET /organizations?q=<tekst>` — wyszukiwanie po nazwie i aliasach;
- `GET /organizations/<id>` — organizacja, aliasy i liczba dokumentów;
- `POST /organizations` — ręczne utworzenie organizacji;
- `POST /organizations/<id>/aliases` — dodanie globalnego aliasu;
- `DELETE /organizations/<id>/aliases/<alias_id>` — usunięcie aliasu;
- `POST /document/<doc_id>/organizations/merge`:

```json
{
  "source_entity_id": 8472,
  "target_entity_id": 8471,
  "make_global_alias": true,
  "comment": "Odmiana nazwy Interia"
}
```

Odpowiedź powinna zawierać kanoniczną organizację, wynikowe warianty,
`mention_count` i identyfikator wpisu audytowego.

Walidacja:

- oba rekordy muszą należeć do dokumentu i mieć typ `orgName`;
- nie wolno scalać organizacji z osobą lub miejscem;
- alias konfliktujący z inną organizacją zwraca `409`;
- operacja jest idempotentna;
- powtórne dodanie tego samego aliasu do tej samej organizacji zwraca sukces,
  a nie błąd duplikatu;
- dokument z embeddingami zwraca `409`, dopóki nie zostanie ponownie otwarty
  do edycji.

## Audyt i możliwość cofnięcia

Wykorzystać istniejące `entity_review_decisions`, dodając decyzję
`organization_merged` oraz szczegóły:

```json
{
  "source_entity_text": "Interii",
  "target_entity_text": "Interia",
  "organization_id": 123,
  "alias_id": 456,
  "global_alias": true,
  "source_variants": ["Interii"],
  "target_variants_before": ["Interii", "Interią"]
}
```

Usunięcie aliasu nie usuwa historii audytowej. Powinno jedynie powodować, że
przyszłe odświeżenia NER przestaną korzystać z reguły. Nie należy usuwać
globalnego aliasu automatycznie przy ponownym otwarciu dokumentu do edycji.

## Migracja danych

Utworzyć kolejną migrację Alembic po aktualnym head.

Migracja/oddzielny skrypt naprawczy powinny:

1. utworzyć organizację `Interia`;
2. dodać aliasy:
   - `Interia` jako forma kanoniczna lub alias techniczny;
   - `Interii`;
   - `Interią`;
   - `Interię`;
3. znaleźć istniejące `DocumentEntity(orgName)` pasujące dokładnie do tych
   form lub posiadające je w `variants`;
4. w każdym dokumencie scalić je do jednego `Interia`;
5. zsumować wystąpienia i warianty bez utraty danych;
6. utworzyć `document_organizations`;
7. nie dotykać `placeName`, `geogName` ani `persName`;
8. nie zmieniać globalnych `ner_exclusions`;
9. przygotować tryb `--dry-run` raportujący liczbę dokumentów i planowane
   zmiany przed zapisem.

Preferowany podział:

- Alembic: wyłącznie schemat i bezpieczny seed `Interia`;
- `backend/imports/backfill_organizations.py`: migracja istniejących encji,
  `--dry-run` domyślnie, zapis dopiero z `--apply`.

## Testy

### Jednostkowe

- `Interia` + `Interii` w jednym wyniku daje jedną grupę i sumę 4;
- warianty są unikalne i zachowują oryginalną pisownię;
- alias `Interii` rozwiązuje się do `Interia`;
- `Interią` i `Interię` rozwiązują się do `Interia`;
- alias działa w następnym dokumencie;
- `orgName` nie scala się z `placeName`;
- brak fuzzy auto-merge;
- konflikt aliasu zwraca `409`;
- ponowienie merge jest idempotentne;
- merge dokumentu z embeddingami zwraca `409`;
- audyt zawiera źródło, cel, komentarz i identyfikator aliasu.

### Integracyjne/API

- wyszukiwanie organizacji po aliasie;
- ręczne scalenie dwóch encji dokumentu;
- usunięcie aliasu;
- ponowne odświeżenie NER nie odtwarza duplikatu;
- `/website_entities` zwraca jeden rekord `Interia`;
- `/read` nadal poprawnie filtruje warianty do rozdziału.

### Regresja

- osoby, miejsca, źródła informacji i klasyfikacja kontekstowa `Pocisków`
  działają bez zmian;
- `Korea` wykluczona globalnie jako `orgName` pozostaje wykluczona;
- Bloomberg/KCNA nadal mogą być klasyfikowane jako cytowane źródła;
- ponowne otwieranie dokumentu z embeddingami nie usuwa rejestru organizacji
  ani globalnych aliasów.

## Kryteria akceptacji na NAS

1. Na `/webpage/9267` po odświeżeniu NER widoczna jest jedna organizacja
   `Interia`, liczba wystąpień `4`.
2. Warianty obejmują co najmniej `Interii` i `Interią`.
3. W drugim artykule zawierającym wyłącznie formę `Interii` system wyświetla
   `Interia` bez ręcznej korekty.
4. Ręczne „Połącz z…” tworzy globalny alias i wpis audytowy.
5. Alias można usunąć, a historia decyzji pozostaje.
6. Nie powstaje dodatkowe wywołanie LLM.
7. Testy backendu, lint i build frontendu przechodzą.
8. Migracje są zastosowane na NAS, backend i frontend wdrożone.
9. Claude Code podaje użytkownikowi adresy testowe:
   - `http://192.168.200.7:3000/webpage/9267`
   - `http://192.168.200.7:3000/information-sources`

## Zalecana kolejność implementacji

1. modele ORM i migracja Alembic;
2. repozytorium/serwis organizacji;
3. deterministyczne scalanie grup NER;
4. zapis `document_organizations`;
5. API wyszukiwania, aliasów i merge;
6. UI „Połącz z…” i obsługa konfliktów;
7. audyt oraz usuwanie aliasu;
8. skrypt backfill z `--dry-run`;
9. testy regresji;
10. migracja, deploy i test dokumentu `9267` na NAS.

## Poza zakresem pierwszej implementacji

- automatyczna disambiguacja organizacji przez LLM;
- Wikidata/OpenCorporates;
- fuzzy auto-merge;
- automatyczne utożsamianie organizacji z `InformationSource`;
- wersjonowanie historycznych stanów `document_entities`;
- masowe automatyczne tworzenie aliasów ze wszystkich dotychczasowych
  wariantów bez ręcznej lub deterministycznej walidacji.

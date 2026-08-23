# Workflow diagnozy encji NER (miejsca / osoby / organizacje)

## Cel

Użytkownik zauważa w czytniku (`/read/:id`) albo w panelu encji błędnie
rozpoznaną, niepowiązaną, zduplikowaną albo brakującą encję —
`geogName`/`placeName` (miejsce), `persName` (osoba) lub `orgName`
(organizacja). Workflow prowadzi diagnozę od konkretnego przypadku do
poprawki w kodzie, tak jak przy dokumencie #9394 ("Al-Faszirze Emiraty",
PR #535): znajdź encję → znajdź zdanie źródłowe → ustal, który mechanizm
pipeline'u zawiódł (albo: czy w ogóle zawiódł, czy to stare dane pod już
naprawionym mechanizmem) → **wyjaśnij przyczynę i zaproponuj poprawkę,
zaczekaj na zgodę użytkownika** → napraw we właściwym miejscu → zregresuj →
wdróż → zweryfikuj na żywym dokumencie.

To diagnoza pojedynczych, zgłoszonych przypadków, nie audyt hurtowy. Nie
przeszukuj całej bazy w poszukiwaniu podobnych błędów, chyba że użytkownik
o to poprosi.

## Wspólne dane wejściowe

Potrzebny jest `document_id` i albo dokładny tekst encji (`entity_text`),
albo rozdział/fragment, w którym użytkownik ją zauważył. Jeśli którekolwiek
brakuje, dopytaj zanim zaczniesz.

## Etap 1: zbierz dowody (wspólne dla wszystkich typów)

Połącz się z bazą NAS przez psql (`docs/CICD/NAS_Deployment.md`,
`psql -h 192.168.200.7 -p 5434 -U postgres -d lenie-ai`).

1. Znajdź wiersz encji:

   ```sql
   SELECT id, entity_type, entity_text, mention_count, variants, geocode_id, source
   FROM document_entities
   WHERE document_id = :doc_id AND entity_text ILIKE '%fragment%';
   ```

2. Znajdź zdanie źródłowe — samo `entity_text` rzadko wystarcza, trzeba
   zobaczyć kontekst (interpunkcja, sąsiednie zdania):

   ```sql
   SELECT id, position, COALESCE(corrected_text, original_text)
   FROM document_chunks
   WHERE document_id = :doc_id AND original_text ILIKE '%fragment%';
   ```

3. Sprawdź, czy przypadek jest już objęty istniejącą regułą korekcyjną:

   ```sql
   SELECT * FROM ner_exclusions WHERE entity_text ILIKE '%fragment%';
   SELECT * FROM ner_corrections WHERE match_lemma ILIKE '%fragment%';
   ```

   `ner_exclusions` usuwa encję całkowicie (fałszywy pozytyw spaCy — np.
   fragment transkrypcji STT rozpoznany jako osoba). `ner_corrections`
   przemianowuje encję na inny tekst/typ (`library/ner_corrections.py`,
   `library/entity_service.py`). Obie tabele mają REST API: `GET/POST
   /ner_exclusions`, `GET/POST /ner_corrections`.

Na tym etapie powinieneś już wiedzieć: czy encja w ogóle istnieje, jak
wygląda zdanie źródłowe, i czy to nowy przypadek, czy coś, co powinna była
złapać istniejąca reguła (a nie złapała — to osobny bug do zdiagnozowania).

## Etap 2: zdiagnozuj mechanizm specyficzny dla typu

### Miejsca (`geogName` / `placeName`)

Pipeline: `library/place_verification.py` (dokumentacja pipeline'u w jego
module docstring i w `docs/ner-integration-plan.md` /
`docs/geo-place-ner-plan.md`).

```sql
SELECT * FROM geocode_cache WHERE query = 'dokładny_entity_text';
SELECT * FROM ner_context_classifications
WHERE document_id = :doc_id AND entity_text ILIKE '%fragment%';
```

Typowe kategorie i gdzie naprawiać:

| Objaw | Przyczyna | Gdzie naprawić |
|---|---|---|
| `geocode_cache.resolved=false`, `entity_text` wygląda jak dwa zlepione zdania (brak przecinka/kropki w źródle) | NER połączył miejsce z sąsiednią wzmianką kraju w jeden span | Już obsługiwane przez `country_gazetteer.strip_country_edge()` + `place_verification._retry_after_stripping_country()` (PR #535) — sprawdź, czy backend na NAS ma tę wersję kodu (`git log -1 -- backend/library/place_verification.py`), a nie że trzeba pisać nową regułę |
| `entity_text` to rzadka odmiana obcojęzycznego miasta/cieśniny/zatoki, geokoder nie widzi w niej mianownika | spaCy nie zlemmatyzowało nazwy, brak wpisu w gazetteerze | Dopisz wariant do `library/city_gazetteer.py` (miasta) albo `library/geo_feature_gazetteer.py` (morza/cieśniny/zatoki/kanały) |
| `geocode_cache.raw` pokazuje trafienie w zupełnie inne miejsce, albo `resolved=false` mimo poprawnej polskiej pisowni | LocationIQ/OSM indeksuje miejsce pod inną transliteracją (patrz `library/geocode_aliases.py` — case Al-Faszir/El Fasher) | Dopisz wpis do `library/geocode_aliases.py`; zweryfikuj ręcznie `geocode()`/`is_plausible_match()` przed dopisaniem (patrz docstring modułu — próg 0.75) |
| Miejsce geokoduje się poprawnie, ale nie dostaje tagu `miejsce-*` | `NerContextClassification` odrzuciło je jako nie-miejsce (homonim, np. system uzbrojenia "Wisła-Narew-Pilica"), albo LLM (`article_tagging.confirm_places_with_llm`) uznał wzmiankę za nieistotną | Sprawdź `context_excerpt`/`rationale` w `ner_context_classifications`; jeśli klasyfikacja jest błędna, to bug w `library/place_context_classifier.py`, nie w geokodowaniu |
| Ten sam realny obiekt widoczny dwa razy pod różną pisownią/typem (`geogName` vs `placeName`) | `_canonicalize_and_merge_places()` nie scaliło — geokoder zwrócił różne `display_name` dla obu wariantów | Sprawdź `canonical_place_name()` w `library/locationiq_client.py`; zwykle wystarczy, że oba wiersze mają ten sam `geocode_id` |
| Miejsce faktycznie nie istnieje w LocationIQ (nie tylko po polsku) | Limit danych geokodera, nie bug | Zostaw jako `verified=false`; nie twórz reguły na siłę |

### Osoby (`persName`)

Pipeline: `library/person_registry.py` (kaskada: alias/canoniczne dopasowanie
→ Wikidata + `article_tagging.confirm_person_with_llm` → filtr
jednowyrazowych wzmianek bez trafienia w Wikidata → fuzzy pg_trgm →
`manual_review`).

```sql
SELECT dp.id, dp.raw_mention, dp.confidence, p.canonical_name, p.wikidata_qid
FROM document_persons dp JOIN persons p ON p.id = dp.person_id
WHERE dp.document_id = :doc_id AND dp.raw_mention ILIKE '%fragment%';

SELECT * FROM persons WHERE canonical_name ILIKE '%fragment%';
SELECT * FROM person_aliases WHERE alias ILIKE '%fragment%';
```

| Objaw | Przyczyna | Gdzie naprawić |
|---|---|---|
| Encja w ogóle nie trafiła do `document_persons` | Filtr jednowyrazowych wzmianek bez trafienia w Wikidata (`person_registry.py`) potraktował ją jako szum | Sprawdź czy to faktycznie osoba; jeśli tak, ale mało znana/lokalna — to oczekiwane, wpis i tak trafi do rejestru bez QID przy kolejnym wystąpieniu z pełniejszym kontekstem |
| `confidence='manual_review'`, ktoś inny niż powinien | LLM (`confirm_person_with_llm`) źle rozstrzygnął ujednoznacznienie (kilku kandydatów w Wikidata o tym samym nazwisku) | To do ręcznej decyzji w `GET/PATCH /persons_review`, nie automatyczna reguła |
| Ta sama osoba pod dwiema pisowniami/odmianami jako różne wpisy w `persons` | Brak aliasu łączącego formy | `POST /persons/<id>/aliases`, albo `merge_review_link()` jeśli to już przeszło przez `manual_review` |
| Coś ewidentnie nie-osobowego rozpoznane jako `persName` (artefakt STT, homograf) | Fałszywy pozytyw spaCy | `POST /ner_exclusions` (`entity_type='persName'`, ew. `scope='author'` dla artefaktów jednego kanału/podcastu) |

### Organizacje (`orgName`)

Pipeline: `library/organization_registry.py` — celowo prostszy niż osoby:
tylko dopasowanie dokładne (alias/kanoniczna nazwa), bez Wikidata/LLM, bez
fuzzy auto-merge (`docs/organization-ner-alias-plan.md`).

```sql
SELECT do_.id, do_.confidence, o.canonical_name
FROM document_organizations do_ JOIN organizations o ON o.id = do_.organization_id
WHERE do_.document_id = :doc_id;

SELECT * FROM organizations WHERE canonical_name ILIKE '%fragment%';
SELECT * FROM organization_aliases WHERE alias ILIKE '%fragment%';
SELECT * FROM organization_ambiguous_aliases WHERE alias ILIKE '%fragment%';
```

| Objaw | Przyczyna | Gdzie naprawić |
|---|---|---|
| Pierwsze wystąpienie nowej organizacji, brak opisu | Oczekiwane — rejestr rośnie z każdym nowym dokumentem | `PATCH /organizations/<id>` żeby dopisać opis, nie bug |
| Ten sam skrót oznacza różne organizacje w różnych dokumentach (np. "SAF") | Skrót niejednoznaczny kontekstowo | `organization_ambiguous_aliases` + `select_ambiguous_alias_candidate_with_llm()` — sprawdź czy skrót ma tam wpis, jeśli nie, to feature do dodania, nie fix |
| Kraj rozpoznany jako `orgName` zamiast `geogName`/`placeName` (spaCy gubi się na imiesłowach, np. "Zjednoczone Emiraty Arabskie") | `COUNTRY_CHECK_TYPES` w `ner_client.py` powinno to złapać przez `country_gazetteer` | Jeśli nie złapało — sprawdź czy nazwa kraju ma pełne pokrycie wariantów w `country_gazetteer.py` |
| Dwie różne pisownie tej samej organizacji jako osobne wpisy | Brak aliasu | `POST /organizations/<id>/aliases`, albo `POST /organizations/<id>/merge` |
| `canonical_name` to bezsensowna, małymi literami, niezgramatyczna fraza (np. "europejski rada sprawa zagraniczny" dla "Europejskiej Rady Spraw Zagranicznych") | Surowy, mangled lemat spaCy (`Span.lemma_` konkatenuje lematy per-token i gubi odmianę przymiotnika) trafił wprost do `canonical_name` przy tworzeniu organizacji | Sprawdź NAJPIERW Etap 2b — `NOMINATIVE_PREFERENCE_TYPES` w `ner_client.py` (Faza 1/5, PR #517) już to naprawia dla nowych/odświeżanych wpisów; jeśli organizacja jest starsza niż wdrożenie tej poprawki, to stara dana, nie żywy bug — napraw przez `PATCH /organizations/<id>` (ustawia nową `canonical_name`, stara zostaje aliasem) + `POST /website_entities` (żeby przepisać `document_entities.entity_text`, bo to on jest wyświetlany w `/read`, nie `organizations.canonical_name`) |

## Etap 2b: to żywy bug, czy stare dane pod już naprawionym mechanizmem?

Zanim zaproponujesz jakąkolwiek poprawkę, sprawdź, czy nie trafiłeś na
przypadek, który mechanizm w obecnym kodzie **już poprawnie obsługuje** — a
zepsuty rekord po prostu powstał, zanim ta poprawka została wdrożona.

1. Znajdź commit, który jako ostatni naprawiał tę klasę błędu (najczęściej
   widoczny w komentarzach/docstringach w tabeli z Etapu 2 — np.
   "Faza 1/5", numer PR). `git log --oneline -- <plik>` żeby potwierdzić datę
   i treść.
2. Sprawdź, czy backend na NAS faktycznie ma tę wersję pliku (`ssh
   admin@192.168.200.7 "$DOCKER exec lenie-ai-server grep -n
   '<charakterystyczny_fragment>' /app/library/<plik>.py"` — `reference_nas_deploy.md`
   w pamięci). Brak → to nadal żywy bug, poprawka nie dotarła na produkcję.
3. Jeśli kod na NAS ma już poprawkę, porównaj datę utworzenia zepsutego
   rekordu (`organizations.created_at`, `persons.created_at`, `geocode_cache.created_at`
   itp.) z datą wdrożenia poprawki. Rekord starszy niż wdrożenie → to stare,
   zepsute dane pod już naprawionym mechanizmem, NIE żywy bug kodu. Napraw
   sam rekord (PATCH/REST/SQL + w razie potrzeby refresh), nie pisz nowego kodu.
4. Napisz krótki test odtwarzający dokładnie ten kształt danych z Etapu 1
   (typ encji, liczba wzmianek, przypadek gramatyczny) i sprawdź, czy
   przechodzi na obecnym kodzie BEZ zmian. Jeśli przechodzi — masz dowód, że
   to przypadek 3, nie nowy bug; dopisz ten test do zestawu regresyjnego jako
   dokumentację tego konkretnego przypadku (patrz Etap 4 pkt 3), zamiast
   zmieniać logikę.

## Etap 3: wyjaśnij i zaproponuj — czekaj na zgodę

Diagnoza (Etapy 1-2b) nie jest zielonym światłem do działania. Zanim
dotkniesz kodu, danych produkcyjnych na NAS albo cokolwiek wdrożysz,
przedstaw użytkownikowi w rozmowie:

1. **Dlaczego błąd się pojawił** — konkretny mechanizm z Etapu 2/2b: który
   plik/funkcja zawiodła (albo: nie zawiodła, tylko rekord jest starszy niż
   poprawka), z cytatem zdania źródłowego z Etapu 1.
2. **Jak chcesz go poprawić** — jawnie rozróżnij:
   - poprawka kodu (nowy plik/funkcja do zmiany, zakres, test regresyjny) —
     wymaga PR + deployu na NAS,
   - poprawka samych danych (PATCH/POST/SQL na już istniejącym rekordzie) —
     bez zmian w kodzie, ale nadal działanie na produkcyjnej bazie NAS,
   - albo obie naraz (poprawka kodu na przyszłość + osobna naprawa
     konkretnego zepsutego rekordu, jak w Etapie 4 pkt 3-4).
3. Zaczekaj na wyraźną zgodę użytkownika, zanim przejdziesz do Etapu 4.
   Użytkownik może mieć inną sugestię co do podejścia — nie zakładaj, że
   zaproponowany kierunek jest jedynym słusznym.

**Nie wykonuj żadnej zmiany w kodzie, żadnego deployu na NAS ani żadnej
bezpośredniej mutacji danych produkcyjnych (PATCH/POST/UPDATE przez REST
albo SQL na `192.168.200.7`) bez wyraźnej zgody użytkownika na TĘ
konkretną propozycję.** Sam odczyt/diagnoza (SELECT, GET) nie wymaga zgody.

## Etap 4: zaimplementuj poprawkę (dopiero po zgodzie z Etapu 3)

1. Feature branch (nigdy commit wprost na `main`).
2. Zmień właściwy plik z tabeli powyżej. Gazetteery (`city_gazetteer.py`,
   `geo_feature_gazetteer.py`, `country_gazetteer.py`) i
   `geocode_aliases.py` to zamknięte, ręcznie kuratorowane listy — dopisuj
   pojedynczy, potwierdzony przypadek, nie buduj ogólnych heurystyk "na
   zapas".
3. Dodaj test regresyjny oparty na rzeczywistym zdaniu źródłowym z Etapu 1
   (patrz istniejące testy w `backend/tests/unit/test_place_verification.py`,
   `test_country_gazetteer.py`, `test_city_gazetteer.py`,
   `test_geocode_aliases.py` jako wzór — regresje tam cytują dokładny
   dokument/zdanie, które je spowodowało).
4. Uruchom testy celowane, potem `ruff check` na zmienionych plikach:

   ```powershell
   cd backend
   $env:PYTHONPATH='.'
   .\.venv\Scripts\python.exe -m pytest tests\unit\test_<dotyczący_plik>.py -q
   uv run ruff check library/<plik>.py tests/unit/test_<plik>.py
   ```

## Etap 5: PR, deploy, weryfikacja

1. `gh pr create` + `gh pr merge` po zielonych checkach (repo convention —
   zawsze PR, nawet dla małej poprawki).
2. Wdróż na NAS:
   - Zmienione tylko pliki `.py`, bez nowych zależności → hotfix `docker cp`
     do `lenie-ai-server`, `lenie-worker`, `lenie-document-worker`
     (`reference_nas_deploy.md` w pamięci / `docs/CICD/NAS_Deployment.md`),
     potem restart tych kontenerów.
   - Nowe zależności/migracja Alembic → pełny `infra/docker/nas-deploy.ps1`.
3. Napraw konkretny, już zepsuty przypadek w danych — nowy kod w pipeline'ie
   naprawia tylko *przyszłe* przebiegi NER, nie cofa się wstecz:
   - jeśli encja ma ustawiony `geocode_id`/link do rejestru z poprzedniego
     (błędnego) przebiegu, sama się nie naprawi — geokodowanie i rejestr
     person/organization pomijają już-połączone encje;
   - najprostsza poprawka: usuń zepsutą encję (`DELETE
     /website_entities/<id>` — obsługuje też sprzątanie osieroconych tagów
     `miejsce-*`) jeśli poprawny wpis już istnieje pod inną encją (tak jak
     w #9394 — "Al-Faszir" już miał osobny, poprawny wiersz);
   - jeśli poprawnego wpisu jeszcze nie ma, `POST /website_entities` wymusi
     pełny refresh NER (uwaga: zwraca 409, jeśli dokument ma już
     embeddingi — trzeba go najpierw "reopen" do edycji), albo popraw
     ręcznie przez SQL/REST, jeśli wynik nowej reguły jest jednoznaczny.
4. Zweryfikuj w przeglądarce na `http://192.168.200.7:3000/read/<id>` (albo
   `?chapter=<n>`), że encja już nie pojawia się błędnie, i podaj ten URL
   użytkownikowi do potwierdzenia.

## Kryterium ukończenia

- zdiagnozowana kategoria i lokalizacja przyczyny są jednoznaczne, poparte
  konkretnym zdaniem źródłowym, nie domysłem,
- ustalone w Etapie 2b, czy to żywy bug kodu, czy stare dane pod już
  naprawionym mechanizmem,
- użytkownik dostał w Etapie 3 wyjaśnienie przyczyny i propozycję poprawki
  i wyraził na nią zgodę, zanim ruszyła implementacja/mutacja danych na NAS,
- poprawka ma test regresyjny cytujący dokument/zdanie, które ją
  spowodowało — również wtedy, gdy okazało się, że kod już działa poprawnie
  i zmiana ograniczyła się do naprawy danych (Etap 2b pkt 4),
- jeśli zakres obejmował zmianę kodu: PR zmergowany, backend wdrożony na
  NAS; jeśli to był wyłącznie przypadek z Etapu 2b (stare dane pod już
  naprawionym mechanizmem), sam test dokumentujący przypadek wystarcza —
  nie twórz kodu na siłę tam, gdzie nic nie jest złamane,
- konkretny zgłoszony przypadek jest naprawiony w danych (nie tylko w
  kodzie na przyszłość) i zweryfikowany w przeglądarce.

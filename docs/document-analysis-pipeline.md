# Jak analizowany jest dokument webowy — pełny flow

Ten dokument opisuje, co dokładnie dzieje się z artykułem/stroną webową od momentu pobrania
do momentu, w którym jego treść jest przeszukiwalna (embeddingi + tagi). Dla każdego kroku
zaznaczono **czym jest realizowany**: `REGEX`/deterministycznie (kod, zero kosztu, w pełni
powtarzalny), `LLM` (Bielik, kosztuje, może się mylić), czy usługa zewnętrzna (`SERWIS`:
NER microservice, geocoder, Wikidata).

Stan na 2026-07-22, gałąź `main`. Kod źródłowy jest tu autorytetem — ten dokument opisuje
*obecny* przepływ, nie docelowy; jeśli coś zmienisz w kodzie, zaktualizuj też ten plik.

## Skrót w jednym zdaniu

```
pobranie HTML → wyciągnięcie treści artykułu → wstępne czyszczenie (regex, per portal)
  → utworzenie "run"-a analizy → podział na chunki → klasyfikacja/streszczenie chunków (LLM)
  → grupowanie w sekcje tematyczne (LLM) → tagowanie + NER + miejsca + osoby + jakość
  → recenzja człowieka (zatwierdzenie chunków TEMAT) → embeddingi (automatycznie po zamknięciu)
  → wyszukiwanie hybrydowe (lexical ILIKE + wektory pgvector)
```

---

## 0. Import / ingest (przed jakimkolwiek "run"-em)

Ten etap dzieje się raz, przy dodaniu dokumentu (`imports/dynamodb_sync.py`,
`imports/article_browser.py`, rozszerzenie Chrome) — zanim ktokolwiek kliknie
"Rozpocznij analizę" na `/chunks`.

| Krok | Mechanizm | Gdzie |
|---|---|---|
| Pobranie surowego HTML | deterministyczne (requests/BeautifulSoup) | `library/website/website_download_context.py` |
| Konwersja HTML → markdown | deterministyczne (MarkItDown/html2markdown) | `library/article_pipeline.py: ensure_raw_markdown()` |
| Wykrycie granic artykułu | **hybryda, asymetryczna między początkiem a końcem — patrz niżej** | `library/article_extractor.py: process_article_with_llm_fallback()` |
| Autor — ekstrakcja deterministyczna (tylko wp.pl/o2.pl/money.pl, z pola `cauthor` w HTML lub selektora CSS) | **REGEX/HTML** | `library/article_metadata.py: extract_article_author()` |
| Data publikacji — jeśli portal daje ją wprost | **REGEX/HTML** | (per-portal, różne miejsca) |

Efekt: `documents.text_md` (markdown już z grubsza wyekstrahowany), ewentualnie `documents.byline`
uzupełniony deterministycznie już na tym etapie (stąd `byline_method` bywa `NULL` — "legacy/import-set",
patrz `library/db/models.py:363-368`).

### Wykrywanie granic artykułu — jak dokładnie (nie jest to proste "LLM z fallbackiem")

To dzieje się w dwóch zupełnie osobnych momentach, z różną rolą regexu i LLM:

**a) Jednorazowa ekstrakcja przy imporcie** (`article_extractor.py`):
1. **Regex — wstępne odchudzenie wejścia dla LLM** (nie wyznacza finalnych granic):
   `_trim_markdown_navigation()` (znajdź ostatni H1, odetnij co wcześniej) +
   `_clean_markdown_for_llm()` (per-portal regexy: utnij od stopki, pomiń znane sekcje
   premium/reklamowe i pojedyncze linie-śmieci).
2. **LLM** (Bielik, ARK Labs lub CloudFerro jako fallback) czyta oczyszczony tekst i zwraca
   dokładny **cytat** pierwszego i ostatniego zdania artykułu (`article_first_sentence`/
   `article_last_sentence`) — `extract_article_markers_with_llm()`.
3. `extract_article_by_markers()` wyznacza finalne granice — **asymetrycznie**:
   - **Początek** = zawsze marker z LLM. Brak regexowej alternatywy na tym etapie.
   - **Koniec** = odwrotnie niż można by się spodziewać: jeśli portal ma zarejestrowany
     deterministyczny marker stopki (`PORTAL_FOOTER_MARKERS`, np. `"Komentarze ("` dla
     bankier.pl, `"Wybrane dla Ciebie"` dla wp.pl) — **regex wygrywa i całkowicie ignoruje
     sugestię LLM** (`_find_footer_line()`). Marker z LLM jest używany **tylko** gdy portal
     nie ma jeszcze zarejestrowanego markera stopki.

**b) Każde kolejne czyszczenie** (`article_cleaner.py: clean_article_text()`, wołane przy
   każdym `create_run()`/„Przeczyść i podziel ponownie") — to już **w 100% regex**, LLM
   w ogóle nie bierze udziału; reużywa tych samych `_find_footer_line()`/`_find_start_line()`
   co wyżej, ale tnie już wcześniej wyekstrahowany `text_md`.

**Sprzężenie zwrotne**: `generate_regex_draft()` przy każdej ekstrakcji LLM zapisuje plik
`.regex.draft` z kontekstem wokół znalezionych granic — surowiec do ręcznego dopisania nowego
portalu do `PORTAL_FOOTER_MARKERS`/`PORTAL_START_AFTER_MARKERS`. W praktyce: nowy/nieznany
portal → LLM znajduje granice za każdym razem (drogo) → człowiek przegląda draft i dopisuje
regex → kolejne artykuły z tego portalu mają koniec wykrywany za darmo regexem.

---

## 1. `DocumentAnalysisService.create_run()` — serce pipeline'u

Cały poniższy flow to **jedno wywołanie** `create_run()` (`backend/library/document_analysis_service.py`),
wyzwalane przyciskiem "▶ Rozpocznij analizę" / "+ Nowa analiza" na `/chunks/:id`. Numeracja kroków
odpowiada komentarzom w kodzie (nie wszystkie numery są tu wymienione — pominięto gałąź `transcript`
dla YouTube/nagrań, bo pytanie dotyczy dokumentów webowych = `mode="article"`).

### Krok 2 — wybór źródła tekstu
`_extract_text(doc, prefer_md=True)` — w trybie `article` priorytet ma `text_md` nad `text`.
**Deterministyczne.**

### Krok 2b — uzupełnienie daty publikacji z artefaktu względnego
Np. interia.pl pisze "Wczoraj, 12:58" zamiast daty — `resolve_relative_publication_date()`
rozwiązuje to względem `ingested_at`. Nigdy nie nadpisuje istniejącej daty.
**REGEX**, zero LLM. (`library/article_cleaner.py`)

### Krok "reclean" (opcjonalny, przycisk "Przeczyść i podziel ponownie")
`clean_article_text()` — czyszczenie per-portal: usuwanie nawigacji, stopki, cookie bannerów,
list "przeczytaj też", podpisów zdjęć, widżetu "o autorze" (dla wp.pl/o2.pl/money.pl —
patrz `_remove_author_bio_paragraph()`, dodane w PR #348). Zamienia obrazki/linki na
znaczniki `[imgN]`/`[linkN]`.
**W całości REGEX**, zero LLM. (`library/article_cleaner.py`)

### Podział na rozdziały (tylko książki, `scope_chapter`)
`detect_chapters()` — wykrywa nagłówki H1 (gdy jest ich ≥2) albo H2 markdown, tekst przed
pierwszym nagłówkiem staje się pseudo-rozdziałem "(wstęp)". Artykuły webowe zwykle mają 0-1
nagłówków, więc ten krok ich nie dotyczy — chapters są dla e-booków/PDF-ów.
**REGEX/markdown headers**, zero LLM. (`library/text_functions.py: detect_chapters()`)

### Krok 5 (w kodzie: linia ~505) — izolacja biogramu autora, GDY autor już znany
`extract_trailing_author_biography(text, doc.byline)` — jeśli `doc.byline` jest już ustawiony
(patrz Import wyżej), szuka w ostatnich ~35% dokumentu akapitu zawierającego imię i nazwisko
autora + język biograficzny ("dziennikarzem jest od...", "pracował w...") i **wycina go
z treści przed podziałem na chunki** — trafia do osobnej zmiennej `author_bio`, nie do
`article_body` używanego dalej.
**REGEX** (sygnały biograficzne: `jest|prac\w*|zajm\w*|dziennikar\w*|redakcj\w*|...`), zero LLM.
(`library/author_biography.py: extract_trailing_author_biography()`)

> Gdy `doc.byline` NIE jest jeszcze znany na tym etapie (bo dopiero zostanie wykryty przez LLM
> w kroku 11b2 poniżej), ta funkcja nie ma szans zadziałać — biogram zostaje w treści i przechodzi
> normalny podział na chunki, trafiając potem jako zwykły chunk SZUM (patrz PR #349, 2026-07-22).

### Krok "preclean" (opcjonalny) — wykrywanie reklam i szumu PRZED podziałem
`propose_article_cleanup(article_body, model)` — **LLM** (Bielik) czyta cały dokument w paczkach
po `PRECLEAN_MAX_TOKENS=1200` tokenów i zwraca listę zakresów linii do wykluczenia z etykietą
`REKLAMA`/`ZRODLA`/`SZUM` + powód. Funkcja jest "lossless" — nic nie jest fizycznie kasowane,
tylko oznaczone; wynik trafia potem jako osobne chunki z gotową etykietą (nie idą do LLM
ponownie). To najdroższy krok tego etapu (cały dokument, per-batch call).
**LLM.** (`library/chunk_llm_analysis.py: propose_article_cleanup()`)

### Podział na chunki
`split_markdown_into_chunks(article_body, chunk_size)` (domyślnie 5000 zn.) — cięcie na
nagłówkach markdown (`#`...`######`), potem pakowanie kolejnych sekcji do limitu znaków;
sekcja większa niż limit jest dalej dzielona na akapitach/zdaniach. Brak nagłówków →
zwykły podział na akapity.
**W całości REGEX/deterministyczne**, zero LLM. (`library/text_functions.py: split_markdown_into_chunks()`)

Jeśli krok wcześniej znalazł `author_bio` — dokładany jest na końcu jako **własny, osobny
chunk**, z góry oznaczony `type="SZUM"`, `topic="Notka biograficzna autora"` — **bez wywołania LLM**
(hardcoded, deterministyczne — patrz `document_analysis_service.py:521-526,558-565`).

### Krok 9 — analiza każdego chunka
`analyze_article_chunk(chunk_text, model, position, total)` — dla każdego chunka (poza
tym zarezerwowanym na biogram autora, który dostaje etykietę za darmo): **LLM** klasyfikuje
jako `TEMAT`/`ZRODLA`/`REKLAMA`/`SZUM` + (jeśli TEMAT) streszczenie 2-3 zdania.
W trybie `article` tekst NIE jest przepisywany (`corrected_text` zawsze `None` — markdown
już jest czysty, w przeciwieństwie do trybu `transcript` dla nagrań).
**LLM**, jedno wywołanie na chunk. (`library/chunk_llm_analysis.py: analyze_article_chunk()`)

### Krok 10 — grupowanie w sekcje tematyczne
`_merge_topics(sections, model)` — **LLM** grupuje chunki wg tematu w `DocumentTopicSection`
(napędza widok "rozdziały" na `/chunks/:id` dla dużych runów, próg `SECTION_VIEW_THRESHOLD`).
Pokrycie częściowe z założenia — LLM nie zawsze przypisze każdy chunk do sekcji.
**LLM.**

### Krok 11 — synteza (opcjonalna)
`_synthesize(sections, title, model)` — **LLM**, jedno zwięzłe podsumowanie całego dokumentu,
wejście dla tagowania poniżej.

### Krok 11b — tagowanie tematyczne + krajowe
- `tag_article_with_llm(text, title)` — **LLM** przypisuje tagi z zamkniętej listy `THEMATIC_TAGS`.
- `extract_countries_hybrid()` — **REGEX prescreen** (`country_gazetteer.detect_countries()`,
  ~190 krajów, dopasowanie rdzenia słowa bez LLM) **+ LLM potwierdzenie**, które z kandydatów
  są faktycznie *omawiane* (nie tylko wspomniane przelotnie) → tagi `kraj-*`.
  Jeśli gazetteer nie znajdzie żadnego kandydata — LLM w ogóle nie jest wywoływany (0 kosztu).
Wynik scalany (nie nadpisywany) z istniejącymi `doc.tags`.
**Hybryda REGEX+LLM.** (`library/article_tagging.py`, `library/country_gazetteer.py`)

### Krok 11b2 — fallback wykrywania autora (gdy import go nie ustalił)
`extract_author_info(head_tail_excerpt(text), model)` — **LLM**, czyta pierwsze+ostatnie
~1500 znaków, zwraca listę autorów (współautorstwo obsłużone). Nigdy nie nadpisuje istniejącego
`doc.byline`. Od PR #349 (2026-07-22): jeśli autor zostanie tu dopiero ustalony, od razu wołane
jest też `extract_trailing_author_biography()` (ten sam **REGEX** mechanizm co krok 5 wyżej) na
`doc.text_md`, żeby wyizolować biogram *na przyszłość* (ten konkretny run ma już chunki podzielone,
więc korzysta z tego dopiero następny reclean/run) — plus `process_author_biography()` (patrz niżej).
**LLM** (wykrycie autora) **+ REGEX** (wyizolowanie biogramu).

### Krok 11f — ocena staranności ("quality")
`compute_quality(doc, sections, model)` — kombinacja deterministycznych kar (np. brak źródeł,
obcięty tekst, agencyjny/własny autor wydawcy → waga 0) **+ jedno wywołanie LLM** (rubryka oceny).
**Hybryda REGEX (kary) + LLM (rubryka), 1 call.** (`library/article_quality.py`)

### Krok 11c — encje NER (osoby/miejsca)
`refresh_document_entities(session, doc_id, text)` — wysyła cały tekst do **wewnętrznego
mikroserwisu** `ner_service/` (spaCy `pl_core_news_lg`, model offline — **NIE LLM**, zero kosztu
per-wywołanie poza czasem obliczeń). Wynik: `document_entities`, semantyka "replace" (pełny
dokument na raz — dlatego pomijane dla runów per-rozdział).
**SERWIS zewnętrzny (spaCy), nie LLM.** (`library/entity_service.py`, `library/ner_client.py`)

### Krok 11d — weryfikacja miejsc
`verify_document_places()` — kandydaci z NER (typ `geogName`/`placeName`) → **geocoder
LocationIQ** (zewnętrzne API, wynik cache'owany w `geocode_cache`) potwierdza że miejsce
istnieje → **LLM** potwierdza że jest faktycznie *omawiane* (nie tylko wspomniane) → tag
`miejsce-<slug>`. Kraje pomijane (mają własny pipeline wyżej).
**SERWIS (LocationIQ) + LLM.** (`library/place_verification.py`)

### Krok 11e — rozwiązywanie osób
`resolve_document_persons()` — kaskada: dokładny alias/kanoniczna nazwa (bez sieci) →
**Wikidata** (zewnętrzne API, tylko ludzie P31=Q5) + **LLM** wybiera właściwy QID z zamkniętej
listy kandydatów → fuzzy match (pg_trgm) w rejestrze → nowa osoba bez QID (kolejka
`manual_review`). Wynik: `document_persons`.
**SERWIS (Wikidata) + LLM + fuzzy matching.** (`library/person_registry.py`)

Tu też: jeśli krok 5/11b2 znalazł `author_bio`, wywoływane jest `process_author_biography()` —
**LLM** porównuje nową notkę biograficzną z istniejącym opisem osoby w rejestrze (`Person.description`)
i decyduje: auto-applied / no_new_information / needs_review / conflict.

### Informacje o źródłach / cytowania
`refresh_document_information_sources()` i `refresh_document_cited_publications()` — **LLM**,
odpowiednio: wykrycie skąd artykuł czerpie informacje (agencje, inne media) i jakie publikacje
są cytowane w tekście.

### Krok 12 — zapis do bazy
Wszystko trafia do `DocumentAnalysisRun` + `DocumentChunk` (po jednym rekordzie na chunk,
status `pending`) + `DocumentTopicSection`. **Deterministyczne**, jeden `session.commit()`.

---

## 2. Recenzja człowieka (`/chunks/:id`)

Reviewer przegląda chunki, może:
- edytować linie / usuwać szum ręcznie (`document_removed_lines` — dane treningowe dla
  przyszłych reguł regex w `article_cleaner.py`),
- scalać/dzielić chunki,
- ręcznie wywołać ✍️ Autor / 📅 Data / 📚 Cytowania na wybranym chunku (te same funkcje LLM
  co wyżej, ale z konkretnym fragmentem jako input),
- zatwierdzić każdy chunk `TEMAT` osobno,
- zamknąć review (`PATCH /analysis_run/<id>` → `status=reviewed`).

Zamknięcie review z ≥1 zatwierdzonym chunkiem `TEMAT` **automatycznie odpala job embeddingów**
w tle (`chunk_review_routes.py: update_run()` → `_start_embedding_job()`). Reviewer nic
dodatkowego nie klika.

---

## 3. Generowanie embeddingów

`generate_embeddings_from_run()` (`document_analysis_service.py:818`):
1. Bierze tylko chunki `type="TEMAT"` + `status="approved"`.
2. Dla każdego: `corrected_text` (transcript) lub `original_text` (article), usuwa podpisy zdjęć,
   dzieli na kawałki embeddingowe `md_split_for_emb()` (hierarchicznie: H1→H2→H3→bold→akapity→zdania),
   czyści markdown (`md_remove_markdown()`).
3. Embeddinguje w paczkach po 32 fragmenty (`EMBEDDING_BATCH_SIZE`) — jedno wywołanie API na paczkę,
   commit po każdej paczce (żeby crash w trakcie nie tracił godzin pracy).
4. Zapis: `DocumentEmbedding` z `chunk_id` wskazującym na źródłowy chunk.

Ponowne uruchomienie na tym samym runie **usuwa** stare embeddingi powiązane z jego chunkami
i generuje od nowa — bezpieczne po edycji/re-approve chunka.
**LLM/embedding provider** (model z configu `EMBEDDING_MODEL`), **zero regexów** poza samym
splitterem markdown.

---

## 4. Wyszukiwanie (`POST /search`) i rola tagów

`SearchService.search()` (`library/search_service.py`) łączy dwa niezależne sygnały dla tego
samego zapytania:

- **Lexical** — `DocumentRepository.search_text()`: SQL `ILIKE` po **skonkatenowanym** polu
  `title + tags + note + text` (`unaccent()` po obu stronach). **To jest jedyne miejsce, gdzie
  tagi w ogóle uczestniczą w wyszukiwaniu** — nie ma osobnego, ustrukturyzowanego filtra
  "dokumenty z tagiem X". Tag działa tylko jako dodatkowy tekst do dopasowania substring/ILIKE.
- **Semantyczny** — `DocumentRepository.get_similar()`: pgvector cosine search po `document_embeddings`
  (embeddingi TYLKO z zatwierdzonej treści chunków — tagi nigdy nie są embeddowane osobno).

Opcjonalnie: `library/search/parser.py` — **LLM** parsuje naturalne zapytanie na `ParsedSearchQuery`
(autor, wydawca, zakres dat, okres historyczny itd.), które trafia do `sql_filters.py:
build_document_filters()` — to ten sam builder dla lexical/vector/filter-only. Filtry są
ustrukturyzowane (autor przez `document_persons`, wydawca przez `publisher_id`, źródło
odkrycia przez `discovery_sources`) — **ale nie ma pola `tags` w `SearchFilters`.**

### Jeśli chcesz zmienić: gdzie by to weszło

- **"Szukaj tylko wśród dokumentów z tagiem X"** (ostre filtrowanie, nie tylko boost) wymagałoby
  nowego pola w `SearchFilters` (`library/search/types.py`) + warunku w `sql_filters.py:
  build_document_filters()` — analogicznie do istniejącego `collection_name`. Dziś tag "działa"
  tylko przypadkiem, bo jest w tym samym polu co reszta tekstu przeszukiwanego ILIKE-iem.
- **Zmiana wykrywania szumu/reklam** (`propose_article_cleanup` — najdroższy krok LLM w całym
  pipeline) — jedyne miejsce, gdzie cały dokument idzie do LLM w paczkach; ewentualne zawężenie
  (np. tylko ostatnie 20% dokumentu, tam gdzie faktycznie żyją stopki/biogramy) obniżyłoby koszt.
- **Kolejność autor→biogram** — dziś biogram jest poprawnie wycinany PRZED podziałem tylko gdy
  `doc.byline` jest znany z importu (deterministyczna ekstrakcja wp.pl/o2.pl/money.pl). Dla
  portali bez takiej ekstrakcji autor i tak zostanie wykryty (krok 11b2), ale dopiero PO
  podziale — więc ten konkretny run i tak dostanie biogram jako osobny chunk SZUM (za darmo,
  bez LLM, ale widoczny). Żeby to wyeliminować całkowicie, trzeba by przesunąć wykrywanie
  autora PRZED podział zawsze (kosztem dodatkowego wywołania LLM na starcie każdego runu,
  nawet gdy autor i tak zostanie znaleziony przez prostszy regex import-time w 90% przypadków).

---

## Szybka tabela: co jest czym

| Etap | Mechanizm |
|---|---|
| Pobranie HTML → markdown | deterministyczne |
| Granice artykułu (import) | LLM + regex fallback |
| Autor (import, wp/o2/money) | regex/HTML |
| Czyszczenie per-portal (`clean_article_text`) | **regex** |
| Biogram autora — wycięcie przed podziałem | **regex** |
| Data publikacji z artefaktu względnego | **regex** |
| Rozdziały (książki) | **regex** (nagłówki md) |
| Wykrywanie reklam/szumu przed podziałem (`preclean`) | **LLM** (całość dokumentu, kosztowne) |
| Podział na chunki | **regex/deterministyczne** |
| Klasyfikacja + streszczenie chunka | **LLM** (1 call/chunk) |
| Grupowanie w sekcje tematyczne | **LLM** |
| Synteza | **LLM** |
| Tagi tematyczne | **LLM** |
| Tagi krajowe (`kraj-*`) | regex prescreen + **LLM** potwierdzenie |
| Autor — fallback (11b2) | **LLM** |
| Ocena staranności | regex kary + **LLM** rubryka (1 call) |
| Encje NER (osoby/miejsca) | **serwis zewnętrzny** (spaCy, nie LLM) |
| Weryfikacja miejsc | **serwis** (LocationIQ) + **LLM** |
| Rozwiązywanie osób | **serwis** (Wikidata) + **LLM** + fuzzy |
| Biogram autora → opis osoby | **LLM** |
| Źródła informacji / cytowania | **LLM** |
| Embeddingi | **model embeddingowy** (provider), regex tylko do splitu markdown |
| Wyszukiwanie lexical | **regex/SQL ILIKE** (tagi tu uczestniczą) |
| Wyszukiwanie semantyczne | **wektory** (pgvector) |
| Parsowanie zapytania naturalnego | **LLM** (opcjonalne) |

---

## Powiązane dokumenty

- [`docs/search-hybrid.md`](search-hybrid.md) — szczegóły scoringu i mergowania wyników lexical/vector.
- [`docs/ner-integration-plan.md`](ner-integration-plan.md) — architektura mikroserwisu NER.
- [`docs/deployment/nas/storage-and-jobs-migration-plan.md`](deployment/nas/storage-and-jobs-migration-plan.md) — plan przeniesienia batchowych skryptów na kolejkę jobów.
- `backend/library/CLAUDE.md` — pełna lista modułów z jednolinijkowym opisem każdego.

# Jak analizowany jest dokument webowy — pełny flow (timeline funkcji)

Ten dokument opisuje, co dokładnie dzieje się z artykułem/stroną webową od momentu pobrania
do momentu, w którym jego treść jest przeszukiwalna (embeddingi + tagi). Każdy krok jest
funkcją konkretnego pliku (`plik.py:LINIA`), w kolejności w jakiej faktycznie się wykonuje,
z opisem co robi na wejściu/wyjściu i oznaczeniem mechanizmu:

- **REGEX** — deterministyczny kod (Python/regex), zero kosztu, w pełni powtarzalny
- **LLM** — wywołanie Bielika (Sherlock/ARK Labs), kosztuje, może się mylić
- **SERWIS** — zewnętrzne API/mikroserwis (NER spaCy, LocationIQ, Wikidata) — nie LLM

Stan na 2026-07-22, gałąź `main`. Kod źródłowy jest tu autorytetem — jeśli coś zmienisz
w kodzie, zaktualizuj też ten plik (i linie, które na pewno się przesuną).

## Skrót w jednym zdaniu

```
pobranie HTML → wyciągnięcie treści artykułu (LLM markery + regex per-portal)
  → utworzenie "run"-a analizy → deterministyczne czyszczenie → podział na chunki
  → klasyfikacja/streszczenie chunków (LLM) → grupowanie w sekcje (LLM)
  → tagowanie + NER + miejsca + osoby + jakość → recenzja człowieka
  → embeddingi (automatycznie po zamknięciu) → wyszukiwanie hybrydowe
```

---

## Część 1 — Import: od HTML do `documents.text_md`

Dzieje się **raz**, przy dodaniu dokumentu (`imports/dynamodb_sync.py`,
`imports/article_browser.py`, rozszerzenie Chrome) — przed pierwszym kliknięciem
"Rozpocznij analizę" na `/chunks`. Wejście: `library/article_pipeline.py: extract_article()`.

| # | Funkcja | Plik:linia | Co robi | Mechanizm |
|---|---|---|---|---|
| 1 | `ensure_raw_markdown()` | `article_pipeline.py:24` | Zwraca surowy markdown CAŁEJ strony. Czyta `{id}_step_1_all.md` z cache jeśli już istnieje; inaczej pobiera HTML (cache/S3) i konwertuje przez `prepare_markdown()` (MarkItDown/html2text), zapisuje do cache. | REGEX/deterministyczne |
| 2 | `process_article_with_llm_fallback()` | `article_extractor.py:656` | Orkiestruje kroki 3-8 poniżej + retry (2 próby) + fallback między dostawcami LLM (ARK Labs ↔ CloudFerro). Zwraca wyekstrahowany tekst artykułu albo `None`. | orkiestracja |
| 3 | `_detect_portal(url)` | `article_extractor.py:72` | Rozpoznaje portal po URL (`onet`/`money`/`wp`/`interia`/`businessinsider`/`natgeo`/`gazeta`/`bankier`/`None`). Steruje którym słownikiem markerów (4, 6) użyć niżej. | REGEX |
| 4 | `_trim_markdown_navigation()` | `article_extractor.py:48` | Znajduje OSTATNI nagłówek `# ` w tekście (portale mają kilka H1, właściwy artykuł jest pod ostatnim) i odcina wszystko 3 linie przed nim. Brak H1 → bierze ostatnie 60% linii. **Tylko wstępne odchudzenie**, nie wyznacza finalnych granic. | REGEX |
| 5 | `_clean_markdown_for_llm()` | `article_extractor.py:285` | Wywołuje `_cut_at_footer()` (6) + usuwa sekcje premium/reklamowe (`PORTAL_SKIP_SECTIONS`) + pojedyncze linie-śmieci (`PORTAL_SKIP_LINES`, np. "Dalszy ciąg materiału pod wideo") + obrazki/emotki/linie z samą liczbą. | REGEX |
| 6 | `_cut_at_footer()` | `article_extractor.py:266` | Jeśli portal ma wpis w `PORTAL_FOOTER_MARKERS` (linia 98) — ucina tekst od PIERWSZEGO dopasowanego markera w dół (np. `"Komentarze ("` dla bankier.pl). To dzieje się PRZED wysłaniem do LLM — dla znanych portali LLM w ogóle nie widzi stopki. | REGEX |
| 7 | `_truncate_for_llm(cleaned, max_chars=15000)` | `article_extractor.py:350` | **Twardy limit**: zostawia pierwsze 15 000 znaków oczyszczonego tekstu, resztę odrzuca (dopisuje `"[...tekst przycięty...]"`). Dla nieznanego portalu z długim artykułem oznacza to, że LLM nie zobaczy prawdziwego zakończenia. | REGEX (obcinanie) |
| 8 | `extract_article_markers_with_llm()` / `_extract_markers_via_cloudferro()` | `article_extractor.py:386` / `:437` | Wysyła oczyszczony+przycięty tekst do Bielika z promptem `EXTRACTION_USER_PROMPT_TEMPLATE` (linia 23). Zwraca JSON: `title`, `author`, `date`, **`article_first_sentence`**, **`article_last_sentence`** (dosłowne cytaty!), `tags`. | **LLM** |
| 9 | `find_text_in_markdown()` | `article_extractor.py:475` | Lokalizuje zwrócony przez LLM cytat w oryginalnym (NIEuciętym) markdownie: exact match → normalizacja białych znaków → dopasowanie po pierwszych 8 słowach. Zwraca numer linii. | REGEX |
| 10 | `_find_footer_line()` | `article_extractor.py:219` | Szuka markera stopki (jak w kroku 6, ale na PEŁNYM, nieuciętym tekście) — potrzebne do wyznaczenia finalnego końca niezależnie od przycięcia z kroku 7. | REGEX |
| 11 | `extract_article_by_markers()` | `article_extractor.py:508` | **Tu zapadają finalne granice — asymetrycznie:** początek = zawsze linia z `article_first_sentence` (krok 9). Koniec: **jeśli krok 10 znalazł footer marker → używa go i CAŁKOWICIE IGNORUJE `article_last_sentence` z LLM** (komentarz w kodzie: *„Footer marker jest pewny — LLM marker traktuj jako fallback"*); dopiero gdy portal nie ma markera, używa końca wskazanego przez LLM. | REGEX > LLM (regex wygrywa gdy dostępny) |
| 12 | `generate_regex_draft()` | `article_extractor.py:560` | Zapisuje `.regex.draft` + `_llm_markers.json` z kontekstem 5 linii przed/po granicach — surowiec do RĘCZNEGO dopisania nowego portalu do `PORTAL_FOOTER_MARKERS`/`PORTAL_START_AFTER_MARKERS`. Pętla sprzężenia zwrotnego: nowy portal → LLM za każdym razem (drogo) → człowiek dopisuje regex → kolejne artykuły z tego portalu mają koniec za darmo. | REGEX (generowanie) |
| 13 | `extract_article_author()` | `article_metadata.py:102` | Osobno, **niezależnie od 1-12**: dla wp.pl/o2.pl/money.pl wyciąga autora wprost z pola `"cauthor"` w surowym HTML (regex na JSON w skrypcie analitycznym strony) albo z selektora CSS `.wp-article-author-link`. Ustawia `doc.byline` już na tym etapie importu (stąd `byline_method` bywa `NULL` — "legacy/import-set"). | REGEX/HTML |

Efekt końcowy: `documents.text_md` = wyekstrahowany tekst artykułu (krok 11), ewentualnie
`documents.byline` już ustawiony (krok 13, niezależnie od LLM).

---

## Część 2 — `create_run()`: analiza chunków

Wszystko poniżej to **jedno wywołanie** `DocumentAnalysisService.create_run()`
(`document_analysis_service.py:347`), tryb `mode="article"` (pomijam gałąź `transcript` dla
YouTube — pytanie dotyczy dokumentów webowych). Numeracja `#` = kolejność wykonania w kodzie,
nie numery komentarzy (te bywają nieciągłe, np. „11b2" — zachowane w nawiasie dla łatwego grep).

| # | Funkcja / blok | Plik:linia | Co robi | Mechanizm |
|---|---|---|---|---|
| 1 | `_extract_text(doc, prefer_md=True)` | `document_analysis_service.py:105` | Wybiera pole źródłowe: `text_md` > `text` > `text_raw` (JSON transkrypcji). W trybie article priorytet ma `text_md`. | REGEX/deterministyczne |
| 2 | backfill `published_on` | `document_analysis_service.py:426-438` → `article_cleaner.py: resolve_relative_publication_date()` | Rozwiązuje artefakty typu "Wczoraj, 12:58" (interia.pl) względem `doc.ingested_at`. Nigdy nie nadpisuje istniejącej daty. | REGEX |
| 3 *(if `reclean`)* | `clean_article_text()` | `document_analysis_service.py:444` → `article_cleaner.py:667` | Patrz szczegółowy rozbój niżej (Część 2a) — cały krok w 100% regex. | REGEX |
| 4 *(książki, `scope_chapter`)* | `_slice_chapter()` → `detect_chapters()` | `document_analysis_service.py:127` → `text_functions.py:209` | Wykrywa nagłówki H1 (gdy ≥2) lub H2 markdown jako granice rozdziałów; tekst przed pierwszym nagłówkiem = pseudo-rozdział "(wstęp)". Artykuły webowe zwykle mają 0-1 nagłówków — to dotyczy głównie e-booków. | REGEX |
| 5 | `extract_trailing_author_biography(text, doc.byline)` | `document_analysis_service.py:505` → `author_biography.py:21` | **Tylko gdy `doc.byline` już znany** (np. z importu, krok 13 wyżej): szuka w ostatnich ~35% dokumentu akapitu z imieniem+nazwiskiem autora + językiem biograficznym (`BIO_SIGNALS_RE`: `jest\|prac\w*\|zajm\w*\|dziennikar\w*\|redakcj\w*\|...`) i WYCINA go z `article_body` przed podziałem na chunki. | REGEX |
| 6 *(opcjonalny, `preclean`)* | `propose_article_cleanup()` | `document_analysis_service.py:509` → `chunk_llm_analysis.py:57` | **Najdroższy krok tego etapu**: cały `article_body` w paczkach po `PRECLEAN_MAX_TOKENS=1200` tokenów idzie do LLM, który zwraca zakresy linii do wykluczenia z etykietą `REKLAMA`/`ZRODLA`/`SZUM`. Lossless — nic nie kasowane, tylko oznaczone. | **LLM** |
| 7 | `split_markdown_into_chunks()` | `document_analysis_service.py:513/520` → `text_functions.py:154` | Tnie na nagłówkach markdown (`#`...`######`), pakuje kolejne sekcje do `chunk_size` (domyślnie 5000 zn.); sekcja większa niż limit → dalszy podział na akapitach/zdaniach. Brak nagłówków → zwykły podział na akapity. | REGEX |
| 8 *(jeśli krok 5 znalazł `author_bio`)* | dopisanie chunka biogramu | `document_analysis_service.py:521-526, 558-565` | Biogram dołączany jako WŁASNY, OSTATNI chunk, z góry oznaczony `type="SZUM"`, `topic="Notka biograficzna autora"` — **bez wywołania LLM** (hardcoded). | REGEX (zero LLM) |
| 9 | `analyze_article_chunk()` (per chunk) | `document_analysis_service.py:575` → `chunk_llm_analysis.py:389` | Dla każdego chunka (poza chunkiem biogramu z kroku 8, który dostaje etykietę za darmo): klasyfikacja `TEMAT`/`ZRODLA`/`REKLAMA`/`SZUM` + (jeśli TEMAT) streszczenie 2-3 zdania. `corrected_text` zawsze `None` w trybie article (markdown już czysty). | **LLM**, 1 call/chunk |
| 10 | `_merge_topics()` | `document_analysis_service.py:589` → `:190` | Grupuje chunki wg tematu w `DocumentTopicSection` (widok "rozdziały" na `/chunks/:id` dla dużych runów). Pokrycie częściowe z założenia. | **LLM** |
| 11 *(opcjonalny)* | `_synthesize()` | `document_analysis_service.py:626` → `:231` | Jedno zwięzłe podsumowanie całego dokumentu — wejście dla tagowania (12). | **LLM** |
| 12 | `_apply_tags()` → `tag_article_with_llm()` + `extract_countries_hybrid()` | `document_analysis_service.py:638, 266` → `article_tagging.py` | Tagi tematyczne z zamkniętej listy `THEMATIC_TAGS` (LLM) + tagi `kraj-*`: `country_gazetteer.detect_countries()` (REGEX prescreen, ~190 krajów, dopasowanie rdzenia słowa) najpierw filtruje kandydatów — jeśli 0 kandydatów, LLM w ogóle nie jest wywoływany. | REGEX prescreen + **LLM** potwierdzenie |
| 13 *(11b2, gdy `doc.byline` PUSTY)* | `extract_author_info(head_tail_excerpt(text), model)` | `document_analysis_service.py:654` → `chunk_llm_analysis.py:143, 135` | Fallback gdy import (krok 13 Części 1) nie ustalił autora: czyta pierwsze+ostatnie ~1500 zn. dokumentu, zwraca listę autorów (współautorstwo obsłużone). Nigdy nie nadpisuje istniejącego `doc.byline`. | **LLM** |
| 14 *(jeśli 13 znalazł autora)* | `extract_trailing_author_biography(doc.text_md, author_names[0])` (drugi raz!) | `document_analysis_service.py:667` → `author_biography.py:21` | Ten konkretny run ma już chunki podzielone (krok 7 był wcześniej) — więc to NIE zmienia liczby chunków tego runu. Zapisuje oczyszczony `doc.text_md` na przyszłość (kolejny reclean/run nie dostanie już tego biogramu jako osobnego chunka). Dodane w PR #349 (2026-07-22). | REGEX |
| 15 *(jeśli 5 lub 14 znalazły biogram)* | `process_author_biography()` | `document_analysis_service.py:672, 732` → `author_biography.py:111` | Porównuje notkę biograficzną z istniejącym `Person.description` w rejestrze osób i decyduje: `auto_applied` / `no_new_information` / `needs_review` / `conflict`. | **LLM** |
| 16 | `compute_quality()` | `document_analysis_service.py:685` → `article_quality.py` | Deterministyczne kary (brak źródeł, obcięty tekst, agencyjny/własny autor wydawcy → waga 0) + **jedno** wywołanie LLM (rubryka oceny). | REGEX kary + **LLM** (1 call) |
| 17 | `refresh_document_entities()` | `document_analysis_service.py:697` → `entity_service.py` | Cały tekst → **wewnętrzny mikroserwis** `ner_service/` (spaCy `pl_core_news_lg`, offline, NIE LLM). Semantyka "replace" — pełny dokument na raz, pomijane dla runów per-rozdział. | **SERWIS** (spaCy) |
| 18 | `verify_document_places()` | `document_analysis_service.py:711` → `place_verification.py` | Kandydaci z NER (typ `geogName`/`placeName`) → **LocationIQ** (geocoder, cache w `geocode_cache`) potwierdza istnienie → LLM potwierdza że miejsce jest faktycznie omawiane → tag `miejsce-<slug>`. | **SERWIS** (LocationIQ) + **LLM** |
| 19 | `resolve_document_persons()` | `document_analysis_service.py:721` → `person_registry.py` | Kaskada: dokładny alias (bez sieci) → **Wikidata** (tylko ludzie P31=Q5) + LLM wybiera QID z zamkniętej listy → fuzzy match (pg_trgm) w rejestrze → nowa osoba bez QID (kolejka `manual_review`). | **SERWIS** (Wikidata) + **LLM** + fuzzy |
| 20 | `refresh_document_information_sources()` | `document_analysis_service.py:740` → `information_provenance.py` | Wykrywa skąd artykuł czerpie informacje (agencje, inne media). | **LLM** |
| 21 | `refresh_document_cited_publications()` | `document_analysis_service.py:800` → `cited_publications.py` | Wykrywa jakie publikacje są cytowane w tekście chunków. | **LLM** |
| 22 | zapis do DB | `document_analysis_service.py:745-812` | `DocumentAnalysisRun` + `DocumentChunk` (1 rekord/chunk, status `pending`) + `DocumentTopicSection`. Jeden `session.commit()`. | REGEX/deterministyczne |

### Część 2a — `clean_article_text()` krok po kroku (wołane w kroku 3 wyżej, `article_cleaner.py:667`)

| # | Co robi w kolejności | Mechanizm |
|---|---|---|
| 1 | `_strip_leading_onet_ai_summary()` / `_strip_interia_chrome_blocks()` (per portal) | REGEX |
| 2 | `links_correct()` + `md_square_brackets_in_one_line()` — naprawa wieloliniowych linków/tagów markdown | REGEX |
| 3 | Usunięcie kart rekomendacji (`[![...` + `#### `) i sklejonych bloków tagów | REGEX |
| 4 | `_detect_h2_ads()` — wykrycie wstawek H2+obrazek PRZED usuwaniem obrazków | REGEX |
| 5 | Zamiana obrazków na markery `[imgN]` (pomijając emotki/tracking pixele/duplikaty) | REGEX |
| 6 | `_attach_image_captions()` — skojarzenie podpisu/credit ze zdjęciem (do `document_images`), potem `_strip_photo_caption_lines()` usuwa tę linię z treści | REGEX |
| 7 | `_find_footer_line()` — ucięcie od stopki portalu (jak w Części 1, krok 6) | REGEX |
| 8 | `_find_start_line()` — ucięcie nawigacji przed artykułem (tylko gdy tekst pochodzi z surowego `step_1_all.md`, nie z ekstrakcji LLM) | REGEX |
| 9 | Zamiana linków na markery `[linkN]` (linki wewnętrzne portalu zostają jako sam tekst) | REGEX |
| 10 | Usunięcie osieroconych referencji/markerów | REGEX |
| 11 | Normalizacja (`\xa0` → spacja, wielokrotne spacje → 1) | REGEX |
| 12 | `_clean_lines_generic()` + dispatch per-portal: `_clean_lines_onet/_money/_wp/_interia/_bankier/_gazeta/_ithardware()` — w tym `_remove_author_bio_paragraph()` dla money/wp (kotwica: linia `x@grupawp.pl o autorze`) | REGEX |

---

## Część 3 — Recenzja i embeddingi

- Reviewer na `/chunks/:id`: edycja linii, scalanie/dzielenie chunków, ręczne ✍️ Autor/📅 Data/📚
  Cytowania (te same funkcje LLM co wyżej, ale z konkretnym fragmentem jako input), zatwierdzenie
  chunków `TEMAT`, zamknięcie review (`PATCH /analysis_run/<id>` → `status=reviewed`).
- Zamknięcie z ≥1 zatwierdzonym chunkiem `TEMAT` **automatycznie odpala** `generate_embeddings_from_run()`
  w tle (`chunk_review_routes.py: update_run()` → `_start_embedding_job()`).
- `generate_embeddings_from_run()` (`document_analysis_service.py:818`): tylko chunki
  `TEMAT`+`approved` → `md_split_for_emb()` (hierarchicznie H1→H2→H3→bold→akapity→zdania) →
  `md_remove_markdown()` → embedding w paczkach po 32 (`EMBEDDING_BATCH_SIZE`), commit po
  każdej paczce. Ponowne uruchomienie usuwa stare embeddingi tego runu i generuje od nowa.

---

## Część 4 — Wyszukiwanie i rola tagów

`SearchService.search()` (`library/search_service.py`) łączy:
- **Lexical** — `DocumentRepository.search_text()`: SQL `ILIKE` po **skonkatenowanym** polu
  `title + tags + note + text` (`unaccent()`). **Jedyne miejsce, gdzie tagi uczestniczą w
  wyszukiwaniu** — nie ma osobnego, ustrukturyzowanego filtra "dokumenty z tagiem X".
- **Semantyczny** — `DocumentRepository.get_similar()`: pgvector cosine search po
  `document_embeddings` (embeddingi TYLKO z zatwierdzonej treści chunków, tagi nigdy nie są
  embeddowane osobno).
- Opcjonalnie `library/search/parser.py` — LLM parsuje naturalne zapytanie na `ParsedSearchQuery`
  → `sql_filters.py: build_document_filters()` (autor/wydawca/daty/okres historyczny) — **ale
  brak pola `tags` w `SearchFilters`.**

### Jeśli chcesz zmienić: gdzie by to weszło

- **Filtrowanie po tagu** (nie tylko boost lexical) → nowe pole w `SearchFilters`
  (`library/search/types.py`) + warunek w `sql_filters.py: build_document_filters()`, analogicznie
  do istniejącego `collection_name`.
- **Koszt `preclean`/`propose_article_cleanup`** (Część 2, krok 6) — jedyne miejsce, gdzie cały
  dokument idzie do LLM w paczkach; zawężenie okna (np. tylko ostatnie 20% dokumentu) obniżyłoby koszt.
- **Limit 15 000 znaków przy imporcie** (Część 1, krok 7) — dla nieznanego portalu z długim
  artykułem LLM nie widzi prawdziwego końca, a nie ma regexowego markera, który by to naprawił.
  Realne ryzyko cichego ucięcia treści — brak logowania tego przypadku.
- **Kolejność autor→biogram** — dziś biogram jest wycinany PRZED podziałem tylko gdy `doc.byline`
  znany z importu (krok 5). Dla portali bez deterministycznej ekstrakcji autor i tak zostanie
  wykryty (krok 13), ale PO podziale — ten konkretny run i tak dostanie biogram jako osobny chunk
  SZUM (za darmo, ale widoczny). Wyeliminowanie tego całkowicie wymagałoby przesunięcia wykrywania
  autora PRZED podział zawsze — kosztem 1 dodatkowego LLM call na starcie KAŻDEGO runu.

---

## Szybka tabela: co jest czym (skrót)

| Etap | Mechanizm |
|---|---|
| Pobranie HTML → markdown | REGEX |
| Wykrycie granic artykułu — początek | **LLM** (zawsze) |
| Wykrycie granic artykułu — koniec | **REGEX** gdy portal znany, **LLM** tylko jako fallback |
| Limit 15 000 zn. przed wysłaniem do LLM | REGEX (obcinanie, bez logowania strat) |
| Autor (import, wp/o2/money) | REGEX/HTML |
| Czyszczenie per-portal (`clean_article_text`) | REGEX (w całości) |
| Biogram autora — wycięcie | REGEX |
| Data publikacji z artefaktu względnego | REGEX |
| Rozdziały (książki) | REGEX (nagłówki md) |
| Wykrywanie reklam/szumu przed podziałem (`preclean`) | **LLM** (całość dokumentu, kosztowne) |
| Podział na chunki | REGEX |
| Klasyfikacja + streszczenie chunka | **LLM** (1 call/chunk) |
| Grupowanie w sekcje tematyczne | **LLM** |
| Synteza | **LLM** |
| Tagi tematyczne | **LLM** |
| Tagi krajowe (`kraj-*`) | regex prescreen + **LLM** potwierdzenie |
| Autor — fallback (11b2) | **LLM** |
| Ocena staranności | regex kary + **LLM** rubryka (1 call) |
| Encje NER (osoby/miejsca) | **SERWIS** (spaCy, nie LLM) |
| Weryfikacja miejsc | **SERWIS** (LocationIQ) + **LLM** |
| Rozwiązywanie osób | **SERWIS** (Wikidata) + **LLM** + fuzzy |
| Biogram autora → opis osoby | **LLM** |
| Źródła informacji / cytowania | **LLM** |
| Embeddingi | model embeddingowy (provider), regex tylko do splitu markdown |
| Wyszukiwanie lexical | REGEX/SQL ILIKE (tagi tu uczestniczą) |
| Wyszukiwanie semantyczne | wektory (pgvector) |
| Parsowanie zapytania naturalnego | **LLM** (opcjonalne) |

---

## Powiązane dokumenty

- [`docs/search-hybrid.md`](search-hybrid.md) — szczegóły scoringu i mergowania wyników lexical/vector.
- [`docs/ner-integration-plan.md`](ner-integration-plan.md) — architektura mikroserwisu NER.
- [`docs/deployment/nas/storage-and-jobs-migration-plan.md`](deployment/nas/storage-and-jobs-migration-plan.md) — plan przeniesienia batchowych skryptów na kolejkę jobów.
- `backend/library/CLAUDE.md` — pełna lista modułów z jednolinijkowym opisem każdego.

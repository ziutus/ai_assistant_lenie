# Backend Library — CLAUDE.md

Core library for Project Lenie providing document processing, LLM abstraction, embedding generation, and database persistence.

## Directory Structure

```
library/
├── db/               # SQLAlchemy ORM layer
│   ├── models.py     # Document, DocumentEmbedding ORM models
│   └── engine.py     # Engine & session factories (get_session, get_scoped_session)
├── models/           # Data classes and enums (domain objects)
├── website/          # HTML download, parsing, paywall detection, content cleanup
├── api/              # External service integrations
│   ├── openai/       # OpenAI chat completions & embeddings
│   ├── aws/          # Bedrock, S3, Comprehend
│   ├── google/       # Vertex AI (Gemini)
│   ├── cloudferro/sherlock/  # Bielik Polish LLM & embeddings
│   └── asemblyai/    # Speech-to-text transcription (sole provider, ADR-011)
├── ai.py             # LLM provider abstraction (routes to api/*)
├── embedding.py      # Embedding provider abstraction (routes to api/*)
├── document_analysis_service.py  # Chunk analysis pipeline: split (chapter-aware for YouTube) → LLM rewrite/summarize → topics → synthesis → tagging → DB
├── chunk_llm_analysis.py         # LLM chunk primitives: speaker extraction, rewrite, summarize
├── chunk_review_routes.py        # Flask blueprint: chunk analysis REST API (runs, chunks, topic sections)
├── analysis_exports.py           # Analysis run file exports (MD/JSON/debug/HTML) to .claude/exports/
├── article_extractor.py     # LLM-based article boundary extraction (Bielik markers + regex drafts)
├── article_pipeline.py      # Shared pipeline: step_1 raw markdown (cache/S3) + LLM article extraction
├── article_cleaner.py       # Portal artifact cleanup of extracted article markdown ([imgN]/[linkN] markers)
├── article_tagging.py       # LLM thematic tagging & country extraction (TAGGING_MODEL config)
├── country_gazetteer.py     # Non-LLM country-name detection (stem-based gazetteer, ~190 countries)
├── ner_client.py            # HTTP client for the NER microservice (ner_service/, NER_SERVICE_URL config)
├── entity_service.py        # Persist NER entities per document (document_entities table, replace semantics)
├── locationiq_client.py     # LocationIQ geocoding + match-quality check (LOCATIONIQ_API_KEY config)
├── overpass_client.py       # Overpass API: pipeline routes by name (infra_geometries cache, reader map)
├── references.py            # Book footnote extraction: text_md -> document_references (reader "Przypisy")
├── place_verification.py    # NER place candidates → geocoder (geocode_cache) → LLM → miejsce-* tags
├── wikidata_client.py       # Wikidata person search (humans only, P31=Q5) for disambiguation
├── person_registry.py       # NER person mentions → alias/Wikidata+LLM/fuzzy → document_persons links
├── search/           # Typed search domain models + parser + SQL filters (stages 1-6, complete, of docs/search-rebuild-implementation-plan.md)
│   ├── types.py      # ParsedSearchQuery, SearchFilters, SearchRequest, SearchFeedback + enums; frozen dataclasses validated at construction (SearchQueryValidationError), target domain names (published_on, subject_period_*), normalize_*_range() helpers for the future parser
│   ├── audit_repository.py  # record_interpretation()/record_feedback() write search_interpretation_logs in their OWN session (a failed audit write is swallowed, never breaks the search path); field-length caps applied here (raw_query→MAX_QUERY_LENGTH, raw_response→20k, error_message→500, visible TRUNCATION_SUFFIX); parsed_query_to_dict() serializes ParsedSearchQuery to JSONB; delete_expired_interpretations() = 90-day retention sweep (ADR-017, errors propagate — maintenance path)
│   ├── parser.py     # parse_search_query(raw_query) → SearchQueryParseResult — the natural-language entry point, independent of the Slack bot's test command parser. ALWAYS returns a usable ParsedSearchQuery: on any failure (LLM exception, invalid/truncated JSON, a response that fails ParsedSearchQuery's own validators) it synthesizes a literal-phrase fallback (query=raw text, model_confidence=LOW) rather than raising. The user's raw text is passed only as the user-role message content, never concatenated into SEARCH_QUERY_SYSTEM_PROMPT — the Polish system prompt explicitly tells the model to treat the entire user message as content to interpret, never as instructions, defending against prompt injection. Uses ai_ask()'s response_format (a full JSON Schema, `_RESPONSE_SCHEMA`, all 22 ParsedSearchQuery-facing fields required, `additionalProperties: false`) and temperature=0. Reversed year/date/datetime ranges from the LLM are swapped via normalize_*_range() (stage 1) *before* constructing ParsedSearchQuery, since the frozen dataclass rejects them outright; every other field is handed through as-is and validated exclusively by ParsedSearchQuery.__post_init__ — the parser does not duplicate validation logic. `subject_period_relation`/`subject_period_anchor_text` (stage 5) are an LLM-optional fallback: only consulted via `temporal.enrich_subject_period()` when the model leaves both `subject_period_start_year`/`subject_period_end_year` null — an explicit numeric year from the LLM is never overridden. Every attempt writes exactly one search_interpretation_logs row via record_interpretation(), regardless of outcome. **Verified live against CloudFerro Sherlock**: the plan's headline example correctly extracted subject_period_start_year=1945; a harder query resolved author/publisher/domain/document_type/language/sort/date-range in one call; a query mentioning "upadek muru berlińskiego" left the year null and set the relation/anchor fields, which the backend then deterministically resolved to 1989.
│   ├── temporal.py   # TemporalRelation (exact/before/after/between/around) + a small versioned HISTORICAL_ANCHORS dict (ANCHOR_DICTIONARY_VERSION; bump on any edit — a wrong entry silently mis-dates every future query mentioning it) + resolve_relation()/resolve_anchor()/enrich_subject_period() (stage 5). Deterministic, auditable year arithmetic instead of trusting the LLM's own computation for well-known historical anchors. enrich_subject_period() ONLY ever reads/returns subject_period_start_year/subject_period_end_year — it cannot touch published_on_*/ingested_at_* even by accident, which is the stage 5 acceptance criterion ("a historical period can never accidentally become a publication date"). AROUND always carries a Polish approximation warning; an anchor the dictionary doesn't recognize leaves the bounds null with a diagnostic warning rather than guessing.
│   ├── sql_filters.py  # the ONE shared filter builder (stages 6-7): publisher via publisher_id subqueries; author via role='author' canonical/alias EXISTS plus byline fallback only for unnormalized docs; discovery source via discovery_sources/discovery_source_id (stage 11d). Never joins information_sources.
│   └── name_resolution.py  # explicit 0/1/N author and discovery-source matches; id is None unless exactly one
├── search_routes.py  # stage 8 Blueprint: POST /search/parse, POST /search, POST /search/<id>/feedback. Strict validated JSON; explicit requests skip LLM; ambiguity returns clarification; resolver failure degrades safely; the legacy /website_similar endpoint was removed in stage 12.
├── llm_usage/        # Central LLM usage & cost accounting (stages 2-3b of the search-rebuild plan)
│   ├── pricing.py    # estimate_cost() — Decimal-only per-token cost math (float money raises PricingError), PricingMode/CostStatus enums, UNKNOWN_COST sentinel; the ONLY place allowed to compute LLM call costs; backing tables: search_interpretation_logs, llm_pricing, llm_usage_logs (db/models.py)
│   ├── recorder.py   # record_llm_usage() — the SINGLE write path for llm_usage_logs (exactly one row per LLM call); snapshots the active llm_pricing row, reported cost (Decimal + currency) beats the local estimate, missing price → cost_status='unknown' (never an error, never 0); own session, DB failures (incl. SystemExit from config_loader.require()) swallowed (usage_log_id=None); wired into ai.py
│   └── report.py     # usage_report()/combine_usage_reports() — shape response.usage (a UsageRecord) into JSON-friendly dicts for the diagnostic reports timeline_events.py/tones.py/time_periods.py return from their per-fragment/per-chapter extraction functions; cost is only ever read from usage.cost, never recomputed; replaces the pre-stage-3b `_response_usage()`/`_combine_costs()` duplication in timeline_events.py that other modules imported privately (and that always returned cost=None — AiResponse never had cost_usd/cost/credits_used)
├── document_repository.py  # Query layer (ORM, list, search, similarity)
├── year_normalization.py    # coerce_year(value, minimum, maximum) — shared "raw JSON value → plausible year, BCE negative, or None" coercion (search-rebuild stage 5), used by time_periods.py and available to library/search/temporal.py; never raises, bounds are caller-supplied so unrelated features aren't forced to agree on a shared range
├── text_functions.py        # Text processing & splitting utilities
├── text_detect_language.py  # Language detection abstraction
├── text_transcript.py       # Transcript/chapter parsing utilities
├── transcript.py            # Transcription service abstraction
├── lenie_markdown.py        # Markdown processing & splitting for embeddings
├── document_markdown.py     # Markdown image/link reference extraction
├── google_auth.py           # Google OAuth 2.0 utilities
└── stalker_youtube_file.py  # YouTube metadata extraction & download
```

## Key Modules

### Domain Model & Database

- **`db/models.py`** — `Document` SQLAlchemy ORM model: ~30 attributes covering URL, text content (raw/English/markdown), metadata, processing state. Methods: `get_by_id()`, `get_by_url()`, `populate_neighbors()`. `DocumentEmbedding` model for vector embeddings — optional `chunk_id` FK to `DocumentChunk`, set when the embedding was generated from a reviewed chunk (`generate_embeddings_from_run()`) rather than the fallback whole-document split.
- **Chunk analysis models** (backing `chunk_review_routes.py` / `document_analysis_service.py`):
  - `DocumentAnalysisRun` — one row per analysis pass over a document. `mode`: `transcript` (YouTube/movie STT — LLM rewrite + speaker labeling, chunk splitting by sentence) or `article` (webpage/link/text/book chapters — no rewrite step, markdown is already clean, so every chunk's `corrected_text` stays `None` by design; split by markdown headings). `status`: run review workflow, `created` → `in_review` → `reviewed` (`PATCH /analysis_run/<id>`), plus `superseded` — set automatically by `create_run()` on an unfinished sibling run of the same `document_id`+`scope` (abandoned attempt: double click, retry) when a new run for that scope lands; its still-open chunks are flipped to `skipped` and the run drops out of the "missing Obsidian notes" filter and all "latest run" queries (one-off backfill: [`imports/fix_duplicate_analysis_runs.py`](../imports/CLAUDE.md)). `scope`: human-readable analysed range (e.g. a book chapter title), `NULL` = whole document — a document can have several runs (e.g. one `split_only` run over a whole book plus one `article` run per chapter; different scopes never supersede each other).
  - `DocumentChunk` — one row per chunk of a run. `type`: `TEMAT` (on-topic) / `REKLAMA` (sponsored) / `SZUM` (extraction junk — portal nav, cookie banners; auto-approved, never sent to an LLM for note-writing). `status`: `pending` → `approved` (or `needs_reanalysis`/`split_requested`/`split`/`skipped`). `obsidian_note_paths` — array of vault-relative paths, populated by the `/obsidian-note` skill when a note is written from the chunk.
  - `DocumentTopicSection` — LLM-synthesized grouping of a run's chunks by topic (`chunk_positions` array of `DocumentChunk.position`). Drives the book/chapter drill-down view in `/chunks/:id` for runs above `SECTION_VIEW_THRESHOLD` chunks. Coverage is partial by design — LLM synthesis doesn't always assign every chunk to a section.
  - `DocumentRemovedLine` — training data for `article_cleaner.py`: lines a human removed from a chunk/document during review (`source`: `manual` or `szum_chunk`). Survives run/chunk deletion (`run_id`/`chunk_id` FKs are `SET NULL`) so aggregate queries (e.g. most-removed lines per portal) keep working after runs are re-created.
- **`db/engine.py`** — SQLAlchemy engine and session factories: `get_session()`, `get_scoped_session()`.
- **`document_repository.py`** — `DocumentRepository`: query layer using SQLAlchemy session. Requires `session` parameter. Methods: `get_list()` (paginated/filtered), `get_similar()` (pgvector cosine search), `search_text()` (lexical `ILIKE` candidate search, diacritic-folded via `unaccent()`), `list_by_filters()` (filter-only listing, no text/embedding query — stage 6 session B; empty `filters` legally lists everything newest-first, `sort` maps `SearchSort` to `published_on`/`created_at` ordering, `RELEVANCE` falls back to `INGESTED_DESC`'s ordering since there's no query to score against), `get_next_to_correct()`, `get_count()`, `embedding_add()`, `embedding_delete()`. `get_similar()`, `search_text()` and `list_by_filters()` all accept an optional `filters: SearchFilters` (stage 6) applied via `search.sql_filters.build_document_filters()` — the same builder for all three, so lexical, vector and filter-only search share identical constraints (stage 11c removed the legacy single-value `project` kwarg — collection filtering goes through `filters.collection_name`, resolved against the `collections` lookup table).
- **`publisher_registry.py`** — deterministic stage-7A resolution of `publisher_name`/`publisher_domain`. `resolve_publisher()` returns `PublisherResolution.matches` with cardinality 0/1/N; `.publisher_id` is populated only for exactly one match. Names are exact after case/diacritic folding, domains after lowercase/`www.` normalization. Never use `.first()` to hide ambiguity. Publishers are publication portals and must never be confused with discovery `Source` or `InformationSource` provenance.
- **`search/name_resolution.py`** — stage-7B read-only resolution for author and discovery-source names. Returns every exact case/diacritic-insensitive canonical/alias match ordered by id; `.id` is only set for cardinality 1. Physical `DiscoverySource` means discovery channel in all new code. `InformationSource` is unrelated claim provenance and is never queried here.
- **`search_routes.py` / stage-8 `SearchService.search()`** — the new HTTP contract accepts natural or explicit requests. Query-less calls delegate without embedding; hybrid calls pass complete filters to lexical/vector paths, fetch enough candidates for offset pagination, apply requested published/ingested sorting, then slice. Invalid JSON/domain values return 400, unknown feedback returns 404, execution failures return a detail-free 503.
- **`search_service.py`** — `SearchService`: hybrid search orchestrator behind `POST /search`. `search()` combines `search_text()` (lexical) and `get_similar()` (semantic/pgvector) candidates, then `_merge_results()` scores and de-duplicates them using its own Python-side diacritic folding (`_normalise()`), which must stay behaviorally aligned with the SQL-side `unaccent()` folding in `search_text()`; filters are a `SearchFilters` applied identically to both repo calls in SQL, before `LIMIT`. A missing query is filter-only: `search_by_filters()` delegates to `list_by_filters()` and never calls `embedding.get_embedding()` (no wasted latency/cost for a query with no text to embed). Embedding failure degrades to lexical-only results; it raises RuntimeError only when there are no lexical hits either. The legacy `search_similar()` (`/website_similar`) path was removed in stage 12. Performance measurements and the ILIKE-vs-FTS / HNSW decisions live in [`docs/search-hybrid.md`](../../docs/search-hybrid.md).

**Database tables:** `public.documents` (31 columns), `public.document_embeddings` (vector similarity, optional `chunk_id` FK), `public.document_analysis_runs`, `public.document_chunks`, `public.document_topic_sections`, `public.document_removed_lines` — see [`database/CLAUDE.md`](../database/CLAUDE.md) for full column definitions.

### Models (`models/`)

| File | Class/Enum | Purpose |
|------|------------|---------|
| `stalker_document_status.py` | `StalkerDocumentStatus` | 15 processing states (URL_ADDED → EMBEDDING_EXIST) |
| `stalker_document_status_error.py` | `StalkerDocumentStatusError` | 14 error types |
| `stalker_document_type.py` | `StalkerDocumentType` | 8 document types (movie, youtube, link, webpage, text_message, text, email, social_media_post) |
| `ai_response.py` | `AiResponse` | LLM response container (text, tokens, model info) |
| `embedding_result.py` | `EmbeddingResult` | Single embedding result (vector, status, token count) |
| `embedding_results.py` | `EmbeddingResults` | Batch embedding results |
| `webpage_parse_result.py` | `WebPageParseResult` | HTML parse output (text, title, language, summary) |

### LLM Abstraction (`ai.py`)

Entry point: `ai_ask(query, model, temperature, max_token_count, top_p, *, system_prompt=None, response_format=None, operation="ai_ask", search_interpretation_log_id=None) → AiResponse`

Supported models:
- **OpenAI**: gpt-3.5-turbo, gpt-4, gpt-4o, gpt-4o-mini
- **AWS Bedrock**: amazon.titan-tg1-large, amazon.nova-micro, amazon.nova-pro
- **Google Vertex AI**: gemini-2.0-flash-lite-001
- **CloudFerro**: Bielik-11B-v2.3-Instruct, Bielik-11B-v3.0-Instruct (Polish)
- **ARK Labs**: `arklabs/<model>` (stateless/stateful GPU session variant)

Documents and prompts stay in their source language; there is no automatic translation helper or pipeline.

**Stage 3 of the search-rebuild plan (docs/search-rebuild-implementation-plan.md).** `system_prompt` is sent as a real system-role message — never string-concatenated with the user prompt — for providers that support it (`cloudferro`, `arklabs`); passing one for any other provider raises `ValueError`. `response_format` is forwarded to Sherlock only (`cloudferro`); other providers raise `ValueError`. **Verified live against CloudFerro Sherlock (2026-07-18):** `{"type": "json_schema", "json_schema": {...}}` is honored — the schema's required keys are imposed on the model's output — but `{"type": "json_object"}` is rejected with HTTP 400, so structured output requires a full JSON Schema, not the bare "give me JSON" mode. Provider-specific token field names (`prompt_tokens`/`completion_tokens` vs Bedrock's `input_tokens`/`output_tokens`) are unified internally before recording usage. After every call (success or exception) `ai_ask()` writes exactly one `llm_usage_logs` row via `library.llm_usage.recorder.record_llm_usage()` and attaches the resulting `UsageRecord` (tokens, latency, `usage_log_id`, `CostEstimate` with status) to `response.usage`; recorder failures (including `SystemExit` from `config_loader.require()` when DB config is absent) are logged and swallowed so a bad usage write never breaks the LLM call. `AiResponse` intentionally has **no** `cost_usd`/`cost`/`credits_used` attributes — cost lives only in `response.usage.cost`. Stage 3b removed the modules that used to probe for those dead attribute names (`timeline_events._response_usage()`/`_combine_costs()`, privately imported by `tones.py`/`time_periods.py`); all three now build their diagnostic reports via `library/llm_usage/report.py`.

**Stage 10 evaluation.** `library/search/evaluation.py` scores the partial expectations in `tests/fixtures/search_query_cases.json`: JSON-safe domain serialization, explicitly pinned fields only, and aggregate JSON validity, field accuracy, latency, tokens and same-currency cost. `imports/evaluate_search_queries.py` runs the real parser sequentially and, unless `--keep-audit` is passed, deletes only the exact audit/usage IDs produced by that run. The first real Bielik baseline is in `docs/search-rebuild-bielik-baseline.md`.

### Embedding Abstraction (`embedding.py`)

Entry point: `get_embedding(model, text) → EmbeddingResult`

Supported models:
- **AWS Bedrock**: amazon.titan-embed-text-v1, amazon.titan-embed-text-v2:0
- **OpenAI**: text-embedding-ada-002
- **CloudFerro**: BAAI/bge-multilingual-gemma2

### Text Processing

- **`article_pipeline.py`** — shared pipeline used by `imports/dynamodb_sync.py` and `imports/article_browser.py`: `ensure_raw_markdown(doc, cache_dir)` (returns `{id}_step_1_all.md` from cache, or downloads HTML via `document_prepare.prepare_markdown` and persists it), `extract_article(doc, cache_dir, skip_llm, arklabs_first)` (raw markdown + `article_extractor.process_article_with_llm_fallback`; returns `(raw_markdown, extracted_article)` tuple). Dependencies imported lazily (markitdown is an optional extra). Unit-tested (`tests/unit/test_article_pipeline.py`).
- **`article_cleaner.py`** — `clean_article_text(text, url)`: cleans extracted article markdown from portal artifacts (ads, video player controls, premium sections). Replaces images/links with `[imgN]`/`[linkN]` markers and returns them as separate lists; each image dict also carries `caption_text`/`caption_category` when a caption/credit line was found next to its marker (`article_quality.photo_caption_candidates()`, attached right after marker substitution, before further cleanup can drop the caption line) — persisted via `library/document_images.py:replace_document_images()` at the three call sites that save `text_md`. Generic rules + per-portal rules (onet, money, wp). Unit-tested (`tests/unit/test_article_cleaner.py`).
- **`document_images.py`** — `replace_document_images(session, document_id, images, chunk_id=None)`: replace-per-document write of `clean_article_text()`'s `images` list into `document_images` (preserves the URL that used to be discarded once replaced by an `[imgN]` marker).
- **`article_tagging.py`** — `tag_article_with_llm()` (thematic categories from `THEMATIC_TAGS`), `extract_countries_with_llm()` (open-ended LLM extraction, `kraj-*` tags), `extract_countries_hybrid()` (preferred: `country_gazetteer.detect_countries()` prescreen — no LLM call if no candidates — then a single LLM call to confirm which candidates are clearly discussed, constrained to the candidate list so the LLM cannot invent a country). Model configurable via `TAGGING_MODEL` (default: Bielik). `COUNTRY_TAG_TRIGGERS` — thematic tags that trigger automatic country extraction. Called from two places: `article_browser.py`'s `[w]`/`[k]` actions, and `document_analysis_service.create_run()` (`_apply_tags()`, step 11b) using the run's synthesis text (or concatenated topic summaries as fallback) as input — merges into `doc.tags` rather than overwriting, so repeat/per-chapter runs accumulate tags instead of clobbering them.
- **`ner_client.py`** — HTTP client for the internal NER microservice (`ner_service/`, spaCy `pl_core_news_lg`): `extract_entities(text)` (raw mentions with lemmas; long texts are processed in 200k-char windows cut at whitespace, capped at 2M chars total — a 1.5M-char book used to be silently truncated to the first window; a mid-run failure returns the mentions collected so far, an immediate failure returns an empty list — service unavailability must never fail a pipeline), `aggregate_entities_detailed()` (groups by `(entity_type, lemma)` with counts + distinct surface variants — Polish inflected variants of the same name collapse into one row but their surface forms are kept for chapter-scoped matching; `aggregate_entities()` is the counts-only view), `warmup_async()` (fire-and-forget background probe that pre-loads the spaCy model, called at the start of `article_browser.py --review` and the youtube analysis scripts so the ~90s post-restart model load overlaps with other work). Service URL from `NER_SERVICE_URL` config (default `http://lenie-ner-service:8090`). See [`docs/ner-integration-plan.md`](../../docs/ner-integration-plan.md).
- **`entity_service.py`** — `refresh_document_entities(session, doc_id, text)` (NER → aggregate → drop entities matched by an `ner_exclusions` rule (`is_excluded()`: case-insensitive text, `entity_type='*'` wildcard, scope `global`/`author`) → replace the document's `document_entities` rows incl. surface `variants`; empty extraction leaves existing rows untouched), `get_document_entities(session, doc_id)` (grouped by type, most-mentioned first, each item carries its row `id` + `variants`; place entities carry `verified`/`lat`/`lon`/`display_name` from their `geocode_cache` link; resolved persons carry `link_id`), `filter_entities_to_text(grouped, text)` (chapter-scoped attribution: subset of the already-verified entities whose surface variants appear in the given text — word-start prefix match, so "Iran" finds "Iranie"; kept items get their `count` replaced with the LOCAL mention count and re-sorted by it, originals untouched; backs `GET /document/<id>/chapter/<pos>/entities` in `chunk_review_routes.py`, used by the `/read` sidebar scope toggle). Called from `document_analysis_service.create_run()` (step 11c, whole-document runs only), `article_browser.py` (`[w]`/`[e]` actions) and the `/website_entities` endpoints in `server.py`.
- **`locationiq_client.py`** — `geocode(query)` (LocationIQ search, `LOCATIONIQ_API_KEY` from config/Vault, free-tier rate limiting, `None` on miss/failure), `is_plausible_match(query, hit)` (fuzzy name-similarity guard — rare Polish exonyms fuzzy-match to wrong places, e.g. "Cieśnina Ormuz" → a lake strait near Iława, so a bare hit is not proof the place exists), `canonical_place_name(query, display_name)` (the display_name part most similar to the query — the geocoder's canonical spelling of the place, used to converge inflected NER variants like "Kijowa"/"Kijów" on one form).
- **`place_verification.py`** — `verify_document_places(session, doc, text)`: the document's `geogName`/`placeName` entities → geocoder via `geocode_cache` (one live call ever per distinct name, negative results cached) → `article_tagging.confirm_places_with_llm()` picks the places actually discussed → `miejsce-<slug>` tags merged into `doc.tags`. Tags are slugged from the geocoder's canonical spelling (`canonical_place_name`), not the NER surface form — spaCy doesn't always lemmatize proper names, so "Kijów"/"Kijowa" used to yield duplicate tags; entities sharing a canonical name merge their mention counts before the auto-confirm threshold and LLM check. Countries are skipped (own `kraj-*` pipeline). Called from `create_run()` step 11d, `article_browser.py` (`[w]`/`[e]`) and `POST /website_entities`. One-off cleanup of pre-existing duplicate tags: [`imports/fix_place_tags.py`](../imports/CLAUDE.md).
- **`overpass_client.py`** — Overpass API (OSM/Open Infrastructure Map data, © OpenStreetMap/ODbL): `fetch_pipeline(name)` (anchored case-insensitive name match on `man_made=pipeline` ways/relations, returns simplified GeoJSON MultiLineString + `substance`/`wikidata` tags; raises `OverpassUnavailable` on transport failures so a flaky shared server can't poison the cache; sends an identifying User-Agent — overpass-api.de rejects generic UAs with 406), `get_or_fetch_pipeline(session, name)` (cache-through via `infra_geometries`, clean misses cached), `attach_document_pipelines(session, doc_id)` (for place entities the geocoder checked but rejected, ≥2 mentions — "Baltic Pipe" has no point hit but has an OSM route; called from `POST /website_entities` after person resolution). Geometries surface as `"pipeline"` on place items in `get_document_entities()` and render as dashed polylines on the reader map (`CountryMap`).
- **`references.py`** — book footnote extraction: `extract_footnotes(text)` (pure: (clean text, footnotes with marker/text/first URL/char offset); superscript-marked lines always count, digit-marked lines (1-99) need a bibliographic signal — URL, "(dostęp:", a year, legal/citation phrases, or a short period-ended sentence — so narrative paragraphs starting with a number stay untouched), `refresh_document_references(session, doc)` (replace semantics; assigns each footnote to its reader chapter via `detect_chapters` on the original text and UPDATES `doc.text_md` to the cleaned version — footnote lines used to pollute NER, e.g. "¹¹ stat.gov.pl/..." became a person entity). CLI: [`imports/extract_references.py`](../imports/CLAUDE.md); reader API: `references` in `GET /document/<id>/chapter/<pos>`.
- **`wikidata_client.py`** — `search_persons(name)`: wbsearchentities + wbgetentities, returns only entities that are humans (P31=Q5) with label/description — the description is the LLM's disambiguation context. Empty list on miss or failure.
- **`person_registry.py`** — `resolve_document_persons(session, doc, text)`: per `persName` mention, a cascade — exact alias/canonical match (`alias_matched`, no network) → Wikidata humans + `article_tagging.confirm_person_with_llm()` (LLM picks a QID from the closed candidate list or NONE — e.g. Donald Tusk the politician vs his father) → junk guard (single-word mention without a Wikidata human is skipped: spaCy noise like "Hornet") → pg_trgm fuzzy match against the registry (`manual_review`, never auto-merged) → new `Person` without QID (`manual_review`). Also `get_document_persons()` for the API. Called from `create_run()` step 11e, `article_browser.py` (`[w]`/`[e]`) and `POST /website_entities`; search endpoints: `GET /persons?q=`, `GET /person_documents?id=`. Review-queue helpers backing `GET/PATCH /persons_review`: `list_manual_review()` (queue entries with document context), `approve_review_link()` (→ `manual_confirmed`), `reject_review_link()` (deletes the link, drops the person if orphaned), `merge_review_link()` (re-points the link to a target person, records the mention + source canonical name as target aliases, drops the orphaned source person; a duplicate link in the same document is deleted instead of re-pointed).
- **`country_gazetteer.py`** — `detect_countries(text) -> list[CountryEntry]`: rule-based (no LLM) country-name detection via word-stem regex matching on diacritic-stripped text (`unidecode`), covering ~190 UN member/observer states + Taiwan/Kosovo. A candidate generator, not a topic classifier — deliberately over-matches (adjectives, demonyms, passing mentions); callers filter further (see `extract_countries_hybrid()`). Capitals are not matched (ambiguity: e.g. Sofia is also a first name).
- **`text_functions.py`** — `split_text_for_embedding()`, regex-based text removal (`remove_last_occurrence_and_after`, `remove_before_regex`, `remove_after_regex`), SHA256 hashing.
- **`lenie_markdown.py`** — `md_split_for_emb()` (recursive hierarchical splitting: H1→H2→H3→bold→paragraphs→sentences), link/image extraction, markdown cleanup.
- **`document_markdown.py`** — `DocumentMarkDown` class: converts inline images and links to numbered references.
- **`text_transcript.py`** — Chapter/timestamp parsing, transcript splitting by chapters (for YouTube).

### Website Processing (`website/`)

- **`website_download_context.py`** — `download_raw_html()`, `webpage_raw_parse()` (BeautifulSoup), `webpage_text_clean()` (applies site-specific rules from `data/site_rules.json`).
- **`website_paid.py`** — `website_is_paid(link)` — hard-coded paywall detection (wyborcza.pl, onet.pl premium paths).
- **`website_text_clean_regexp.py`** — Site-specific regex cleanup rules for Polish news sites (WP, Onet, Interia, Newsweek, BusinessInsider, etc.).

### API Integrations (`api/`)

| Subdir | Key Functions | Auth |
|--------|--------------|------|
| `openai/openai_my.py` | `OpenAIClient.get_completion()`, `get_completion_image()` | `OPENAI_API_KEY` |
| `openai/openai_embedding.py` | `get_embedding()` (ada-002) | `OPENAI_API_KEY` |
| `aws/bedrock_ask.py` | `query_aws_bedrock()`, `aws_bedrock_describe_image()` | AWS credentials |
| `aws/bedrock_embedding.py` | `get_embedding()` (Titan v1), `get_embedding2()` (Titan v2) | AWS credentials |
| `aws/s3_aws.py` | `s3_file_exist()`, `s3_take_file()` | AWS credentials |
| `aws/text_detect_language_aws.py` | `detect_text_language_aws()` (Comprehend) | AWS credentials |
| `aws/credentionals.py` | `validate_credentials()` (STS) | AWS credentials |
| `google/google_vertexai.py` | `connect_to_google_llm_with_role()` | `GCP_PROJECT_ID`, `GCP_LOCATION` |
| `cloudferro/sherlock/sherlock.py` | `sherlock_get_completion()` | `CLOUDFERRO_SHERLOCK_KEY` |
| `cloudferro/sherlock/sherlock_embedding.py` | `sherlock_create_embedding()`, `sherlock_create_embeddings()` | `CLOUDFERRO_SHERLOCK_KEY` |
| `asemblyai/asemblyai_transcript.py` | `transcript_assemblyai()` | `ASSEMBLYAI` |

### Other Modules

- **`transcript.py`** — Transcription via AssemblyAI (sole provider, ADR-011) + `transcript_price()` cost calculator + `get_assemblyai_price_per_minute()` per-model pricing.
- **`google_auth.py`** — Google OAuth 2.0 credential management with token caching.
- **`stalker_youtube_file.py`** — `StalkerYoutubeFile`: YouTube URL validation, metadata via `pytubefix`/`yt-dlp`, video download, transcript loading/splitting by chapters.

## Patterns & Conventions

- **Provider abstraction**: `ai.py` and `embedding.py` act as routers — they inspect the model name and delegate to the appropriate `api/*` module. New providers should follow this pattern.
- **SQLAlchemy ORM**: Database access uses SQLAlchemy ORM (`db/models.py`, `db/engine.py`). `Document` model handles single-document CRUD; `DocumentRepository` handles queries and vector search. Connection supports optional SSL via `POSTGRESQL_SSLMODE` env var (required for AWS RDS).
- **Data classes**: Models in `models/` are plain Python classes (not dataclasses or Pydantic). They use `__init__` with explicit attributes.
- **Environment-driven config**: All API keys and connection strings come from environment variables (loaded via `dotenv`).
- **Site-specific rules**: Website content cleanup uses regex rules defined in `data/site_rules.json` and `website/website_text_clean_regexp.py`, targeted at Polish news sites.

## Environment Variables

```
# Database
POSTGRESQL_HOST, POSTGRESQL_DATABASE, POSTGRESQL_USER, POSTGRESQL_PASSWORD, POSTGRESQL_PORT
POSTGRESQL_SSLMODE  # Optional: set to 'require' for RDS encrypted connections

# LLM / Embedding providers
OPENAI_API_KEY, OPENAI_ORGANIZATION
AWS_REGION
GCP_PROJECT_ID, GCP_LOCATION
CLOUDFERRO_SHERLOCK_KEY
ASSEMBLYAI

# App config
EMBEDDING_MODEL, TAGGING_MODEL, ENV_DATA, DEBUG
```

# Frontend (React) — CLAUDE.md

React 18 single-page application for managing documents and running AI operations (text correction, embedding, similarity search). Built with **Vite** and **TypeScript**.

**App version**: 0.3.17.12 | **Package version**: 0.3.17.12

2026-09-10 (0.3.17.2): added piggyback browse telemetry to Document List and Search, with per-tab sessions and criterion provenance.

## Pages & Routes

All protected routes wrapped in `RequireAuth` → `Layout` → `Authorization`. Unauthenticated users redirected to `/connect`.

## UX conventions

### Pagination for collection views

Any view that can list more than 50 records must use pagination. The backend
endpoint must accept `limit` and `offset` and return `total`; preserve both
the current page and page size in the URL so the view can be shared and
restored. Reuse `src/modules/shared/components/Pagination/pagination.tsx`
instead of duplicating navigation controls. Views that intentionally load a
single document progressively (for example, chunk review) may use a
"load more" interaction instead.

### Voice of status labels

Labels that record a decision are worded by who made it: first person when the
user decided (`Obserwuję`, `Porównuję`, `Testuję`, `Używam`, `Odrzuciłem` — the
Tool Radar tabs), third person when an LLM or the system decided (`System
odrzucił`, `Model zaproponował`). Never mix the voices within one label set;
action buttons stay imperative. The short rule for agents lives in
[AGENTS.md](AGENTS.md); keep the two in sync.

### Multi-value filters

The short rule agents must follow when choosing a selection control lives in
[AGENTS.md](AGENTS.md); keep the two in sync.

Use `src/modules/shared/components/MultiSelectFilter/MultiSelectFilter.tsx`
for expandable multi-value checkbox filters (contact groups and document
topics, document types and statuses). It is controlled by `options`, `selectedValues`, `onChange`, and
`labels`, with an optional separate `emptyOption` and `onTelemetry` callback.
The trigger shows `Wszystkie [kategorie]` or `<Label>: wybrano N`.
The menu provides `Zaznacz wszystkie`, `Odznacz wszystkie`, and
`Odwróć wybór`; every option, including the empty value, has a `tylko`
button that selects that value alone. Every action invokes the telemetry
callback when supplied. Native `<details>` closes on outside `pointerdown`
via a document listener and a ref. Optional `variant="select"` matches the compact
native selects on `/list`; contacts retain the default appearance.

Document type/status selections remain strings in AuthorizationContext and storage:
`ALL` selects everything, CSV selects multiple values, and an empty string selects
nothing. `utils/multiValueFilter.ts` converts between strings and checkbox values.
Empty selection clears results with a Polish message without a `/website_list`
request; stale responses cannot overwrite it. Shareable URLs use `type`/`status`
(including empty values), and the reader maps `status` to `processing_status` for
`/website_list_neighbors`. Single-value URLs remain supported.

Keep filter state and URL persistence in the owning page. Reuse the shared
component instead of copying the pattern. Inclusion/exclusion filters such
as contact interests can keep local controls: `tylko` selects one included
value and removes it from exclusions. Single-choice controls, independent
boolean toggles, and form fields do not require this pattern.

| Route | Page | Purpose |
|-------|------|---------|
| `/connect` | `connect.tsx` | Backend connection configuration (API type, URL, key) |
| `/` | — | Redirects to `/list` |
| `/list` | `list.tsx` | Browse documents with multi-value type/status/topic filters and text search. Each row shows a `🔗 N` badge (from `/website_list`'s `link_count`/`proposed_link_count`) when the document has `document_links` — amber `· N?` for links still awaiting review; the badge links to the document's editor (or `/read` for `obsidian_note`) where `DocumentLinksPanel` lives. |
| `/search` | `search.tsx` | Stage 9 complete: natural `POST /search`, visible interpretation, editable/removable topic/filter chips, corrected explicit re-search without LLM, feedback, and shareable `mode=explicit&criteria=<JSON>` URLs that replay explicit criteria without Bielik. |
| `/link/:id?` | `link.tsx` | Edit link documents (metadata only) |
| `/webpage/:id?` | `webpage.tsx` | Edit webpages with AI tools (split, clean). The collapsed "🖼️ Ilustracje (N)" panel (`DocumentImagesPanel`, `GET /document/:id/images`) reloads after every save — deleting an `[imgN]` marker from the text drops that image — and offers "📦 Pobierz do MinIO" per image plus "Pobierz wszystkie do MinIO" (`POST /document/:id/images/download`); a stored copy is served via presigned link and badged "📦 storage" |
| `/youtube/:id?` | `youtube.tsx` | Edit YouTube transcripts with per-chapter entity chips; NER skips ad/noise/source chapters; ChapterBoundariesPanel opens by default with all chapter sentences in one request (`with_sentences=1`), with collapse, split, merge (with previous or next chapter), move and chapter-type controls (Treść/Reklama/Szum/Źródła), coloured badges and persistent merge type-conflict warnings; keeps the viewport anchored on the affected sentence; replaces only the raw text textarea when H2 chapters exist. Immediate saves reload Formik before page Save is enabled; headerless/missing transcripts keep the textarea. Bottom buttons: "Zapisz i przejdź do przeglądu NER" (same save + `NEED_MANUAL_REVIEW`, then `/ner/:id/1` — the first chapter, not the whole document) and "Przejdź prosto do chunków" (same save, then `/chunks/:id`) — `handleSaveWebsiteNext(values, "ner" \| "chunks")`, other document types unchanged |
| `/movie/:id?` | `movie.tsx` | Edit movie transcripts |
| `/ner/:id` | `nerChapters.tsx` | Optional `/ner/:id/:chapter` reviews one chapter (0 = preamble), using `position` on both chapter GET endpoints, with full header navigation and previous/next links. Entity edits reload only that chapter; marking noise lazily fetches all chapter entities to preserve shared mentions.  Per-chapter NER review between the editor and `/chunks/:id`: sticky chapter nav, one card per chapter with its sentences (`GET /document/:id/chapter_sections?with_sentences=1`) and the entity mentions highlighted (`utils/entityHighlight.ts`, same matching rules as `entity_service.filter_entities_to_text`), chips from `GET /document/:id/chapter_entities` drawn by `EntitiesPanel`'s `chapterRenderer` mode so every chip keeps the panel's action menus (the dialogs dock to the window bottom in this mode). Filters: entity kind (persons, places, organizations, countries), only chapters with entities, entity search. Countries (`is_country` entities, kept out of the chips) are highlighted in the sentences and listed as a "Państwa" row under the chapter's chips; each chapter has "Scal z poprzednim/następnym" buttons (`POST /document/:id/merge_chapter`, 409 with embeddings or a running analysis) and, for content chapters, "Oznacz jako szum" (`POST /document/:id/chapter_type` → `SZUM`, then `DELETE /website_entities/:id` for every entity that appears in no other content chapter). Edits apply to the whole document; ad/noise/source chapters are shown as skipped. Groups of states from `country_groups` ("państwa bałtyckie", `library/country_group_gazetteer.py`) join the "Państwa" row with their members and are highlighted with a members tooltip. Right click on selected text in a chapter opens `SelectionEntityMenu` (name field + 👤 Osoba / 🏢 Organizacja / 📍 Miejsce / 📅 Wydarzenie / 🛰️ Produkt / system → `POST /document/:id/entities/add_mention`, plus ✏️ Popraw błąd w transkrypcji — a second form ("Poprawna wersja", optional "Tylko dla kanału" scope) that stores a phrase rule (`POST /transcript_corrections`, a 409 duplicate is ignored) and rewrites this document at once (`POST /transcript_corrections/apply`, `dry_run: false`), then reloads the chapters — entities are not rebuilt, re-run NER; both writes accept `user` and `service` keys (PATCH/DELETE of rules stay service-only); the pattern must be a phrase, not one short word — and 📋 Kopiuj for the selected text; without a selection the browser menu stays). Each content chapter has a "🤖 Uzupełnij brakujące opisy" button under its chips (`ChapterDescriptionsPanel`): it lists the organizations and persons without a registry description (`POST /document/:id/chapter/:pos/describe_entities` with `dry_run`), lets the reviewer pick a model (price/limits from `modelOptionText`, external-model warning) and asks for ALL of them in one request; the proposals appear with a checkbox and an editable text each, and only "Zapisz zaznaczone" writes (`PATCH /organizations/:id` / `PATCH /persons/:id`, stops at the first failure) and refreshes the chips. Events (`eventName`, pink highlight, "Wydarzenia" kind filter) and products/systems (`productName`, violet highlight, "Produkty i systemy" kind filter) are drawn by `EntitiesPanel` like every other chip (rows "Wydarzenia" and "Produkty i systemy" inside `renderGroups`) with the same dropdown menu — see "Entity chip menus" below; the page only owns the dialogs those menus open (`onDescribeEvent` → `EventDescriptionDialog`, `onMergeProducts` → the "Scal produkty" form: tick the spellings of one product, name the result, `POST /document/:id/products/merge`). The event menu's "Opis wydarzenia…" or a right click on its mention (no text selected) opens `EventDescriptionDialog`: the LLM drafts a description from the sentences that mention it (`POST /website_entities/:id/describe`), the reviewer edits it, only "Zapisz" stores it (`PUT .../description`); the description is the chip/mark tooltip. A left click on a highlighted person / organization / place / country in the text (no text selected) opens the same action menu a chip has, at the click point (`EntitiesPanel`'s `mentionMenu` prop → floating menu built from the chip menu builders), so the reviewer need not look for the chip in the side column; person, organization and place menus offer "To błąd transkrypcji…" (the mention is a speech-to-text slip of another entity of the document, e.g. person "Hutni" → organization "Huti": `POST /website_entities/:id/transcription_error` folds it into that entity as a surface form, drops the registry link without creating any alias and adds the slip to the channel glossary), person menus also offer "Nadaj prawdziwe nazwisko…" (a nickname such as "Łacha Piachu" → "Icchak Herzog": `POST /website_entities/:id/real_name` finds or creates the registry person, makes the mention its alias and re-points the document link), "To inna osoba z rejestru…" (the registry-search merge, now outside edit mode too), "Otwórz osobę w rejestrze" (`MenuEntry.newTab` — plain link in a new browser tab; `/persons/:id` has an "Edytuj osobę" form: name — old one kept as alias —, description, Wikidata id, aliases via `PATCH /persons/:id`), "Połącz z inną osobą w dokumencie…" (list of the persons of the chapter the menu was opened in — a book has hundreds — with an "cały dokument" switch and a search box, ones sharing a word first; `POST /document/:id/persons/merge`, e.g. "Stone" into "Andy Stone"; a "dołącz" checkbox per row takes further persons along, so several spellings — "Nikuleswsku", "Ninkulesko" → "Luka Nikulesku" — go into one target in a single go: the endpoint merges one pair, so the panel posts them one after another and stops at the first failure) and "Zmień na organizację" (name form, `POST /website_entities/:id/to_organization` with `text`, e.g. "Xie" → "X"). |
| `/world-events` | `worldEvents.tsx` | Index of the events marked in document texts (`GET /entity_events`, URL `q`/`page`/`page_size`, shared pagination): name, description, documents with links to `/ner/:id`. General-knowledge events — NOT the private contact-book events (`/contact-events`, sidebar "Wydarzenia"); the sidebar entry is "Wydarzenia w tekstach". |
| `/products`, `/products/:name` | `products.tsx`, `productDetail.tsx` | Index of products/systems marked in document texts (`GET /entity_products`, URL `q`/`page`/`page_size`, shared pagination) and one page per product (`GET /entity_product?name=`): description shared by all documents (editable, `PUT /entity_product/description` — audited as `entity_described` on every row, replayed after a reopen), spellings found in texts, documents with links to `/webpage/:id` and `/ner/:id`. Reached from the sidebar ("Produkty i systemy") and from the product chip menu ("Otwórz stronę produktu"). |
| `/chunks/:id` | `chunks.tsx` | Review a document's chunk analysis runs (see below) |
| `/read/:id` | `read.tsx` | Chapter-by-chapter reader view (book/article `text_md`, or TEMAT chunk topics as fallback for YouTube/movie transcripts), with per-user progress + notes. Sidebar (map, persons/places, kraj-* countries) has a scope toggle — "rozdział" (default, `GET /document/:id/chapter/:pos/entities`, refetched on chapter change; chip ×N counts are chapter-local) vs "cały dokument" (×N = whole document); a failed chapter fetch falls back to document-level data. Book footnotes extracted to `document_references` render as a collapsible "📚 Przypisy" section at the chapter end — the URL fragment inside a footnote is a clickable link — and ¹⁸ markers in the text become anchors with the footnote as tooltip. Persons/organizations with a stored `person_description`/`organization_description` get an always-on dotted-underline tooltip on every mention in the chapter text itself (`renderMarkdown`'s `described` param, built by `buildEntityDescriptions()` from the sidebar's `shownPersons`/`shownOrganizations` — distinct from `highlightTerms`, the blue chip-click highlight, which only activates on an explicit "podświetl w tekście" click). Book-PDF images (`document_images`, storage_key-sourced; `GET /document/:id/chapter/:pos` `images` field, presigned MinIO URLs) with a `[imgN]` marker in the text render inline as a `<figure>` where the marker sits (`renderMarkdown`'s `IMG_MARKER`); the rest (backfilled books imported before extraction existed, `inline: false`) render in a collapsible "🖼 Ilustracje" section at the chapter end, same pattern as "📚 Przypisy". A `null` `url` (LocalStorage backend, no presigned links) shows the caption alone instead of a broken image box. Inline markdown is a hand-rolled renderer (`renderInline`, exported + unit-tested in `read.renderInline.test.tsx`), not a markdown library: it linkifies a bare `https://` URL, a `[label](https://…)` link and a `(https://…)` parenthesized URL, keeps trailing sentence punctuation outside the link, resolves `[[wikilinks]]` server-side (`chunk_review_routes.py` `_resolve_wiki_links` → `/read/:id`, grey text when unresolved), and re-parses `**bold**`/`*italic*` recursively so a wikilink or URL nested inside them still renders. A `#`-heading always starts its own block even without a blank line on either side — a preprocessing pass in `renderMarkdown` inserts one before any embedded heading line (an Obsidian note commonly runs one straight into the preceding list/paragraph, e.g. "...networking\n### Workloads & Scheduling 15%"), and the heading pattern itself is matched on the block's first line only, with any remaining lines re-rendered as their own block — so neither side swallows the other into (or out of) the `<h_>`. A single `\n` within a paragraph/callout block (no blank line — a blank line already starts a new block) renders as a real line break (`white-space: pre-line`) rather than being flattened to a space — Obsidian's own one-sentence-per-line style otherwise read as a run-on wall of text in the reader; note/entity/timeline exact-quote matching still runs against the un-flattened text (a quote straddling the break falls back to the existing whole-paragraph tint, same as any other whitespace/typography mismatch). A "Stan przetwarzania" checklist (`GET /document/:id/readiness`) renders as a compact ✅/🔧 badge next to the title (tooltip = full step list) plus a collapsible `ReadinessPanel` in the sidebar — steps are content / chunks / embeddings / NER / enrichment / quality / thematic tags (+ an informational Obsidian-note row); missing required steps link to `/chunks/:id` or the type's editor, the panel never runs anything itself. Open by default only when the verdict is `needs_work`; refetched on an in-reader entity edit (`entitiesEditVersion`). Linked Obsidian notes (`Document.obsidian_note_paths` + a chapter's chunk paths) show in a "📝 Notatki Obsidian" sidebar list; when Lenie has reimported that note (`GET /document/:id/obsidian_notes` returns it — the vault folders synced via `OBSIDIAN_SYNC_SUBFOLDERS`) the entry is a preview trigger (opens the right-hand `obsidian-panel` on that note) plus `⤢` (`/read/:id` of the note) and `↗` (Obsidian) icons, otherwise just the `↗` Obsidian link |
| `/persons/:id?` | `persons.tsx` | Person registry (NER stage 4): fuzzy search (`GET /persons?q=`; `?q=` in the URL pre-fills it — unresolved person chips in the reader link here), person details (QID link to wikidata.org, aliases, the long description and external `links` such as Wikipedia, editable via "Edytuj opisy i linki" → `PATCH /persons/:id`; the short `description` is the reader tooltip) and the person's documents (`GET /person_documents`) sorted by `mention_count` (shown as ×N), each with editor + `/read/:id` links and a "rozdziały" drill-down (`GET /document/:id/entity_occurrences?text=` — per-chapter counts linking to `/read/:id?chapter=N`) |
| `/organizations/:id?` | `organizations.tsx` | Organization registry: search, aliases, merge, documents mentioning the organization (each shows its top 3 chapters by mention count as `/read/:id?chapter=N` links, "+N więcej" expands the rest; fetched automatically for the first 30 documents via `GET /document/:id/entity_occurrences`, the "rozdziały" button hides/loads them). Detail also shows the headquarters address, website and linked Obsidian note path (editable; the address is geocoded server-side), a lazy-loaded `CountryMap` with the headquarters plus the geocoded places of the organization's documents, a "Kraje" editor (`GET/POST /organizations/:id/countries`, `DELETE .../countries/:rowId`: relation `siedziba w` / `działa w` / `powiązana z` + country + optional note, with one-click suggestions from the documents' `kraj-*` tags) whose countries tint the map by relation (`CountryTag.relation` / `relation_label`, legend + `title` props on `CountryMap`; default reader behaviour unchanged), and "Powiązane osoby" (`GET /organizations/:id/related`) linking to `/persons/:id` |
| `/places` | `places.tsx` | Global place registry (`GET /places`, paginated, URL `q`/`with_wikipedia`/`page`/`page_size`/`name`): places from all documents grouped by name with document/mention counts, 🌍 for countries, ✓ when geocoded and 📖 when a Wikipedia article is attached. Selecting a place (`?name=`) loads `GET /places/detail` and shows its documents (links to `/read/:id` and `/ner/:id`) plus an editable Wikipedia URL, aliases and note (`PUT /places/profile`). Place chips offer "Dodaj/Zmień stronę Wikipedii" and "Otwórz w rejestrze miejsc" in their menu and show a 📖 link when `wikipedia_url` is set. |
| `/persons-review` | `personsReview.tsx` | manual_review queue (`GET /persons_review`): approve / reject / merge decisions (`PATCH /persons_review/<link_id>`); merge target picked via the `GET /persons?q=` search |
| `/ner-decisions` | `nerDecisions.tsx` | Read-only automatic NER context decisions with URL filters, latest-only mode, summary tiles and shared pagination. EntitiesPanel hides rejected place chips and provides a collapsed rejected-place disclosure with lazily loaded rationales and a document-filtered link. |
| `/ner-corrections` | `nerCorrections.tsx` | Usage statistics of the NER correction dictionary (`GET /ner_corrections/stats`): per-rule applications / distinct documents / last use, unused-rule filter, applications per entity-type change, exclusion-rule counts. Read-only; shows which manual fixes recur and deserve a code fix. |
| `/ner-gazetteer` | `nerGazetteer.tsx` | Database additions to the curated NER gazetteers ([ADR-029](../docs/adr/adr-029-ner-gazetteer-db-backed.md), `GET/POST/PATCH/DELETE /ner_gazetteer`): table of entries (name, stem patterns or geocoder alias, note, link to the source document, author/date) with a `kind` filter in the URL (`?kind=city\|geocode_alias\|place_mention`), an add form (patterns one per line or comma-separated for `city`, query text for `geocode_alias`, optional source document id and note), inline edit and two-click delete (no native dialogs). Writes need a `service` API key — a 403 is explained in Polish; backend validation messages are shown as returned. Entries take effect within the backend's 60 s cache. |
| *(channel badge)* | `components/ChannelBadge.tsx` | "📺 Kanał: <byline>" at the top of `/ner/:id`, `/read/:id`, `/chunks/:id` (not article runs, which already show "Autor") and the YouTube editor; links to that channel's `/ner-glossary`. `/ner/:id` also shows a "Słownik kanału" note (`GET /ner_channel_glossary/applications?document_id=`: the channel's glossary entries and what was repaired at the last entity refresh). `GET /document/:id/chapters` returns `byline` for the reader. |
| `/ner-glossary` | `nerChannelGlossary.tsx` | Per-channel glossary of expected names (`GET/POST/PATCH/DELETE /ner_channel_glossary`): channel (byline) filter in the URL (`?author=`), add form (channel with suggestions, correct name, wrong phrases one per line, approximate-matching switch, note), inline edit of aliases/switch/note, two-click delete. Repairs speech-to-text slips ("Hekset" → Hegseth) in a copy of the transcript before NER; takes effect on the next entity refresh. |
| `/feed-review` | `feedReview.tsx` | Feed curation with `Nowe` and `Do przeczytania / obejrzenia` tabs. The latter uses `saved_for_later`; source filters remain in the URL. Page-level errors (failed load / page change) show as a dismissible banner fixed to the bottom of the viewport, so they are visible wherever the user has scrolled; action errors are also repeated on the clicked card. Topic suggestions are NOT automatic here: each card's `ContentGroupsPanel` has `manualSuggest` and a "🤖 Zaproponuj temat" button that requests one fresh run (`POST /feed_items/:id/group-suggestions` with `force` and the page's model), shows "Szukam kategorii…" while polling, then each proposal separately with its reason, the model name and Akceptuj / Odrzuć (feed items are never auto-applied). The "Model tematów" select above the list (`GET /content_group_suggestion_models`: allowlist with prices/limits, empty = server default, remembered in localStorage `lenie_feedReviewSuggestModel`) picks the model, e.g. a cheap OpenRouter one instead of Bielik. `autoSuggest` still exists on the panel but no page uses it for feeds. A "Do radaru" button (both tabs) opens a small form (tool name prefilled from the title up to the first dash/colon, optional category with hints such as `DecisionModels`) and calls `POST /feed_items/:id/to_radar`: the item becomes a `watchlist` entry in `/tool-recommendations` (or a new mention of an existing one), proposed relations are listed in the confirmation line and the item leaves the queue. The radar cards in turn show "📰 N wzmianek w feedach" (popularity signal), relation chips with confirm/reject and "Dotyczy Twojego stacku". |
| `/tool-candidates-review` | `toolCandidatesReview.tsx` | Review queue for Bielik-detected tool candidates (`GET/POST /tool_candidates*`, Epic 44): grouped by discovery source, sorted by detection date, accept/reject/defer actions refresh via `fetch` (no page reload), inline dismissible banner for the accept-response duplicate warning. |
| `/tools` | `tools.tsx` | Catalog of saved tools (`GET /tools`) with a client-derived category-tag filter. The note is Lenie's own (`personal_notes`): "Dodaj/Edytuj notatkę" saves through `PATCH /tools/:id`; an Obsidian note is optional and shown only as an older copy when `obsidian_note_path` exists (no "missing note" warning any more). Cards also show the detail fields of the Obsidian application template — type, links (homepage / GitHub / Wikipedia / pricing), licence, pricing model, key points, "Ważne polecenia" — plus the GitHub numbers line (`components/GithubStatsLine`, shared with the radar; "Odśwież dane GitHuba" → `POST /tools/github_stats/refresh`). "Edytuj dane" opens an inline form (`PATCH /tools/:id`); "Odchodzę od tego narzędzia" sets `migrating_away` (amber "odchodzę" badge + note) and a header checkbox filters to those. Each card lists the tool's relations from the radar (`relations`, shared `components/ToolRelations/toolRelations.tsx` with ✓/✗ for proposed ones, wording by direction: "emuluje" vs "emulowane przez"). |
| `/topics/:id` | `topics.tsx` | Topic presentation with description and grouped document, contact, event (`contact_group_event`), chat and message links. Explicit edit mode with save/cancel, one-click archive/restore, and a collapsible add-link form. Events link to `/contact-events/:id` with a date or date range. |
| `/project-cards` | `projectCards.tsx` | Project card library (`GET /project_cards`, paginated): filters for the child's age (remembered in localStorage, `age`/`stretch`/`max_difficulty`/`kind`/`series`/`group`/`review_status`/`q`/`page`/`page_size` all in the URL; `kind` = project/experiment/craft/puzzle), "show a year harder" cards marked "do spróbowania z dorosłym" |
| `/recipes`, `/recipes/:id` | `recipes.tsx`, `recipe.tsx` | Recipes imported from cookbooks (`GET /recipes`, `GET /recipes/:id`): search over title and ingredients (diacritic-folded on the server), meal chips with counts, "Z wersją wege" toggle; `q`/`meal`/`wege`/`page`/`page_size` live in the URL. The detail page shows ingredients, method and the book's meal-plan slots and links to `/text/:id` for editing |
| `/project-cards/:id` | `projectCard.tsx` | One card (free-form `sections` render as titled blocks — puzzle/hint sections before the materials, explanations/tips after the steps, `hidden` ones such as puzzle solutions behind a "Pokaż (spoiler)" button; inline SVG illustration rendered via `<img src="data:image/svg+xml…">` so it stays passive, steps, materials, child/adult split, safety) with a review form (age, difficulty, `review_status`, notes via `PATCH /project_cards/:id`) and a print view (`.no-print` hides the form) and an "Oryginał PDF" row: open the original (presigned MinIO link, blob fallback) and upload/replace it (`POST /project_cards/:id/source_pdf`) to compare the import with the source |
| `/upload-file` | `file.tsx` | Upload image files (alpha) |

### Chunk analysis review (`chunks.tsx`)

Reviews `DocumentAnalysisRun` / `DocumentChunk` / `DocumentTopicSection` data (`GET/POST/PATCH /analysis_run*`, `/chunk/*`, `/topic_section/*` in `backend/library/chunk_review_routes.py`) for any document type — see [`backend/database/CLAUDE.md`](../backend/database/CLAUDE.md) for the underlying schema.

- **Run mode selector**: `transcript` (YouTube/movie, rewrite + speaker labeling) vs `article` (webpage/link/text/book chapters, no rewrite — chunks render `original_text` since `corrected_text` is always `NULL` in this mode). For book documents (`GET /document/<id>/chapters`), a chapter can be picked as the analysis scope instead of the whole document.
- **Run workflow status**: `created` → `in_review` → `reviewed`, toggled via "✔ Zamknij review" / "↺ Otwórz ponownie". A run may also be `superseded` ("zastąpiona nowszą" in the run selector) — set by the backend when a new run for the same document+scope replaces an unfinished one.
- **Section view**: runs with more than `SECTION_VIEW_THRESHOLD` (30) `TEMAT` chunks switch to an accordion grouped by `DocumentTopicSection`, lazy-loading each section's chunks on expand (`?section_id=`); smaller/`split_only` runs page the flat chunk list (`?offset=&limit=`, `CHUNK_PAGE_SIZE` = 20).
- **Synteza panel**: collapsible summary of the whole run (`run.synthesis`), collapsed by default.
- **Tagi dokumentu**: thematic + country (`kraj-*`) tag chips from `data.document.thematic_tags`/`data.document.countries`, populated by `document_analysis_service._apply_tags()` at the end of `create_run()`.
- **Embeddings**: 🟢/⚪ indicator per chunk (`has_embeddings`, derived from `document_embeddings.chunk_id`) + "Generuj embeddingi" button (`POST /analysis_run/<id>/generate_embeddings`) — only embeds `TEMAT` chunks with `status=approved`.
- **Obsidian notes**: 📝 indicator with tooltip listing `chunk.obsidian_note_paths`, written by the `/lenie-obsidian-note` skill (`.claude/commands/lenie-obsidian-note.md`), not by this UI. A TEMAT chunk with no note shows an `oznacz: bez notatki` toggle (`PATCH /chunk/<id>` `obsidian_note_not_needed`) — flagged chunks read `🚫📝 bez notatki` and drop out of the "do zrobienia" count on `/list` while still being embedded. A run-level `Pozostałe bez notatki` button (`POST /analysis_run/<id>/mark_notes_not_needed`) flags every remaining note-less TEMAT chunk at once. Both the per-chunk toggle and the run-level button also appear in the post-embedding "✓ Proces zakończony" panel (the summary line there shows `📝 N bez notatki Obsidian` and the toggles live in "Pokaż wynikowe chunki") — the backend endpoints don't gate on run status, so no review re-open is needed. A one-chunk document whose `Document.obsidian_note_paths` is set is counted as noted automatically (backend read-time rule) — `/list` then shows `1 gotowych, 0 do zrobienia` and the green `📝 notatka` badge instead of `📝 częściowo opracowane`.
- **Speakers bar** (transcript runs): lists `run.speakers`; a single speaker renders as "Jedyny mówca:" (monologue). "To monolog (autor)" (`POST /analysis_run/<id>/set_monologue_speaker`, no LLM) sets the document's `byline` author as the sole speaker with role `autor`; "Wykryj rozmówców" runs LLM detection for conversations. New transcript runs without `>>` speaker-change markers get the byline author automatically.
- **Transcript timestamps**: for transcript-mode runs with parsed segments (`doc.text_raw`), `SegmentsView` shows a `[mm:ss]` link per segment group (jump to `youtube.com/watch?v=…&t=`). These are a review/split aid only — **not part of a chunk's text and never embedded**. A "Znaczniki czasu [mm:ss]" checkbox above the chunk list (state `showTimestamps`, default on; the explanatory note sits next to it) hides/shows that overlay; the ▶ speaker-change marker stays visible regardless.

### Entity chip menus

All NER chips are rendered by `EntityChips` and take their actions from a `MenuEntry` dropdown built in
`EntitiesPanel` (`menuActions`); the first entry, "Kopiuj nazwę", is added by `EntityChips` itself. **No page draws
its own chip row with inline buttons** (the rule is also in [AGENTS.md](AGENTS.md)). The product and event chips were
once the exception — a row of their own on `/ner/:id` with only `×` — which is why they lacked the type changes the
other chips had; they now use the same menus. Actions that need a page-owned form go through a callback prop
(`onShowInText`, `onDescribeEvent`, `onMergeProducts`).

| Chip | Highlight in text | Change type to | Delete | Type-specific entries |
|---|---|---|---|---|
| Person | yes | place, organization, product, event | "× Usuń encję", "🚫 To nie jest osoba" | real name, another registry person, merge within document, topic relevance, transcription slip |
| Organization / cited source | yes | place, person, product, event | "× Usuń encję", "🚫 Usuń i nie wykrywaj więcej" | rename (global), description / source data, merge, split, transcription slip |
| Place | yes | organization, person, product, event | "× Usuń encję", "🚫 Usuń i nie wykrywaj więcej" | rename (geocodes), merge, split, Wikipedia, place registry, topic relevance, transcription slip |
| Product / system | yes | person, organization, place, event | "× Usuń encję" | "Scal z innymi zapisami…" |
| Event | yes | person, organization, place, product | "× Usuń encję" | "Dodaj opis wydarzenia…" / "Opis wydarzenia…" |
| Country | — | — | — | none: a read-only row derived from places and `kraj-*` tags |

Retype endpoints: person/organization/place → product or event `POST /website_entities/:id/to_product` (`entity_type`
`productName` default / `eventName`); product/event → anything `POST /website_entities/:id/from_product`; the older
`to_place`, `to_organization`, `to_person` (organization **or place** → person) are unchanged. A retype to product or
event keeps counts and spellings; an event's approved description is not carried over. The tests in
`entitiesPanel.test.tsx` assert the exact menu lists — change the matrix and the tests together.

## Architecture

### Provider Hierarchy

```
AuthorizationProvider (init from localStorage) → BrowserRouter → App → RequireAuth → Layout → Page
```

### Connection Flow

1. User opens app → `RequireAuth` checks for API key in context (loaded from localStorage)
2. No key → redirect to `/connect`
3. User enters API type, URL, API key → validates via `GET /website_list?type=link&limit=1`
4. On success → saves to localStorage, sets context, redirects to `/list`
5. On page refresh → `AuthorizationProvider` loads config from localStorage

### Global State (`authorizationContext.tsx`)

- **API config** (persisted to localStorage): `apiUrl`, `apiKey`, `apiType` (always "Docker" since 2026-07-04)
- *(Infrastructure status state removed 2026-07-02 — the RDS/OpenVPN/SQS widgets went away along with the AWS resources they monitored)*
- **Document filters**: `selectedDocumentType`, `selectedDocumentState`, `searchInDocument`, `searchType`

### localStorage Keys

| Key | Value |
|-----|-------|
| `lenie_apiType` | "Docker" (stale "AWS Serverless" values are ignored on load) |
| `lenie_apiUrl` | API URL (single URL for both app and infra endpoints) |
| `lenie_apiKey` | API authentication key |

### Custom Hooks

| Hook | Purpose | Key API Endpoints |
|------|---------|-------------------|
| `useManageLLM` | Document CRUD, AI processing (clean) | `/website_get` (response includes `embeddings_count` + `approved_chunks_count` shown in the editor stats line), `/website_save`, `/website_delete`, `/website_download_text_content`, `/website_text_remove_not_needed` |
| `useList` | Fetch document list with filters | `/website_list` |
| `useSearch` | Natural + corrected explicit search, interpretation and feedback state | `POST /search`; `POST /search/<id>/feedback`. Corrections search first, then persist `partially_correct` + full `corrected_query` only after successful search. |
| `useFileSubmit` | Image upload | Separate AWS endpoint |

`EntitiesPanel` displays document `countries` (`{slug, name_pl}`) from GET `/website_entities` unless the reader supplies its own list. Its "Wykryj państwa" button calls POST `/document/<id>/countries/detect`, updates the country chips and reports how many countries were added.

The `EntitiesPanel` component (rendered inside `InputsForAllExceptLink`, so it appears on webpage/youtube/movie/email editors) calls `GET /website_entities?id=` on load and `POST /website_entities` ("Wykryj osoby i miejsca" button, 150s timeout — the first NER call after a service restart loads the spaCy model; the POST also runs stage-3 place verification) — data comes from the `document_entities` table, see [`docs/ner-integration-plan.md`](../docs/ner-integration-plan.md). An "Edytuj" toggle adds per-chip actions: **×** delete entity (`DELETE /website_entities/<id>`; for persons also removes the `document_persons` link), **↷** "this is another person" (registry search via `GET /persons?q=` → `PATCH /document_persons/<link_id>` merge, works on any confidence), **+** add alias (`POST /persons/<person_id>/aliases` — e.g. a podcast nickname, resolves as alias_matched next time), **🚫** exclude (`POST /ner_exclusions` global or author-scoped + entity delete — suppresses the phrase in future NER runs; rules are listed and removable at the bottom of `/persons-review`), and for `orgName` chips **ℹ️** add/edit a short description (`PATCH /organizations/<id>` — the global registry's `Organization.description`; one-off LLM backfill: `backend/imports/organization_descriptions_backfill.py`). The optional `onShowInText(item, kind)` prop adds "🔎 Podświetl w tekście" to every chip menu (`/ner/:id` marks that entity's mentions strongly in all chapters, whatever the kind filters say, scrolls to the first one and shows a "wyczyść" bar). Organization chips also offer "Zmień na miejsce" (`POST /website_entities/<id>/to_place`, editable name) and "Zmień na osobę" (`POST /website_entities/<id>/to_person`). Person chips open a menu with "Zmień na miejsce" (`POST /website_entities/<id>/to_place`, editable place name), "× Usuń encję" and "🚫 To nie jest osoba" (the exclusion form with the reason `not_a_person` preselected: `POST /ner_exclusions` global or author-scoped + entity delete — the way to drop a transcription slip such as "Egekwo" for "ex aequo"). Place chips also open an action menu without enabling edit mode: "Podziel na: …" / "Podziel na kilka miejsc…" (`POST /website_entities/<id>/split_place`; the item's `split_suggestion` pre-fills the parts when the mention is only a list of countries), "Popraw nazwę" (inline name correction via `PATCH /website_entities/<id>`), merge into another place when available, delete with a reason, or exclude from future detection. Person and place chip menus also hold one "Związek z tematem: <current>" entry that expands in place into a submenu (`MenuEntry.children`; Główny temat / Pośrednio / Przenośnie, `PATCH /website_entities/<id>/relevance`; ✓ marks the current level). Long menus reposition themselves — upwards when there is more room above, scrollable, right-aligned near the screen edge; the chip colour shows it (amber = related, grey dashed = figurative), and figurative places drop off the map and the `miejsce-*` tags. Corrections retain surface variants and use `source=manual`, protected from NER refresh and place enrichment. Stale geocoding and orphaned place tags are cleared, then the corrected entity is geocoded through the cache (including the country-stripping retry), without an LLM classifier or canonical renaming. Geocoder failures do not block the correction. The panel reports geocoder confirmation and offers a merge hint when another place has the same geocode or canonical name, or when a 409 response identifies a name collision; the other entry survives the merge. Chips of organizations and cited sources ("Organizacje", "Źródła cytowane") open a similar menu: a link to the registry (`/information-sources?id=` or `/organizations/:id`), "Popraw nazwę" (global rename via `PATCH /organizations/<id>` — also renames the document entities and the bound source, merging a same-named duplicate; a 409 because the name belongs to another organization opens the merge comparison for that organization instead of an error), for a cited source "Dane źródła (typ, strona, opis)" (`PATCH /information_sources/<id>`; the website may be pasted as a URL, founding year and the like go into the description), for another organization "Opis organizacji", the global merge, "Podziel na kilka organizacji…" (`POST /website_entities/<id>/split_organization`; a two-word name such as "NATO Moskwa" pre-fills "Podziel na: NATO, Moskwa", never applied automatically; shares the split form with places via `splitKind`), delete and exclude. A cited source's chip tooltip reads "typ · domena · opis". Every organization merge (a taken name on rename, or "Połącz z inną organizacją") goes through `organizationMergePreview.tsx`: a side-by-side table (name, type, description, aliases, documents, information source) plus a "Co się stanie" list from `GET /organizations/<id>/merge_preview`, and only "Połącz" executes `POST /document/<id>/organizations/merge`; "Anuluj" changes nothing. The optional `menuActions` prop leaves reader chip behavior unchanged; a `MenuEntry` with `to` renders a router link. The optional `refreshKey` prop forces a reset and refetch for the same document: `webpage.tsx` bumps it after `POST /document/<id>/reopen_editing`, which deletes the document's entities server-side, so the panel shows an empty state instead of stale chips. A 404 on rename also reloads the list. Under "Miejsca" a read-only "Tagi miejsc: …" line lists the document's `miejsce-*` tags (`place_tags` in `GET /website_entities`). "Pełna weryfikacja encji zakończona." is shown only for a verification job the panel watched run in this session, never for a leftover finished job found on load. The exported `EntityChips` component is reused by `read.tsx` for the reader's persons/places sidebar (resolved persons link to `/persons/:id`). Unverified chips dim their content but never the action menu. Geocoder-verified places render as green chips with ✓ (tooltip: `display_name`), unverified ones dimmed; places with `place_verification_status='rejected'` are not rendered as chips at all (neither here nor in the reader) and appear only in the collapsed "Odrzucone miejsca (N)" disclosure; historical states (`item.historical`, e.g. Jugosławia, ZSRR) render as amber chips with 🕰️ and a tooltip with the years of existence and successors. Stage-4 resolved persons render as blue chips — ✓ for `wikidata_matched`/`alias_matched`, "?" for `manual_review` (tooltip: canonical name | description | QID | confidence). Organization chips with a saved `organization_description` show it as both the chip tooltip and an ℹ️ marker — set globally, so it appears on every document mentioning that organization, not just the one it was added from. `CountryMap` additionally accepts `places` (verified places with `lat`/`lon`, orange point markers) and `pipelines` (Overpass/OSM routes from `item.pipeline.geojson`, dashed polylines — dark red for oil, orange for gas, with an OSM-attribution tooltip); `read.tsx` derives both from entity items (`GET /website_entities` or the chapter-scoped endpoint). Pipeline entities render a 🛢️ marker in their chips. Copy-name is the first entry of the chip action menu for persons, places, organizations, and cited sources (the menu appears whenever `menuActions` is passed; the reader sidebar passes none).

## Backend API Communication

- **HTTP client**: axios
- **Auth header**: `x-api-key: {apiKey}` on all requests
- **Content-Type**: `application/x-www-form-urlencoded`
- **API type**: Docker (Flask backend, localhost:5000 or NAS) — the only mode. The "AWS Serverless" option was removed from the connect screen 2026-07-02 and purged entirely 2026-07-04 (`ApiType` union, `DEFAULT_API_URLS`, storage fallback, `authorizationContext` default, `useSearch` AWS branch, app2 default URL): its document-serving Lambdas (`app-server-db`/`app-server-internet`) were decommissioned, leaving only `/url_add` in the AWS API (used by the Chrome extension, not this frontend). Restoration: [docs/aws-serverless-restoration.md](../docs/aws-serverless-restoration.md).

### Default URLs

| API Type | API URL |
|----------|---------|
| Docker | `http://localhost:5000` |
| ~~AWS Serverless~~ (removed from UI) | `https://api.dev.lenie-ai.eu` |

App endpoints use the base URL (e.g., `/website_list`). (The `/infra` prefix and `useSqs` hook were removed 2026-07-02 along with the AWS infra API.)

## TypeScript

All source files are TypeScript (`.ts`/`.tsx`). Strict mode enabled (`tsconfig.json`: `strict: true`).

### Shared Types (`@lenie/shared`)

Domain types are defined in `shared/` (project root) and imported via `@lenie/shared` alias:
- `ApiType` — union type for API backend mode
- `Document` — document form fields interface
- `emptyDocument` — factory constant
- `DEFAULT_API_URLS` — default backend URLs per API type
- `SearchResult`, `ListItem` — API response types

The alias is configured in both `tsconfig.json` (`paths`) and `vite.config.ts` (`resolve.alias`). The local `src/types/index.ts` re-exports shared types and adds app-specific `AuthorizationState`.

See `docs/shared-types.md` for full details.

## Running

**Installing dependencies.** `package-lock.json` is deliberately not committed (`Dockerfile` runs `npm install`), and `.npmrc` sets `shamefully-hoist=true`, a pnpm-only option that npm ignores with a warning. With **npm 10.9.x** `npm install` can crash in arborist with `TypeError: Cannot read properties of null (reading 'edgesOut')` (`#loadPeerSet`, triggered by vitest's optional `@vitest/*`/`jsdom` peers) — it fails even in an empty directory and leaves a half-installed `node_modules` (symptom: vitest dies with `Cannot find module '@asamuzakjp/css-color'`, no `.bin`). Use a newer npm without touching the global one: `npx --yes npm@11 install --no-audit --no-fund`. Worktrees share the main checkout's `node_modules` through a link, so repair it there once. vitest 4 declares Node `^20 || ^22 || >=24` (a Node 23 only prints an `EBADENGINE` warning; the suite passes).

## AWS Deployment

**Hosting deleted 2026-07-02** — the `app.dev.lenie-ai.eu` S3+CloudFront stacks were removed (the frontend required the decommissioned AWS document API; it now runs only against Docker/NAS). `./deploy.sh` will fail until the stacks are restored — see [docs/aws-serverless-restoration.md](../docs/aws-serverless-restoration.md). Original flow (kept for restoration): the script resolves S3 bucket and CloudFront distribution ID from SSM Parameter Store.

```bash
./deploy.sh                      # Full build + deploy to S3 + CF invalidation
./deploy.sh --skip-build         # Deploy existing build/ only
./deploy.sh --skip-invalidation  # Skip CF cache invalidation
```

SSM parameters used:
- `/${PROJECT_CODE}/${ENVIRONMENT}/s3/app-web/name` — S3 bucket name
- `/${PROJECT_CODE}/${ENVIRONMENT}/cloudfront/app/id` — CloudFront distribution ID

Environment variables: `PROJECT_CODE` (default: `lenie`), `ENVIRONMENT` (default: `dev`), `AWS_REGION` (default: `us-east-1`).

## Docker Build

```
Stage 1: node:24 → npm ci && npm run build (build context is repo root; copies shared/ + web_interface_react/)
Stage 2: nginx:alpine → serve build/ on port 80
Config: nginx.conf with SPA routing (all paths → index.html)
```

Note: The Dockerfile expects the build context to be the repository root (set in `infra/docker/compose.yaml`). It copies `shared/` into `../shared/` relative to the app workdir so Vite can resolve `@lenie/shared`.

## i18n

`react-i18next` and `i18next` are installed as dependencies but not yet configured. UI strings are currently hardcoded in Polish.

# Frontend (React) — CLAUDE.md

React 18 single-page application for managing documents and running AI operations (text correction, embedding, similarity search). Built with **Vite** and **TypeScript**.

**App version**: 0.3.15.5 | **Package version**: 0.3.15.5

## Directory Structure

```
web_interface_react/
├── public/                             # Static assets (favicon, icons, manifest)
├── src/
│   ├── main.tsx                        # Entry point (AuthorizationProvider + Router)
│   ├── App.tsx                         # Route definitions (React Router v6) + RequireAuth guard
│   ├── App.test.tsx                    # Vitest smoke tests
│   ├── utils.tsx                       # Utility components
│   ├── vite-env.d.ts                   # Vite + CSS module type declarations
│   ├── types/
│   │   └── index.ts                    # Re-exports from @lenie/shared + app-specific AuthorizationState
│   ├── modules/shared/
│   │   ├── context/
│   │   │   └── authorizationContext.tsx # Global state: API config (from localStorage), DB/VPN status, filters
│   │   ├── services/
│   │   │   └── storage.ts              # localStorage persistence for connection config
│   │   ├── hooks/
│   │   │   ├── useManageLLM.ts         # Core document CRUD + AI operations
│   │   │   ├── useList.ts              # Document list fetching
│   │   │   ├── useSearch.ts            # Vector similarity search
│   │   │   └── useFileSubmit.ts        # Image file upload
│   │   ├── components/
│   │   │   ├── Layout/                 # Sidebar navigation + content area
│   │   │   ├── Authorization/          # DB/VPN status panel, connection indicator, disconnect
│   │   │   ├── Input/                  # Reusable text/textarea input
│   │   │   ├── Select/                 # Reusable select dropdown
│   │   │   ├── SharedInputs/           # Common document form fields
│   │   │   ├── EntitiesPanel/          # NER persons/places chips + refresh button (GET/POST /website_entities)
│   │   │   ├── TagsInput/              # Chip editor over the CSV tags field (suggestions from GET /tags)
│   │   │   └── FormButtons/            # Save/delete action buttons
│   │   ├── pages/
│   │   │   ├── connect.tsx             # Connection configuration (/connect)
│   │   │   ├── list.tsx                # Document list with type/state filtering
│   │   │   ├── search.tsx              # Vector similarity search
│   │   │   ├── link.tsx                # Link document editing
│   │   │   ├── webpage.tsx             # Webpage editing + AI processing
│   │   │   ├── youtube.tsx             # YouTube transcript editing
│   │   │   ├── movie.tsx               # Movie transcript editing
│   │   │   ├── chunks.tsx              # Chunk analysis review (/chunks/:id)
│   │   │   ├── read.tsx                # Reader view (/read/:id)
│   │   │   ├── persons.tsx             # Person registry search + person → documents (/persons/:id?)
│   │   │   ├── personsReview.tsx       # manual_review person queue (/persons-review)
│   │   │   └── file.tsx                # File upload (alpha)
│   │   ├── constants/
│   │   │   └── variables.ts            # App version
│   │   └── styles/
│   │       └── index.css               # Global styles (buttons, loader, errors)
├── index.html                          # Root HTML (Vite entry point)
├── vite.config.ts                      # Vite + Vitest configuration
├── tsconfig.json                       # TypeScript strict configuration
├── Dockerfile                          # Multi-stage: Vite build + nginx
├── nginx.conf                          # SPA routing + cache headers
├── package.json                        # Dependencies & scripts
├── .prettierrc                         # Code formatting
├── .stylelintrc                        # CSS linting
└── .gitignore
```

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

### Multi-value filters

When a user can select several values from one category — especially when the
list can grow — use a compact, expandable multi-select filter rather than a
permanent row of checkboxes. The trigger must say either `Wszystkie
[kategorie]` or show the count of selected values. The menu provides
`Zaznacz wszystkie`, `Odznacz wszystkie`, and `Odwróć wybór` actions.

The expandable menu must close when the user clicks outside it. Use a ref on
the native `<details>` element and a `pointerdown` listener on `document`;
when the event target is outside an open menu, set its `.open` property to
`false`. This keeps clicks on its checkboxes and action buttons intact while
making the filter behave like a standard dropdown.

If the domain has a meaningful empty value, include it as a separate choice,
for example `(bez tematów)`. Preserve the complete filter state in the URL so
the filtered view can be shared. This pattern is for multi-value filters, not
for every small single-choice control: a native select, radios, or a few
standalone toggles can remain clearer.

When this pattern is needed in more than one view, extract a shared component
instead of copying its markup and state handling.

| Route | Page | Purpose |
|-------|------|---------|
| `/connect` | `connect.tsx` | Backend connection configuration (API type, URL, key) |
| `/` | — | Redirects to `/list` |
| `/list` | `list.tsx` | Browse documents with type/state/text filters |
| `/search` | `search.tsx` | Stage 9 complete: natural `POST /search`, visible interpretation, editable/removable topic/filter chips, corrected explicit re-search without LLM, feedback, and shareable `mode=explicit&criteria=<JSON>` URLs that replay explicit criteria without Bielik. |
| `/link/:id?` | `link.tsx` | Edit link documents (metadata only) |
| `/webpage/:id?` | `webpage.tsx` | Edit webpages with AI tools (split, clean) |
| `/youtube/:id?` | `youtube.tsx` | Edit YouTube transcripts |
| `/movie/:id?` | `movie.tsx` | Edit movie transcripts |
| `/chunks/:id` | `chunks.tsx` | Review a document's chunk analysis runs (see below) |
| `/read/:id` | `read.tsx` | Chapter-by-chapter reader view (book/article `text_md`, or TEMAT chunk topics as fallback for YouTube/movie transcripts), with per-user progress + notes. Sidebar (map, persons/places, kraj-* countries) has a scope toggle — "rozdział" (default, `GET /document/:id/chapter/:pos/entities`, refetched on chapter change; chip ×N counts are chapter-local) vs "cały dokument" (×N = whole document); a failed chapter fetch falls back to document-level data. Book footnotes extracted to `document_references` render as a collapsible "📚 Przypisy" section at the chapter end — the URL fragment inside a footnote is a clickable link — and ¹⁸ markers in the text become anchors with the footnote as tooltip. Persons/organizations with a stored `person_description`/`organization_description` get an always-on dotted-underline tooltip on every mention in the chapter text itself (`renderMarkdown`'s `described` param, built by `buildEntityDescriptions()` from the sidebar's `shownPersons`/`shownOrganizations` — distinct from `highlightTerms`, the blue chip-click highlight, which only activates on an explicit "podświetl w tekście" click). Book-PDF images (`document_images`, storage_key-sourced; `GET /document/:id/chapter/:pos` `images` field, presigned MinIO URLs) with a `[imgN]` marker in the text render inline as a `<figure>` where the marker sits (`renderMarkdown`'s `IMG_MARKER`); the rest (backfilled books imported before extraction existed, `inline: false`) render in a collapsible "🖼 Ilustracje" section at the chapter end, same pattern as "📚 Przypisy". A `null` `url` (LocalStorage backend, no presigned links) shows the caption alone instead of a broken image box. Inline markdown is a hand-rolled renderer (`renderInline`, exported + unit-tested in `read.renderInline.test.tsx`), not a markdown library: it linkifies a bare `https://` URL, a `[label](https://…)` link and a `(https://…)` parenthesized URL, keeps trailing sentence punctuation outside the link, resolves `[[wikilinks]]` server-side (`chunk_review_routes.py` `_resolve_wiki_links` → `/read/:id`, grey text when unresolved), and re-parses `**bold**`/`*italic*` recursively so a wikilink or URL nested inside them still renders. A `#`-heading is matched on the block's first line only (an Obsidian note often drops the blank line between a heading and its body — the follow-on lines are re-rendered as their own block, not swallowed into the `<h_>`). A single `\n` within a paragraph/callout block (no blank line — a blank line already starts a new block) renders as a real line break (`white-space: pre-line`) rather than being flattened to a space — Obsidian's own one-sentence-per-line style otherwise read as a run-on wall of text in the reader; note/entity/timeline exact-quote matching still runs against the un-flattened text (a quote straddling the break falls back to the existing whole-paragraph tint, same as any other whitespace/typography mismatch). A "Stan przetwarzania" checklist (`GET /document/:id/readiness`) renders as a compact ✅/🔧 badge next to the title (tooltip = full step list) plus a collapsible `ReadinessPanel` in the sidebar — steps are content / chunks / embeddings / NER / enrichment / quality / thematic tags (+ an informational Obsidian-note row); missing required steps link to `/chunks/:id` or the type's editor, the panel never runs anything itself. Open by default only when the verdict is `needs_work`; refetched on an in-reader entity edit (`entitiesEditVersion`). Linked Obsidian notes (`Document.obsidian_note_paths` + a chapter's chunk paths) show in a "📝 Notatki Obsidian" sidebar list; when Lenie has reimported that note (`GET /document/:id/obsidian_notes` returns it — the two pilot vault folders) the entry is a preview trigger (opens the right-hand `obsidian-panel` on that note) plus `⤢` (`/read/:id` of the note) and `↗` (Obsidian) icons, otherwise just the `↗` Obsidian link |
| `/persons/:id?` | `persons.tsx` | Person registry (NER stage 4): fuzzy search (`GET /persons?q=`; `?q=` in the URL pre-fills it — unresolved person chips in the reader link here), person details (QID link to wikidata.org, aliases) and the person's documents (`GET /person_documents`) sorted by `mention_count` (shown as ×N), each with editor + `/read/:id` links and a "rozdziały" drill-down (`GET /document/:id/entity_occurrences?text=` — per-chapter counts linking to `/read/:id?chapter=N`) |
| `/persons-review` | `personsReview.tsx` | manual_review queue (`GET /persons_review`): approve / reject / merge decisions (`PATCH /persons_review/<link_id>`); merge target picked via the `GET /persons?q=` search |
| `/feed-review` | `feedReview.tsx` | Feed curation with `Nowe` and `Do przeczytania / obejrzenia` tabs. The latter uses `saved_for_later`; source filters remain in the URL. |
| `/tool-candidates-review` | `toolCandidatesReview.tsx` | Review queue for Bielik-detected tool candidates (`GET/POST /tool_candidates*`, Epic 44): grouped by discovery source, sorted by detection date, accept/reject/defer actions refresh via `fetch` (no page reload), inline dismissible banner for the accept-response duplicate warning. |
| `/tools` | `tools.tsx` | Read-only catalog of saved tools (`GET /tools`), with a client-derived category-tag filter and Obsidian-note status. |
| `/upload-file` | `file.tsx` | Upload image files (alpha) |

### Chunk analysis review (`chunks.tsx`)

Reviews `DocumentAnalysisRun` / `DocumentChunk` / `DocumentTopicSection` data (`GET/POST/PATCH /analysis_run*`, `/chunk/*`, `/topic_section/*` in `backend/library/chunk_review_routes.py`) for any document type — see [`backend/database/CLAUDE.md`](../backend/database/CLAUDE.md) for the underlying schema.

- **Run mode selector**: `transcript` (YouTube/movie, rewrite + speaker labeling) vs `article` (webpage/link/text/book chapters, no rewrite — chunks render `original_text` since `corrected_text` is always `NULL` in this mode). For book documents (`GET /document/<id>/chapters`), a chapter can be picked as the analysis scope instead of the whole document.
- **Run workflow status**: `created` → `in_review` → `reviewed`, toggled via "✔ Zamknij review" / "↺ Otwórz ponownie". A run may also be `superseded` ("zastąpiona nowszą" in the run selector) — set by the backend when a new run for the same document+scope replaces an unfinished one.
- **Section view**: runs with more than `SECTION_VIEW_THRESHOLD` (30) `TEMAT` chunks switch to an accordion grouped by `DocumentTopicSection`, lazy-loading each section's chunks on expand (`?section_id=`); smaller/`split_only` runs page the flat chunk list (`?offset=&limit=`, `CHUNK_PAGE_SIZE` = 20).
- **Synteza panel**: collapsible summary of the whole run (`run.synthesis`), collapsed by default.
- **Tagi dokumentu**: thematic + country (`kraj-*`) tag chips from `data.document.thematic_tags`/`data.document.countries`, populated by `document_analysis_service._apply_tags()` at the end of `create_run()`.
- **Embeddings**: 🟢/⚪ indicator per chunk (`has_embeddings`, derived from `document_embeddings.chunk_id`) + "Generuj embeddingi" button (`POST /analysis_run/<id>/generate_embeddings`) — only embeds `TEMAT` chunks with `status=approved`.
- **Obsidian notes**: 📝 indicator with tooltip listing `chunk.obsidian_note_paths`, written by the `/lenie-obsidian-note` skill (`.claude/commands/lenie-obsidian-note.md`), not by this UI. A TEMAT chunk with no note shows an `oznacz: bez notatki` toggle (`PATCH /chunk/<id>` `obsidian_note_not_needed`) — flagged chunks read `🚫📝 bez notatki` and drop out of the "do zrobienia" count on `/list` while still being embedded. A run-level `Pozostałe bez notatki` button (`POST /analysis_run/<id>/mark_notes_not_needed`) flags every remaining note-less TEMAT chunk at once. A one-chunk document whose `Document.obsidian_note_paths` is set is counted as noted automatically (backend read-time rule) — `/list` then shows `1 gotowych, 0 do zrobienia` and the green `📝 notatka` badge instead of `📝 częściowo opracowane`.
- **Transcript timestamps**: for transcript-mode runs with parsed segments (`doc.text_raw`), `SegmentsView` shows a `[mm:ss]` link per segment group (jump to `youtube.com/watch?v=…&t=`). These are a review/split aid only — **not part of a chunk's text and never embedded**. A "Znaczniki czasu [mm:ss]" checkbox above the chunk list (state `showTimestamps`, default on; the explanatory note sits next to it) hides/shows that overlay; the ▶ speaker-change marker stays visible regardless.

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

The `EntitiesPanel` component (rendered inside `InputsForAllExceptLink`, so it appears on webpage/youtube/movie/email editors) calls `GET /website_entities?id=` on load and `POST /website_entities` ("Wykryj osoby i miejsca" button, 150s timeout — the first NER call after a service restart loads the spaCy model; the POST also runs stage-3 place verification) — data comes from the `document_entities` table, see [`docs/ner-integration-plan.md`](../docs/ner-integration-plan.md). An "Edytuj" toggle adds per-chip actions: **×** delete entity (`DELETE /website_entities/<id>`; for persons also removes the `document_persons` link), **↷** "this is another person" (registry search via `GET /persons?q=` → `PATCH /document_persons/<link_id>` merge, works on any confidence), **+** add alias (`POST /persons/<person_id>/aliases` — e.g. a podcast nickname, resolves as alias_matched next time), **🚫** exclude (`POST /ner_exclusions` global or author-scoped + entity delete — suppresses the phrase in future NER runs; rules are listed and removable at the bottom of `/persons-review`), and for `orgName` chips **ℹ️** add/edit a short description (`PATCH /organizations/<id>` — the global registry's `Organization.description`; one-off LLM backfill: `backend/imports/organization_descriptions_backfill.py`). The exported `EntityChips` component is reused by `read.tsx` for the reader's persons/places sidebar (resolved persons link to `/persons/:id`). Geocoder-verified places render as green chips with ✓ (tooltip: `display_name`), rejected ones dimmed. Stage-4 resolved persons render as blue chips — ✓ for `wikidata_matched`/`alias_matched`, "?" for `manual_review` (tooltip: canonical name | description | QID | confidence). Organization chips with a saved `organization_description` show it as both the chip tooltip and an ℹ️ marker — set globally, so it appears on every document mentioning that organization, not just the one it was added from. `CountryMap` additionally accepts `places` (verified places with `lat`/`lon`, orange point markers) and `pipelines` (Overpass/OSM routes from `item.pipeline.geojson`, dashed polylines — dark red for oil, orange for gas, with an OSM-attribution tooltip); `read.tsx` derives both from entity items (`GET /website_entities` or the chapter-scoped endpoint). Pipeline entities render a 🛢️ marker in their chips.

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

## Dependencies

| Library | Version | Purpose |
|---------|---------|---------|
| react | ^18.3.1 | UI framework |
| react-router-dom | ^6.30.3 | Client-side routing |
| axios | ^1.13.5 | HTTP client |
| formik | ^2.4.9 | Form state management |
| react-i18next | ^15.7.4 | i18n support (installed, not yet configured) |
| i18next | ^23.16.8 | i18n core |
| vite | ^6.0.7 | Build toolchain |
| typescript | ^5.7.3 | Type checking |
| vitest | ^2.1.8 | Test framework |

## Running

```bash
npm run dev       # Dev server (port 3000)
npm run build     # TypeScript check + Vite production build (output: build/)
npm run preview   # Preview production build
npm test          # Run Vitest tests
npm run lint      # TypeScript type check only
```

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

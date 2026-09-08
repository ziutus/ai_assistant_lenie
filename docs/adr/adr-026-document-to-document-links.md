# ADR-026: Typed, directed links between two library documents

**Date:** 2026-09-08
**Status:** Accepted — implemented in the same change
**Decision makers:** Ziutus

## Context

Two documents in the library can be about exactly the same thing from
different angles — e.g. a GitHub repository (`document_type='link'`) and the
LinkedIn post that announces and discusses it (`document_type='social_media_post'`,
its text carrying the repo URL verbatim). Nothing in the data model expressed
that pair:

- **`collections`** (`Document.collection_id`, 1:N) — a document sits in at
  most one broad thematic collection; wrong granularity and no direction.
- **`content_groups` / Tematy** (M:N) — topic buckets, not tight pairs; a
  group per pair would bloat the shared group list.
- **`document_source_relationships`** + `GET /document/<id>/relationship_graph`
  — provenance of claims *inside* one article, keyed by entity *name*
  (`subject_name`/`object_name` are strings), never by another `Document`.
- **`cited_publications`** — academic papers only (DOI/PMID/PMCID).
- **`Document.note`** — free text, not navigable.

## Decision

Add a `document_links` table: one typed, directed edge per
`(from_document_id, to_document_id, relation)`.

- **Relation vocabulary** lives in code
  (`library/document_links_service.RELATIONS`), not a lookup table — it is a
  small controlled set, each entry carrying a Polish phrase for the `from`
  side and one for the `to` side so the reader renders the edge from either
  endpoint (`discusses` → "Omawia" / "Omawiane w"). Initial set: `references`,
  `discusses`, `summarizes`, `updates`, `translates`, `responds_to`,
  `related`, `duplicates` (the last two symmetric).
- **`status`** mirrors `document_source_relationships`: a human-created link
  is `confirmed`; an auto-detected one is `proposed` and needs a one-click
  accept. `rejected` edges are kept so the detector does not re-propose them.
- **Auto-detection** (`detect_url_mention_links()`): scan a document's text
  for URLs — including bare `host/path` mentions common in social posts —
  that normalize to another document's `url` / `canonical_url`, and propose a
  `references` edge. Exposed as `POST /document/<id>/links/detect` and the
  `imports/detect_document_links.py` backfill; **not** wired into the
  ingestion pipeline as automatic mutation (same restraint as the rest of the
  provenance work — proposals only, humans confirm).
- **Surfacing**: `GET/POST /document/<id>/links`, `PATCH/DELETE
  /document_links/<id>`; a "Powiązane dokumenty" panel on the link / webpage /
  social-post editors and the reader sidebar; confirmed edges also join
  `GET /document/<id>/relationship_graph` as `document:<id>` nodes.

## Consequences

- One more domain primitive next to collections, Tematy and provenance. It is
  deliberately the narrowest of the four: an explicit pair, not a bucket.
- The detector's matching is URL-equality only; "same story, no shared link"
  still needs a manual `related`/`duplicates` edge (an LLM cluster suggestion
  is possible later, out of scope here).
- `relationship_graph` now mixes entity-provenance edges and
  document-to-document edges; the frontend graph view distinguishes them by
  node `type` (`document` vs `organization`/`information_source`/...).

# ADR-033: Native geopolitics model — source-backed events and versioned, directed country relations

**Date:** 2026-11-01
**Status:** Accepted (MVP implemented)
**Decision makers:** Ziutus

## Context

The author keeps geopolitical knowledge in Obsidian country notes (today only a Freedom House section per
country) and wants a world map of how states influence each other: "Brazil elected a president, the
opponent fled to the USA — mark Brazil as unfriendly to the USA". The author is leaving Obsidian for
geopolitics within about a year, and relations will be added **continuously, as consequences of world
events** read in documents, not in a separate curation pass. So the model lives in Lenie from the start;
there is no Obsidian intermediate step.

Requirements that shaped the model:

- relations are **directed** (A's stance toward B is not B's toward A) and **change over time** (a state moves
  between spheres of influence);
- one label per state cannot express a state like Turkey (allied in defence, independent in politics, trading
  with the rival) or Israel (heavy dependence, low obedience) — a relation is per pair **and per axis**;
- an event is not an assessment: a politician fleeing abroad is evidence, not proof of hostility;
- the map must be reproducible for a past date, so confirmed history is never rewritten.

## Options

1. **A bloc/zone attribute on the country.** Simple, but cannot express independence, time or direction.
2. **Pure event sourcing:** the relation is computed from weighted events. Elegant, but facts do not determine a
   relation unambiguously, and re-weighting would repaint the historical map.
3. **Source-backed events plus a separate, versioned, human-confirmed assessment history (chosen).** Events
   *propose* an assessment; only `confirmed` assessments are drawn. Aggregation can later *suggest*, never
   decide.

## Decision

Tables (migration `d7e1a4b9c205`, models in `library/db/models.py`):

| Table | Role |
|---|---|
| `countries` | frozen seed of the gazetteer (197 entities) with real FKs; `iso3` is NULL for Kosovo, `map_code` keys the GeoJSON; `entity_kind` marks disputed entities (Kosovo, Taiwan, Palestine, Western Sahara) |
| `geo_events` / `geo_event_participants` / `geo_event_sources` | a dated event, the countries involved (actor/target/affected/location) and the document passages that report it (`document_id` is `RESTRICT`, quote + hash) |
| `country_relation_assessments` | `from → to`, `axis`, `score` −2..+2, `confidence`, `[valid_from, valid_to)`, `review_due_at`, `status` proposed/confirmed/rejected, `supersedes_id`, optimistic `version` |
| `country_relation_evidence` | which events back which assessment |

Rules:

- `document_events` is **input only**: its refresh deletes and recreates rows, so it cannot be the canonical
  event. A `geo_event` may cite many documents; a repeated report adds a source instead of a second event,
  and a rejected event is never revived.
- An exclusion constraint (`btree_gist`, `daterange(valid_from, valid_to, '[)')`, `WHERE status='confirmed'`)
  forbids overlapping confirmed periods for one (from, to, axis). Confirming a new assessment closes the
  previous open period in the same transaction (`valid_to = new.valid_from`) under `SELECT … FOR UPDATE`;
  the constraint is the concurrency backstop. A change dated before an already confirmed period starts is
  refused (409) rather than splitting history — see "Not in the MVP".
- Axes: `political` and `security`, both −2..+2, with the meaning of each step written in
  `geopolitics_service.AXES` and shown in the UI. "Strength of influence" is a different quantity and is
  deliberately not folded into these axes yet.
- **No event decides a relation alone.** An assessment backed by fewer than two *independent documents* has its
  confidence capped at 0.7 (`SINGLE_EVENT_CONFIDENCE_CAP`); several events from one article are still one source.
  Repeated proposals for the same pair, axis, start and score are merged into one proposal with more evidence
  (`propose_assessment`) instead of a queue of identical cards. No data is not neutrality: the map shows grey, and an empty result says
  so. A confirmed assessment past `review_due_at` (default 6 months) is flagged as needing review, never
  silently changed.
- "Zones of influence" are a **view**, not an attribute; independence of a state shows up as different scores
  on different axes toward different states.

Where it runs: on demand, from the "Zaproponuj relacje geopolityczne" button of the entities panel (editors and
reader). The input is the text NER reads (no advertisement/noise/source chapters of a transcript); the countries offered to
the model are found after the channel glossary is applied. A background job queued after `create_run()` (the
`entity_enrichment` pattern), gated by country tags, is the planned next step; running it inside `create_run()` is
rejected because it would lengthen an already long request without a retry.

Flow (`library/geopolitics_detect.py`, `POST /document/<id>/geopolitics/detect`): the model gets the text in
fragments (≤ 4 × 10 000 characters) and the slugs of the countries found in it. It may answer "nothing". Every
candidate is validated: the quote must occur verbatim in the document, the date must parse (a relative date such as
"obecnie" that the model could not resolve against the document's publication/ingestion date is dated to that
date, month precision, with a note in the description, instead of being dropped), countries must
exist, a relation is kept only if both countries are participants of the same event. Everything is stored as
`proposed`; the reader approves "event + change" in one click (`POST /geopolitics/proposals/<id>/decision`,
`expected_version` → 409 on a stale view) or rejects it. Usage is logged by `ai_ask()` as
`geopolitics_event_extraction`.

The analysis prompt is a versioned `prompt_templates` task (`geopolitics_events`), editable at `/prompt-templates`
without a deploy; every event and proposal stores the label of the prompt version that produced it.

Surface: `library/geopolitics_service.py`, `geopolitics_detect.py`, `geopolitics_routes.py`; the `/geopolitics`
page in `web_interface_react` (map, proposal queue, events, document analysis) on the existing Leaflet stack.

## Not in the MVP

Influence instruments (X, Facebook, TikTok, Starlink, currency, arms, energy) and their use as a separate
`influence_*` family — they must not inherit a state's actions from the company's seat; a *possible* lever, a
*documented use* and an *observed effect* are three different records. Further axes (economic, information),
a 0–4 influence-strength scale, aggregation with time decay as a *suggestion*, splitting a confirmed period for
back-dated corrections, derived "sphere" views, `organization_countries` → `countries` FK, backfill over
existing documents, a background job instead of the synchronous detect call.

## Consequences

- Positive: history is reproducible; the model's hypotheses are visible and reviewable; one table family
  answers "what did we believe on date D, and why".
- Negative: confirmation is manual work (by design); the exclusion constraint needs the `btree_gist`
  extension; the synchronous detect call holds a request for up to a few minutes on a long document.
- The author must keep the meaning of the scale stable; changing it later invalidates old scores.

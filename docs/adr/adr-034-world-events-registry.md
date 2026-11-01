# ADR-034: Canonical registry of world events — identity, mentions and source links

**Date:** 2026-11-01
**Status:** Accepted (part 1 implemented)
**Decision makers:** Ziutus

## Context

Three things in Lenie were called "events" and shared no data:

1. `document_entities` rows of type `eventName` — a **mention**: a named event ("Galanbard 2026", "szczyt NATO w
   Hadze") marked by hand in one document. Rebuilt on every NER refresh, grouped only by the casefolded text,
   shown on `/world-events`.
2. `document_events` — a **dated statement** an LLM extracted from one document. Its extraction deletes and
   recreates the rows, so it cannot be the permanent record.
3. `geo_events` ([ADR-033](adr-033-geopolitics-events-and-country-relations.md)) — a canonical event with several
   cited documents, but one that required a date and at least one country.

The reader needs one place for events that recur across many documents ("wybory w Izraelu", US midterms, Polish
parliamentary and presidential elections: announced, campaigned, voted, counted), under different names, and
that are **not necessarily between countries**: the CrowdStrike outage, a Bitcoin halving, a model launch,
the WHO declaring a pandemic (an organization, not a state), Log4Shell.

## Options

1. **A new `events` table, migrate and replace `geo_events`.** Cleaner name, but every ADR-033 foreign key
   (participants, sources, evidence) must be re-pointed, with no domain gain.
2. **Extend `geo_events` (chosen).** IDs and foreign keys stay; the physical rename to `events` can be a separate,
   coordinated step if the name keeps misleading.
3. **Keep three mechanisms and link them by name.** A name is not an identity ("Wybory w Polsce" is the 2023 and
   the 2027 election).

## Decision

`geo_events` becomes the registry of world events (migration `c7e2b5a9d814`).

- **Nothing about an event is mandatory but its title.** `event_date` is nullable (`date_precision='unknown'`,
  enforced both ways by a CHECK), a range has `event_date_end` + `end_date_precision`, and `is_ongoing` says
  "started, not ended" — an unknown end is not a point event. `kind` and the participant `role` are
  dictionaries (`geo_event_kinds`, `geo_event_roles`), not CHECKs, so a new kind or `host`/`winner` needs a row,
  not a migration (a test keeps the code constants and the seed in step).
- **Participants have real foreign keys**, one table per kind: `geo_event_participants` (countries, unchanged),
  `geo_event_organizations`, `geo_event_persons`. A polymorphic `(type, id)` pair would not give referential
  integrity. A company's seat does not make its country a participant. A person cannot be a `location`.
- **Identity is the event `id`, never the name or the date.** `geo_event_aliases` lists every name
  (`name_key`: NFC, collapsed spaces, casefold; accents kept — and `search_key`, folded, with a trigram index).
  An alias is unique **within** an event and may belong to several: "Wybory w Polsce" names both elections.
  Renaming keeps the old title as an alias. `dedup_key` stays the identity of a *report* (same title, date and
  participants — countries-only dated events keep the ADR-033 formula) and is now UNIQUE; a lost race is resolved
  inside a savepoint to the winner instead of failing the request.
- **A name only suggests.** Mentions are linked by `geo_event_mention_links`, keyed by `(document, name_key)`
  because the `document_entities` row is rebuilt: `confirmed` links an event, `rejected` is remembered so the
  suggestion is not repeated. Suggestions come from an exact alias, then (PostgreSQL) trigram similarity.
  Nothing is linked automatically, also not when only one event carries the alias — the 2027 election may simply
  not exist yet. Linking a name teaches the event that spelling as an alias.
- **`document_events` is input, not the record.** A timeline entry is promoted to a new event or attached to an
  existing one as a source; `geo_event_sources.document_event_id` is `ON DELETE SET NULL` and the quote is stored
  independently, so a re-extraction cannot orphan it. A vague date ("decade", "era") becomes an undated event with
  the original wording in the description, never an invented date.
- **Events and assessments stay apart** (the ADR-033 rule). A `direct` piece of evidence must name **both**
  countries of the assessment — enforced in the shared service (`create_assessment`, `propose_assessment`,
  including a context → direct promotion), not only in the extractor. A `context` piece (an election in one of the
  countries, an outage) is background: it needs a written rationale, is shown as such, and does not count toward
  the independent-source confidence cap. `country_relation_evidence.event_id` is now `RESTRICT`: deleting an event
  must not silently remove the grounds of a confirmed assessment, and a country a confirmed assessment's direct
  evidence relies on cannot be removed from the event.
- **Surfaces.** `/world-events` is the registry ("Zdarzenia") plus the queue of unlinked names ("Do powiązania z
  tekstów"); `/geopolitics?tab=events` lists only events with a country. Edits carry `expected_version`.

## Phasing

1. **Done:** the above — optional date and participants, aliases, kinds, organizations/persons as manually
   assigned participants, persistent mention links, manual create/link/promote, canonical `/world-events`.
2. The LLM task `world_events/event_extraction` (today the analysis prompt requires country slugs and discards a
   candidate without participants), the match queue "same event as #N?" with scores and reasons, a catalogue of
   organizations/persons offered to the model.
3. Merging two events (transaction, ordered locks, redirect of the old id, audit) and an immutable snapshot of the
   evidence seen at the moment an assessment is confirmed; event families (a parent with stages: announcement,
   vote, results). Families and snapshots are deliberately postponed until there is a case that needs them.
4. Optional physical rename `geo_events` → `events`.

## Consequences

- Positive: one place for recurring, multi-document and country-less events; a name no longer decides identity;
  past decisions about mentions survive NER refreshes and `reopen_editing`.
- Negative: the table name says "geo" for a general registry until step 4; the reader must confirm links (by
  design); the trigram search exists only on PostgreSQL, so SQLite tests cover the alias path only. Behaviour that
  SQLite cannot check (UNIQUE race, trigram, `FOR UPDATE ... OF`, foreign keys) was verified against PostgreSQL in
  rolled-back transactions when the migration was written.
- A mention rebuilt by NER keeps its link only while its normalized name stays the same; renaming a mention in the
  text creates a new, unlinked name (and a new suggestion).

# ADR-029: Database-backed additions to the curated NER gazetteers

**Date:** 2026-10-17
**Status:** Accepted
**Decision makers:** Ziutus

## Context

Several NER corrections are plain additions to a closed, hand-curated list that lives in code:

| List | File | Entry |
|---|---|---|
| Foreign cities (stem patterns) | `backend/library/city_gazetteer.py` `_CITY_DATA` | `("Luizjana", ("luizjan*", "luisian*"))` |
| English/OSM geocoder aliases | `backend/library/geocode_aliases.py` `GEOCODE_ALIASES` | `"Kaliningrad": "Królewiec"` |

On 2026-10-17 three fixes for document #10872 were made; two were exactly such one-line
additions ("Riadzie" → "Rijad", E028; "Luisianie" → "Luizjana", E031). Each cost a branch,
review, CI, an image rebuild and a NAS deploy — for data, not logic. The repository already has
the opposite precedent: cleanup rules moved to a table with REST ([ADR-027](adr-027-cleanup-rules-db-backed.md)),
as did `ner_exclusions` and `ner_corrections`. `ner_corrections` cannot replace a gazetteer
entry, because it matches one exact lemma, while a gazetteer entry matches a whole inflection
family (`luizjan*`).

## Options

1. **Keep lists in code.** Every entry is reviewed in a PR and covered by a test quoting the
   source sentence. Cost: the full deploy cycle per entry.
2. **JSON file read at runtime.** Fewer rebuilds, but the file still lives in the image or a
   volume; no audit, no REST, no UI.
3. **Table `ner_gazetteer_entries` extending the code lists (chosen).** Entries are added with
   `POST /ner_gazetteer`, without a deploy.

## Decision

Option 3, phase 1 — only `kind='city'` and `kind='geocode_alias'`:

- The lists in code stay the **seed** and are never removed or overridden by a row; a row only
  adds patterns to an existing name or adds a new name. No data migration.
- `library/ner_gazetteer_store.py` reads rows through a short own session with a 60 s cache
  (REST writes bust it). **NER never fails because of the database:** any DB error, including
  the `SystemExit` of `config_loader.require()`, yields an empty list, i.e. the seed alone.
- `city_gazetteer` recompiles its patterns when the store refreshes; `geocode_aliases` checks the
  seed first, then rows. `canonical_city_name` keeps its contract (full match, at most 4 suffix
  characters per stem token, a result only when exactly one name matches).
- Writes are validated (`validate_entry`): known `kind`; for `city` 1–8 patterns of
  `[a-z0-9 *-]` after `unidecode`, `*` only at the end of a token, a stem of at least 3
  characters (so `a*` and `*` cannot match everything), and compilation through the same
  `compile_variant` the seed uses; for `geocode_alias` a non-empty alias.
- REST `GET/POST/PATCH/DELETE /ner_gazetteer` (`library/ner_gazetteer_routes.py`); writes need a
  `kind=service` key (as `cleanup_rules`); duplicates by `(kind, lower(name_pl))` answer 409.
  Each row records `created_by`, `created_at`, optional `source_document_id` and `note`.

Algorithmic rules (for example splitting `A na B` organization spans, or `non_place_demonym`
logic) stay in code: they are logic, not lists.

## Consequences

- A new city form or geocoder alias no longer needs a PR or deploy; the next NER run (within the
  cache TTL) uses it. The case-log entry (`docs/ner-entity-diagnose-case-log.md`) is still
  written for every diagnosed case.
- **Risks and mitigations.**
  - *Closed-list discipline* used to be enforced by code review; it is now enforced by
    validation and the audit columns. Keep entries tied to a confirmed document
    (`source_document_id`).
  - *Regression tests quoting the source sentence* cannot be attached to a row; the case-log entry
    is the record, and a representative case may still be added to the unit tests.
  - *Entries are not in git.* Back them up with the database; `GET /ner_gazetteer` is the export.
  - *Purity of `aggregate_entities_detailed`*: the store is consulted only through the gazetteer
    modules, with a cache and a failure fallback; unit tests keep the store empty by default
    (`tests/unit/conftest.py`).
- **Not in phase 1:** a UI page, and the other lists (`geo_feature_gazetteer`, `region_gazetteer`,
  `geopolitical_region_gazetteer`, `historical_state_gazetteer`, `non_place_demonym_patterns`).
  The store is keyed by `kind`, so each can adopt it with a small change.

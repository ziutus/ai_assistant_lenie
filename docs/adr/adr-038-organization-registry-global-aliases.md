# ADR-038: Global Organization Registry with Exact-Match Aliases

**Date:** 2026-07-23
**Status:** Accepted (implemented in PR #362; this ADR was written 2026-11-20 to replace `organization-ner-alias-plan.md`)
**Decision Makers:** Ziutus
**Current behaviour:** [backend/library/CLAUDE.md](../../backend/library/CLAUDE.md) (organization registry paragraph)

### Context

NER returned the same organization under several spellings as separate records:
in document 9267 `Interia` (variants `Interii`, `Interią`) and `Interii` were two
canonical `orgName` groups. A one-off manual merge had to hold globally — in the
current document, in already-saved documents and in future NER runs — without
poisoning the registry with NER noise (for example `Korea` tagged as `orgName`).

### Decision

1. **A global registry** — `organizations`, `organization_aliases`,
   `document_organizations` — analogous to the person registry
   ([ADR-037](adr-037-person-registry-dedicated-tables.md)) but deliberately
   simpler: **exact-match resolution only** (normalized alias, then canonical
   name). No Wikidata, no LLM disambiguation, no fuzzy auto-merge. A merge made
   once by a human must never silently reverse itself.
2. **Alias uniqueness is global**: `UNIQUE(normalized_alias)` plus `409` on
   conflict. This is a conscious departure from `PersonAlias` and
   `InformationSourceAlias`, which are unique only per owner, because the
   requirement is "linked once, linked everywhere".
3. **Normalization:** `normalize_ner_text()`, whitespace unification, `casefold()`,
   Polish diacritics kept.
4. **No automatic global aliases from raw NER output.** Observed variants are
   recorded (`alias_kind="ner_observed"`) only after the group matched an
   existing organization, and stay auditable and removable.
5. **`document_organizations` is a pure link** (document, organization,
   `document_entity_id`, `confidence`); mention counts and variants live only in
   `DocumentEntity`, as for persons. `reopen_document_for_editing()` deletes
   these links but never the global registry rows.
6. **Organization ≠ information source.** `organizations` is the single place
   that resolves a name/alias; `information_sources` carries a nullable, unique
   `organization_id` FK (one direction), and `entity_service` resolves an `orgName`
   group once and hands the id to `refresh_ner_cited_sources`. Two drifting alias
   registries were rejected. NATO is an organization, not necessarily a source.
7. **Manual merge ("Połącz z…")** runs in one transaction: global alias, merge of
   `DocumentEntity` and `DocumentOrganization`, summed counts/variants, audit row.
   Audit reuses `entity_review_decisions` with the new decision
   `organization_merged` (people use `corrected`; that is unchanged). Removing an
   alias stops future use of the rule and keeps the audit history.

### Rationale

- The failure was an aggregation bug: NER already passed `Interii` as a variant of
  `Interia` yet also created a second canonical record.
- Exact matching is the only mode that makes a manual decision durable and
  predictable; fuzzy or LLM merges would reintroduce the same duplicates.

### Consequences

- **Positive:** one decision fixes every document, past and future.
- **Positive:** organization names resolved in one registry for NER chips and
  cited-source tracking.
- **Negative:** inflected forms not yet seen need an alias (manual or observed);
  there is no fuzzy catch-all.
- **Negative:** `canonical_name` is intentionally not unique, so two different
  organizations with one display name are distinguished only by manual curation.
- **Deferred:** LLM disambiguation, Wikidata/OpenCorporates, fuzzy auto-merge,
  automatic organization↔`InformationSource` matching, historical versions of
  `document_entities`.

### Related Artifacts

- `backend/library/organization_registry.py`, `backend/library/entity_service.py`,
  `backend/library/information_provenance.py`, `/organizations` routes in
  `backend/server.py`, UI `web_interface_react/src/modules/shared/pages/organizations.tsx`
- Migration `e23a1b2c3d4e_create_organizations`, `backend/imports/backfill_organizations.py`
- Later additions to the same model (countries of an organization, ambiguous
  aliases for context-dependent abbreviations) are described in
  [backend/library/CLAUDE.md](../../backend/library/CLAUDE.md)

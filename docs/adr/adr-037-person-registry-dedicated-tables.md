# ADR-037: Person Recognition — Dedicated Tables, Wikidata + LLM Disambiguation

**Date:** 2026-07-10
**Status:** Accepted (implemented; this ADR was written 2026-11-20 to replace `person-ner-plan.md`)
**Decision Makers:** Ziutus
**Implementation:** [ner-integration-plan.md](../ner-integration-plan.md) (stage 4)

### Context

Documents carried no structure for a *person*: "all articles about Jan Kowalski"
was only possible as `LIKE '%kowalski%'` on article text, which cannot tell two
people with the same surname apart, misses spelling variants (inflection,
initials) and does not scale to analytical queries. Countries work as `kraj-*`
tags because they are a closed, unambiguous list (a *classification* problem).
For people the problem is *entity identification* — which exact person — which
is not a deterministic yes/no fact like "does this place exist in OSM"
([ADR-018](adr-018-geo-place-ner-locationiq.md)).

### Decision

1. **Dedicated relational tables, not an `osoba-*` tag namespace:** `persons`
   (canonical name, optional `wikidata_qid`, `description` as disambiguation
   context), `person_aliases` (spelling variants), `document_persons`
   (document↔person M:N with `raw_mention` and `confidence`). `pg_trgm` GIN
   indexes on canonical names and aliases. `tags` stays thematic/country tagging.
2. **Pipeline: NER → disambiguation → LLM.** spaCy `persName` yields candidates
   (same model as places). Per mention, a cascade in `library/person_registry.py`:
   exact alias/canonical match (no network) → Wikidata (`library/wikidata_client.py`,
   **humans only, P31=Q5**) with the LLM picking a QID from a closed candidate list
   by description (it may answer NONE) → `pg_trgm` fuzzy match against the registry
   → new person without a QID.
3. **Never auto-merge on low confidence.** Fuzzy and new-person results get
   `confidence=manual_review` and go to a human queue. `confidence` has four
   values: `wikidata_matched`, `alias_matched`, `manual_review`, `manual_confirmed`.
4. **Junk guard:** a single-word mention with no Wikidata human match is skipped
   (spaCy `persName` noise such as product names).

### Rationale

| | `osoba-*` tags | Dedicated tables |
|---|---|---|
| Two people with one surname | No — same slug | Yes — separate rows, told apart by `description`/QID |
| Aliases / spelling variants | No | Yes — `person_aliases` |
| "All articles about X" | Poor — text scan of `tags` | Indexed JOIN |
| Fuzzy surname search | No | Yes — `pg_trgm` |

Tags would have been enough for a thematic UI filter, but the goal — searching
by person — needs a foreign key to an entity.

### Consequences

- **Positive:** correct per-person aggregation and `GET /person_documents`.
- **Positive:** the LLM only confirms among closed candidates, it does not
  generate identities.
- **Negative:** three tables, an ORM module and a manual review queue to maintain
  (`/persons-review`).
- **Negative:** depends on the public Wikidata API for the first-pass match.

### Related Artifacts

- `backend/library/person_registry.py`, `backend/library/wikidata_client.py`
- Tables `persons`, `person_aliases`, `document_persons` — see
  [backend/database/CLAUDE.md](../../backend/database/CLAUDE.md)

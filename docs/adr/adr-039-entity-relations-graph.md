# ADR-039: Global entity relations with human decisions

Status: accepted for implementation; migration not applied by this task.

## Decision

Store person–person, person–organization, person–country, organization–organization and
organization–country relations in PostgreSQL, with a closed vocabulary shared by extraction
and validation. No graph database is needed: the reader requires only bounded joins.

LLM (`relations-pl-v3`) and Wikidata produce proposals. Each relation keeps idempotent evidence
(passages or source URLs), and a human confirms or rejects it. Proposals never change a human
decision or overwrite confirmed titles/periods. Symmetric endpoints have a canonical order;
disjoint dated terms are separate records. Missing period bounds are open.

Confirmation projects country relations into the existing `organization_countries` and
`person_territories` truth tables. Only a projection created by this service is owned and
removable by rejection/deletion. Existing truth is preserved. Ownership transfers when another
confirmed term still needs that row. The legacy person table allows only one row per country
and relation; the full separate terms remain in `entity_relations`, which takes precedence in
API/graph output. A transferred owned projection uses the surviving term's dates.

Merges move both endpoints and evidence, prefer confirmed over proposed over rejected, and
drop self-relations. Non-rejected relations prevent automatic orphan deletion. Re-pointing a
single person mention transfers global relations only when the source has no other document
mentions; otherwise its identity remains separate.

The graph reuses existing nodes and provenance, adds only connected persons and expands
person → organization → country, with direct family ties and relation periods. Proposed edges
are explicitly marked. Legacy country ties without a counterpart remain visible and read-only.

## Extraction boundaries

Only uniquely resolved registry entities may be linked. No persons or organizations are created
from model output. Unresolved Wikidata targets include QIDs and labels. Wikidata reads complete
before any writes, so network failure cannot leave partial proposals. The LLM reads at most ten
6000-character fragments using context-preserving bounded parallel calls; each failed model call
is reported. Confirmed/rejected context is filtered per fragment and requires fresh textual evidence.

The model picker uses household `relation_extraction_model`, preferring the seeded OpenRouter
Gemma 4 31B identifier while available, otherwise the first available model. Provider availability
and prices use the existing model registry; no live catalog or production data was consulted
while implementing this task.

## Validation

Offline SQLite tests cover identity, periods, evidence, projection ownership, merge/orphan rules,
registry resolution, fake LLM/Wikidata, HTTP contracts and graph chains. PostgreSQL migration
execution and live provider behaviour require separate deployment validation; neither is performed
in this worktree task.

# ADR-021: Bielik-generated search terms separate from thematic tags

**Date:** 2026-08-11
**Status:** Accepted
**Decision Makers:** Ziutus

### Context

Hybrid search combines literal matching with embedding similarity. A relevant
document can still be difficult to find when the user remembers its purpose
rather than its title or wording. Document 9381 is an email about OpenNDA; the
query “sprawdzenie NDA” reached it only through the semantic leg because the
literal word “sprawdzenie” is absent from the document. It ranked behind
incidental lexical matches from longer documents.

The existing `documents.tags` field is a controlled thematic taxonomy used by
classification and filters. Adding arbitrary user-language aliases to it would
mix two different meanings and make the taxonomy unreliable.

### Decision

Add nullable `documents.search_terms` (migration `ff6a7b8c9d0e`) as a separate,
comma-separated set of 3–6 short retrieval phrases.

- After a full document analysis, Bielik generates terms only when the field is
  empty. The prompt asks for concepts, synonyms and a phrase expressing user
  intent; it does not invent facts.
- A non-empty value is considered reviewed/manual and is never overwritten by
  automatic analysis.
- `POST /document/<id>/search_terms/generate` supports generating terms for an
  existing document. The email editor exposes this operation and the field
  remains manually editable through normal document saving.
- The lexical search expression and its Python scoring text include
  `search_terms` alongside title, thematic tags, note and body text.
- `search_terms` do not affect embeddings, semantic-vector storage or the
  structured search filters.

### Rationale

- The field gives high-value lexical aliases for likely future wording without
  requiring the user to remember product names.
- Separating aliases from `tags` preserves the controlled vocabulary needed by
  thematic and geographic workflows.
- Generation after analysis uses concise, already reviewed context and avoids a
  new LLM call for split-only runs.
- Manual editing provides a correction path for imperfect LLM phrasing.

### Consequences

- **Positive:** Queries such as “analiza umowy o poufności” can recall a
  document titled primarily by a product name.
- **Positive:** Existing and historical documents can be enriched on demand.
- **Negative:** Terms are not a complete synonym dictionary and add one cheap
  Bielik call to a full analysis when the field is empty.
- **Negative:** PostgreSQL `ILIKE` still does not stem Polish inflections;
  `sprawdzenie` and `sprawdzania` are distinct literal forms.
- **Deferred:** Rebalance hybrid ranking so strong semantic results are not
  overtaken by incidental lexical matches; consider Polish stemming separately.

### Related Artifacts

- [search-hybrid.md](../search-hybrid.md#frazy-wyszukiwawcze-search_terms)
- [search-rebuild-progress.md](../search-rebuild-progress.md)
- [ADR-020](adr-020-search-indexing-deferred.md)
- `backend/library/search_terms.py`
- `backend/library/document_repository.py`
- `backend/library/search_service.py`

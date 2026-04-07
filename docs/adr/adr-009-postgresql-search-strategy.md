# ADR-009: PostgreSQL Search Strategy — `unaccent` + `pg_trgm` for Structured Fields, Embeddings for Content

**Date:** 2026-03-10
**Status:** Accepted
**Decision Makers:** Ziutus

### Context

Project Lenie is evolving toward a personal CRM capability — linking contacts from Google Contacts with notes and documents in the database and Obsidian. The key use case: *"I met person X, we talked about Y — I want to find this quickly before the next meeting."*

This requires effective search across two dimensions:

1. **Structured fields** — names (`Michał Śliwiński` vs `Michal Sliwinski`), cities (`Łódź` vs `Lodz`, `w Warszawie` vs `Warszawa`), and other metadata with Polish diacritics and variant spellings.
2. **Content/notes** — free-text notes and document content where semantic understanding matters (e.g., finding notes about "Warsaw" when the text says "warszawski meetup").

Four PostgreSQL search mechanisms were evaluated:

| Mechanism | Strengths | Weaknesses for this use case |
|-----------|-----------|------------------------------|
| `simple` dictionary | Trivial setup, lowercase normalization | No diacritic handling, no fuzzy matching |
| `unaccent` extension | Normalizes diacritics (`ł→l`, `ą→a`, `ź→z`) | Exact match only, no fuzzy/typo tolerance |
| `pg_trgm` extension | Fuzzy matching via trigram similarity, handles typos and partial matches | Doesn't understand semantics |
| Hunspell `pl_PL` | Polish stemming for common words | Poor with proper nouns (names, small towns not in dictionary), complex setup, high maintenance |
| pgvector embeddings | Semantic understanding, handles inflection naturally | Already implemented; overkill for exact name lookups |

### Decision

Adopt a **three-layer search strategy**:

1. **`unaccent` extension** — for diacritic-insensitive matching on structured fields (names, cities, authors). Solves the primary problem of `Michał` vs `Michal`, `Łódź` vs `Lodz`.

2. **`pg_trgm` extension** — for fuzzy/approximate matching on structured fields. Handles typos (`karboviak` → `Karbowiak`), partial matches, and Polish case inflection at the trigram level (`Warszawa` ↔ `Warszawie` share 5/7 trigrams, similarity ~0.6).

3. **pgvector embeddings** (existing) — for semantic content search in notes and documents. Already handles Polish inflection, synonyms, and meaning-based retrieval naturally.

**Rejected alternative:** Hunspell/Ispell Polish stemmer. While it handles inflection for common Polish words well, it fails for proper nouns — names like `Karbowiaka` (genitive) and small towns like `Pcim Dolny` or `Huta Dłutowska` are not in the dictionary. The setup and maintenance cost (dictionary files, custom text search configuration) is not justified given that embeddings already solve the content search problem and `pg_trgm` provides sufficient fuzzy matching for names.

### Implementation

Add to database init scripts:

```sql
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

Example usage patterns:

```sql
-- Diacritic-insensitive name search
SELECT * FROM contacts
WHERE unaccent(lower(name)) LIKE '%' || unaccent(lower('Michal')) || '%';

-- Fuzzy city matching (handles typos and partial inflection)
SELECT * FROM contacts
WHERE similarity(unaccent(lower(address_1_city)), unaccent(lower('Łódź'))) > 0.3;

-- Semantic content search (existing pgvector mechanism)
SELECT * FROM websites_embeddings
WHERE embedding <=> query_embedding < 0.3;
```

### Consequences

- **Positive:** Covers all search scenarios — exact names, fuzzy names, diacritics, semantic content — with minimal new infrastructure.
- **Positive:** `unaccent` and `pg_trgm` are built-in PostgreSQL extensions — no external dependencies or dictionary files to manage.
- **Positive:** Both extensions are lightweight and have negligible impact on database performance.
- **Positive:** Works with existing PostgreSQL 16/18 deployments (both Docker and AWS RDS support these extensions).
- **Negative:** `pg_trgm` similarity threshold (0.3) may need tuning per use case — too low gives false positives, too high misses valid matches.
- **Negative:** Neither `unaccent` nor `pg_trgm` solves full Polish inflection (e.g., `Pcim Dolny` → `w Pcimiu Dolnym`) — but embeddings handle this for content search.

### Related Artifacts

- `backend/database/init/02-create-extension.sql` — extension installation (to be updated)
- `backend/database/init/03-create-table.sql` — `web_documents` table
- `backend/database/init/04-create-table.sql` — `websites_embeddings` table (pgvector)
- `backend/tmp/sql_data/lenie_aws-2026_01_23_05_00_40-dump.sql` — AWS dump showing `unaccent` and `polish` text search config already present
- [ADR-001](adr-001-native-language-embeddings.md) — native-language embeddings decision

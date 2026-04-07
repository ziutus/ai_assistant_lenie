# ADR-004: Raw psycopg2 Instead of ORM

**Date:** 2025 (initial development)
**Status:** Superseded by ADR-004a

### Context

The project needed PostgreSQL access with pgvector extension support for vector similarity search.

### Decision

Use raw `psycopg2` queries instead of an ORM (SQLAlchemy, Django ORM). Custom domain model classes (`StalkerWebDocument`, `StalkerWebDocumentDB`) handle persistence directly.

### Consequences

- **Positive:** Full control over queries, especially pgvector-specific operations (cosine similarity search with IVFFlat index).
- **Positive:** Simpler dependency tree, no ORM abstraction overhead.
- **Negative:** Manual SQL query construction, no migration framework, schema changes require manual DDL scripts.

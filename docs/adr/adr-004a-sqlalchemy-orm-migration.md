# ADR-004a: Migrate to SQLAlchemy ORM + Pydantic Schemas

**Date:** 2026-03
**Status:** Accepted (supersedes ADR-004)

### Context

The raw psycopg2 approach (ADR-004) proved increasingly painful as the schema grew. Adding a single column required manual changes in 5+ places: SELECT column list, INSERT statement, UPDATE columns, `dict()` serialization, `__clean_values()`, and the domain model constructor. This violated DRY and was error-prone.

Additionally, the project needs:
- **OpenAPI schema generation** for automatic TypeScript type generation ([B-50](#b-50-api-type-synchronization-pipeline-pydantic--openapi--typescript))
- **Structured AI outputs** — Pydantic models as response format for LLM calls (OpenAI, Bedrock, Vertex AI)
- **Schema migration management** — currently using raw DDL scripts with no versioning

### Decision

Adopt a two-layer architecture:

1. **SQLAlchemy 2.x ORM** — database access layer. Declarative models define the schema once; SQLAlchemy generates all SQL (SELECT, INSERT, UPDATE, DELETE). Alembic manages schema migrations.
2. **Pydantic v2 schemas** — API serialization and validation layer. Separate from ORM models. Used for Flask API responses, OpenAPI generation, and structured AI outputs.

Key technology choices:
- **SQLAlchemy 2.x** with `mapped_column()` declarative style
- **pgvector-python** for `Vector()` column type and `cosine_distance()` operator
- **Alembic** for migration management
- **Pydantic v2** for API response schemas (not SQLModel — separation of DB and API concerns is cleaner)

### Consequences

- **Positive:** Adding a column = one field in the ORM model. SQL is generated automatically.
- **Positive:** Alembic auto-generates migration scripts from model changes.
- **Positive:** Pydantic schemas enable OpenAPI → TypeScript pipeline ([B-50](#b-50-api-type-synchronization-pipeline-pydantic--openapi--typescript)).
- **Positive:** Pydantic schemas work directly as structured output format for LLM calls.
- **Positive:** pgvector-python provides native SQLAlchemy support for vector operations.
- **Negative:** Larger dependency tree (SQLAlchemy, Alembic, pgvector-python).
- **Negative:** Two model layers (ORM + Pydantic) instead of one custom class.
- **Negative:** Lambda cold start may increase slightly due to SQLAlchemy import size.
- **Trade-off:** Supersedes B-91 (SQL f-strings) — SQLAlchemy uses parameterized queries by default.

# ADR-015: UUID as Global Document Identifier — Rename s3_uuid to uuid

**Date:** 2026-03-30
**Status:** Accepted
**Decision Makers:** Ziutus
**Backlog Item:** B-102

## Context

Documents in `web_documents` are identified by an auto-incremented `id` (SERIAL). This ID is instance-specific — the same article has different IDs on NAS PostgreSQL vs AWS RDS. This creates problems for:

1. **Obsidian note references** — notes contain `Lenie AI id: 8799`, which is meaningless on another instance.
2. **Cross-instance synchronization** — no way to match documents between NAS and AWS databases.
3. **Stable external links** — API links with `?id=8799` break when data is moved between instances.

The table already has an `s3_uuid` column (`VARCHAR(100)`, nullable), but it is only populated for documents added through the AWS flow (Chrome Extension → Lambda `sqs-weblink-put-into` → DynamoDB → S3). Documents from `unknown_news_import.py`, `feed_monitor.py`, and manual inserts have `s3_uuid = NULL`.

## Decision

**Rename `s3_uuid` to `uuid` and auto-generate a UUID for every document.**

### Schema change

```sql
-- 1. Rename column
ALTER TABLE web_documents RENAME COLUMN s3_uuid TO uuid;

-- 2. Backfill NULL values
UPDATE web_documents SET uuid = gen_random_uuid() WHERE uuid IS NULL;

-- 3. Add constraints
ALTER TABLE web_documents ALTER COLUMN uuid SET NOT NULL;
ALTER TABLE web_documents ALTER COLUMN uuid SET DEFAULT gen_random_uuid();
ALTER TABLE web_documents ADD CONSTRAINT uq_web_documents_uuid UNIQUE (uuid);
```

### ORM model change

```python
# Before
s3_uuid: Mapped[str | None] = mapped_column(String(100))

# After
uuid: Mapped[str] = mapped_column(
    String(100), nullable=False, unique=True,
    server_default=func.gen_random_uuid(),
)
```

### Code rename scope

- **Backend Python**: ~88 occurrences in 15 files — mechanical find-replace `s3_uuid` → `uuid`
- **Lambda (AWS, on hold)**: 2 files, 5 occurrences — update when AWS is reactivated (tracked in [docs/aws-sync-backlog.md](aws-sync-backlog.md))
- **Frontend**: 0 occurrences — no impact
- **DynamoDB**: existing items keep `s3_uuid` field name (schemaless). `dynamodb_sync.py` maps `item.get("uuid") or item.get("s3_uuid")` for backward compatibility

### Obsidian notes convention

After migration, Obsidian notes reference documents by UUID:

```markdown
*Source: [title](URL) | Lenie: a1b2c3d4-e5f6-...*
```

This is stable across all instances.

## Alternatives Considered

| Alternative | Pros | Cons |
|---|---|---|
| **URL as identifier** | Zero migration, naturally unique | Long, unreadable in notes, some documents may share URL |
| **Short hash of URL** | Deterministic, readable | Not a standard format, collision risk with short hashes |
| **Keep `s3_uuid` + add separate `uuid`** | No rename needed | Two UUID-like columns, confusing semantics |
| **Use `id` with instance prefix** | No schema change | Breaks existing references, complex synchronization |

## Consequences

- Every new document gets a UUID automatically (DB default)
- Existing documents get a UUID via backfill migration
- Obsidian notes and external references become instance-independent
- `dynamodb_sync.py` needs backward-compat mapping for old DynamoDB items
- AWS Lambda code update deferred (tracked in `docs/aws-sync-backlog.md`)
- `s3_uuid` name disappears from codebase — clearer semantics (`uuid` is not S3-specific)

# AWS Sync Backlog

Rejestr zmian wprowadzonych lokalnie (backend, DB schema, konfiguracja), które wymagają synchronizacji z rozwiązaniem AWS (Lambda, API Gateway, DynamoDB, RDS) przy jego przywróceniu.

**Status AWS**: on hold — Lambda/API Gateway nie jest aktywnie deployowane. Zmiany są wdrażane lokalnie (NAS/Docker) i dokumentowane tutaj.

## Jak korzystać

Przy każdej zmianie, która wpływa na kod Lambda, schemat DynamoDB, schemat RDS (AWS), lub API Gateway — dodaj wpis poniżej. Przy przywróceniu AWS, przejdź listę i zaaplikuj zmiany.

---

## Pending changes

### DB schema

- [ ] **Rename `s3_uuid` → `uuid` + auto-generate for all documents**
  - Alembic migration: `ALTER TABLE web_documents RENAME COLUMN s3_uuid TO uuid`
  - Set `DEFAULT gen_random_uuid()`, `NOT NULL` (after backfill), `UNIQUE`
  - Backfill: `UPDATE web_documents SET uuid = gen_random_uuid() WHERE uuid IS NULL`
  - ORM model: `uuid: Mapped[str]` with `server_default=func.gen_random_uuid()`
  - *Reason*: UUID needed as global document identifier across instances (NAS, AWS RDS). `s3_uuid` was only set for S3-uploaded webpages, not all documents.
  - *Sprint*: TBD
  - *Added*: 2026-03-30

- [ ] **Table `import_logs`** (story 33-2)
  - Alembic migration exists locally but not applied to AWS RDS
  - *Added*: 2026-03-29

### Lambda code

- [ ] **`sqs-weblink-put-into`**: rename `s3_uuid` → `uuid` in DynamoDB item write (line ~136, 172)
  - *Depends on*: DB schema rename above
  - *Added*: 2026-03-30

- [ ] **`sqs-into-rds`**: rename `s3_uuid` → `uuid` in document field mapping (line ~41-42)
  - *Depends on*: DB schema rename above
  - *Added*: 2026-03-30

- [ ] **`app-server-db`, `app-server-internet`**: re-package with updated `backend/library/`
  - ORM model changes (ImportLog, uuid rename, lookup tables) require fresh ZIP build
  - *Added*: 2026-03-30

### DynamoDB

- [ ] **Field name `s3_uuid` in existing items**: `dynamodb_sync.py` must handle both `uuid` and `s3_uuid` (backward compat for old items)
  - New items written by updated Lambda will use `uuid`
  - Old items keep `s3_uuid` — no migration needed (DynamoDB is schemaless)
  - *Added*: 2026-03-30

### Lambda layers

- [ ] **B-52: Lambda layer security audit** — dependencies ~1.5+ years old. Audit, update, rebuild layer ZIPs.
  - *Reference*: [sprint-status.yaml](../_bmad-output/implementation-artifacts/sprint-status.yaml) (B-52)
  - *Added*: pre-existing backlog item

---

## Completed

<!-- Move items here when applied to AWS -->

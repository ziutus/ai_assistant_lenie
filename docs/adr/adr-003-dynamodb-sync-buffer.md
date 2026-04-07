# ADR-003: DynamoDB as Cloud-Local Synchronization Buffer

**Date:** 2025 (initial AWS architecture)
**Status:** Accepted

### Context

Documents are submitted from mobile devices at any time, but the PostgreSQL RDS database runs only on demand (cost optimization). A persistent, always-available store was needed to buffer incoming documents.

### Decision

Use DynamoDB (PAY_PER_REQUEST) to immediately store document metadata from mobile submissions. S3 stores the full content. The local PostgreSQL database synchronizes from DynamoDB/S3 when needed.

### Consequences

- **Positive:** Documents are never lost — DynamoDB is always available regardless of RDS state.
- **Positive:** Enables asynchronous processing via SQS when RDS starts.
- **Negative:** Two data stores to manage, potential sync issues.

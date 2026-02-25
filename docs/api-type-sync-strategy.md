# API Type Synchronization Strategy: Pydantic → OpenAPI → TypeScript

## Problem

Frontend (`shared/types/`) and backend (`backend/library/`) define the same data structures independently, leading to drift:

| Issue | Detail |
|-------|--------|
| **`id` type mismatch** | TS: `string`, Python: `int` (serial PK) |
| **`WebDocument` missing fields** | Backend `.dict()` returns 13 fields not in TS interface (paywall, created_at, title_english, project, etc.) |
| **`ListItem` field count** | TS: 5 fields, backend returns 10 |
| **`SearchResult` field count** | TS: 5 fields, backend returns 12 |
| **Enums as plain strings** | Backend has typed enums (`StalkerDocumentStatus`, `StalkerDocumentType`, `StalkerDocumentStatusError`), frontend treats them as `string` |
| **No contract** | No OpenAPI, JSON Schema, or Pydantic — backend uses custom classes + raw dicts |

## Chosen Approach

**Python Pydantic models → OpenAPI schema → generated TypeScript types**

```
┌─────────────────────┐     ┌──────────────┐     ┌───────────────────┐
│  Pydantic models    │────▶│ openapi.json │────▶│ shared/types/*.ts │
│  (source of truth)  │     │ (generated)  │     │ (generated)       │
│  backend/library/   │     │ docs/        │     │                   │
│  models/schemas/    │     └──────────────┘     └───────────────────┘
└─────────────────────┘
```

## Implementation Plan

### Phase 1: Pydantic Response Models

Create Pydantic v2 models for all API response shapes. These replace the manual `.dict()` methods.

**Files to create:**

```
backend/library/models/schemas/
├── __init__.py
├── documents.py        # WebDocumentResponse, WebDocumentListItem, SearchResultItem
├── api_responses.py    # ListResponse, SearchResponse, ErrorResponse, SuccessResponse
└── enums.py            # Re-export existing enums with Pydantic-compatible serialization
```

**Key models:**

```python
# backend/library/models/schemas/documents.py
from pydantic import BaseModel
from enum import Enum

class DocumentType(str, Enum):
    movie = "movie"
    youtube = "youtube"
    link = "link"
    webpage = "webpage"
    text_message = "text_message"
    text = "text"

class DocumentStatus(str, Enum):
    ERROR = "ERROR"
    URL_ADDED = "URL_ADDED"
    NEED_TRANSCRIPTION = "NEED_TRANSCRIPTION"
    # ... all 15 values from StalkerDocumentStatus

class DocumentStatusError(str, Enum):
    NONE = "NONE"
    ERROR_DOWNLOAD = "ERROR_DOWNLOAD"
    # ... all 14 values from StalkerDocumentStatusError

class WebDocumentResponse(BaseModel):
    id: int
    url: str
    title: str | None = None
    author: str | None = None
    source: str | None = None
    language: str | None = None
    tags: str | None = None
    summary: str | None = None
    text: str | None = None
    text_md: str | None = None
    text_english: str | None = None
    text_raw: str | None = None
    document_type: DocumentType
    document_state: DocumentStatus
    document_state_error: DocumentStatusError
    chapter_list: str | None = None
    note: str | None = None
    next_id: int | None = None
    previous_id: int | None = None
    next_type: str | None = None
    previous_type: str | None = None
    paywall: bool | None = None
    created_at: str | None = None        # formatted "%Y-%m-%d %H:%M:%S"
    title_english: str | None = None
    summary_english: str | None = None
    date_from: str | None = None
    original_id: str | None = None
    document_length: int | None = None
    transcript_job_id: str | None = None
    ai_summary_needed: bool | None = None
    s3_uuid: str | None = None
    project: str | None = None

class WebDocumentListItem(BaseModel):
    id: int
    url: str
    title: str | None = None
    document_type: str
    created_at: str
    document_state: str
    document_state_error: str | None = None
    note: str | None = None
    project: str | None = None
    s3_uuid: str | None = None

class SearchResultItem(BaseModel):
    id: int
    website_id: int
    text: str
    similarity: float
    url: str
    language: str | None = None
    text_original: str | None = None
    websites_text_length: int | None = None
    embeddings_text_length: int | None = None
    title: str | None = None
    document_type: str | None = None
    project: str | None = None
```

```python
# backend/library/models/schemas/api_responses.py
from pydantic import BaseModel

class ListResponse(BaseModel):
    status: str
    message: str
    encoding: str
    websites: list[WebDocumentListItem]
    all_results_count: int

class SearchResponse(BaseModel):
    status: str
    message: str
    encoding: str
    text: str
    websites: list[SearchResultItem]

class ErrorResponse(BaseModel):
    status: str = "error"
    message: str
```

### Phase 2: Use Models in Flask Routes

Replace raw dict returns with Pydantic model serialization:

```python
# Before (current)
return web_document.dict(), 200

# After
response = WebDocumentResponse.model_validate(web_document.__dict__)
return response.model_dump(mode="json"), 200
```

**Files to modify:**
- `backend/server.py` — all route handlers that return data
- `backend/library/stalker_web_document_db.py` — `.dict()` method can delegate to Pydantic
- Lambda handlers in `infra/aws/serverless/` — same changes for serverless endpoints

### Phase 3: Generate OpenAPI Schema

Option A — manual export script:

```python
# backend/scripts/generate_openapi.py
import json
from library.models.schemas.documents import WebDocumentResponse, WebDocumentListItem, SearchResultItem
from library.models.schemas.api_responses import ListResponse, SearchResponse

schema = {
    "openapi": "3.1.0",
    "info": {"title": "Lenie AI API", "version": "0.3.13.0"},
    "paths": { ... },  # manually or via flask-smorest
    "components": {
        "schemas": {
            "WebDocumentResponse": WebDocumentResponse.model_json_schema(),
            "WebDocumentListItem": WebDocumentListItem.model_json_schema(),
            "SearchResultItem": SearchResultItem.model_json_schema(),
            "ListResponse": ListResponse.model_json_schema(),
            "SearchResponse": SearchResponse.model_json_schema(),
        }
    }
}

with open("docs/openapi.json", "w") as f:
    json.dump(schema, f, indent=2)
```

Option B — use `flask-smorest` or `apiflask` for automatic OpenAPI generation from decorated routes. This is more work upfront but produces complete path definitions.

### Phase 4: Generate TypeScript from OpenAPI

Install and run `openapi-typescript`:

```bash
# One-time setup
cd web_interface_react
npm install -D openapi-typescript

# Generation (add to package.json scripts or Makefile)
npx openapi-typescript ../docs/openapi.json -o ../shared/types/generated.ts
```

Then update `shared/types/index.ts` to re-export from generated types instead of hand-written ones.

### Phase 5: CI Integration

Add to CI pipeline (CircleCI or Jenkins):

```bash
# 1. Generate OpenAPI from Pydantic
cd backend && python scripts/generate_openapi.py

# 2. Generate TS from OpenAPI
cd web_interface_react && npx openapi-typescript ../docs/openapi.json -o ../shared/types/generated.ts

# 3. Verify no diff (types are up to date)
git diff --exit-code shared/types/generated.ts || (echo "ERROR: Generated types are out of date. Run 'make generate-types'" && exit 1)
```

## Migration Path (Incremental)

The refactor can be done incrementally — one endpoint at a time:

1. **Start with `/website_get`** — most used, clearest contract
2. Add `WebDocumentResponse` model, use it in the route
3. Generate OpenAPI + TS for just this model
4. Verify frontend still works (TS types become a superset — no breaking changes)
5. Move to `/website_list`, `/website_similar`, etc.

During migration, hand-written `shared/types/` coexists with generated types. Once all endpoints are covered, remove hand-written types.

## Known Decisions to Make

| Decision | Options | Notes |
|----------|---------|-------|
| **`id` type** | Fix frontend to `number` | Backend always sends `int`, frontend incorrectly declares `string` |
| **Nullable fields** | `T \| null` vs `T \| undefined` | Pydantic uses `None`, TS should use `null` to match JSON |
| **Enum representation** | String enums vs string literals | `openapi-typescript` generates string literal unions by default — matches current TS approach |
| **OpenAPI generation tool** | Manual script vs flask-smorest vs apiflask | Manual is simplest for current architecture, flask-smorest for full path coverage |
| **Pydantic dependency** | Add to base deps vs optional extra | Should be base — it's core to API contract |

## Files Affected (Full List)

### New files
- `backend/library/models/schemas/__init__.py`
- `backend/library/models/schemas/documents.py`
- `backend/library/models/schemas/api_responses.py`
- `backend/library/models/schemas/enums.py`
- `backend/scripts/generate_openapi.py`
- `docs/openapi.json` (generated)
- `shared/types/generated.ts` (generated)

### Modified files
- `backend/pyproject.toml` — add `pydantic` dependency
- `backend/server.py` — use Pydantic models in route handlers
- `backend/library/stalker_web_document_db.py` — align `.dict()` with Pydantic model
- `infra/aws/serverless/app-server-db/handler.py` — same changes for Lambda
- `infra/aws/serverless/app-server-internet/handler.py` — same
- `shared/types/index.ts` — re-export from generated.ts
- `web_interface_react/package.json` — add `openapi-typescript` dev dependency
- `Makefile` — add `generate-types` target
- CI config — add type generation verification step

## Related Documentation

- [Shared Types](shared-types.md) — current shared TS types setup
- [API Contracts](api-contracts-backend.md) — existing backend API documentation
- [Architecture Backend](architecture-backend.md) — backend architecture overview

# AssemblyAI Usage Tracking — Stories & Tasks

## Context

Track AssemblyAI transcription spending against a $50 budget. AssemblyAI has no billing API, so we log each transcription locally and calculate costs from known prices.

**Source plan:** `~/.claude/plans/proud-yawning-shell.md`

---

## Story 1: Database — Create `transcription_log` Table

**Size:** S | **Priority:** P0 (blocks all other stories)

Create the table to store transcription usage records.

### Tasks

1. **Create SQL migration** `backend/database/init/11-create-transcription-log.sql`
   - Table: `transcription_log` (id, document_id FK nullable ON DELETE SET NULL, provider VARCHAR(50), speech_model VARCHAR(100), audio_duration_seconds INTEGER, cost_usd NUMERIC(10,4), transcript_job_id VARCHAR(255), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
   - Indexes: on `provider`, on `created_at`

2. **Add SQLAlchemy model** `TranscriptionLog` to `backend/library/db/models.py`
   - All columns matching SQL
   - Relationship to `WebDocument` (optional, nullable FK)
   - Class method `get_usage_summary(session, provider=None)` — returns dict with totals (sum cost, sum seconds, count, grouped by provider)

3. **Run migration on NAS** (`192.168.200.7:5434`)

### Acceptance Criteria
- Table exists in database
- SQLAlchemy model can create/query records
- `get_usage_summary()` returns correct aggregation

### Definition of Done
- SQL file committed
- Model added and tested with unit test for `get_usage_summary()`

---

## Story 2: Update Transcription Prices

**Size:** XS | **Priority:** P0 (blocks cost calculation)

Update hardcoded prices in `backend/library/transcript.py` to match current AssemblyAI pricing.

### Tasks

1. **Update `transcript_prices_by_minute`** dict:
   ```python
   # Prices last verified: 2026-03-12 from https://www.assemblyai.com/pricing
   # No API available for price checking — manual verification required
   # Keys match `speech_model_used` values from AssemblyAI API response
   transcript_prices_by_minute = {
       'OpenAI': 0.006,                # https://openai.com/api/pricing/
       'assemblyai_best': 0.0035,      # $0.21/hr — Universal-3 Pro (speech_model_used="best")
       'assemblyai_universal': 0.0025, # $0.15/hr — Universal-2 (speech_model_used="universal")
       'assemblyai_slam-1': 0.0035,    # $0.21/hr — SLAM-1 (assume same as best, verify)
   }
   ```

2. **Add helper function** `get_assemblyai_price_per_minute(speech_model_used: str | None) -> float`
   - Maps API `speech_model_used` values (`best`, `slam-1`, `universal`, `None`) to prices
   - `None` → fallback to `assemblyai_best` (most expensive, conservative estimate)

3. **Update `transcript_price()`** to accept optional `speech_model` param for AssemblyAI
4. **Remove `'AWS': 0.02400`** from pricing dict (see Story 6 — AWS Transcribe removal)

### Acceptance Criteria
- Prices match https://www.assemblyai.com/pricing as of 2026-03-12
- Old `'assemblyai': 0.002` key replaced
- Price keys align with `speech_model_used` values from API

### Files
- `backend/library/transcript.py`

---

## Story 3: Log Transcription Usage After Each AssemblyAI Job

**Size:** M | **Priority:** P1

After a successful AssemblyAI transcription, save a record to `transcription_log` with duration, model, and calculated cost.

### Tasks

1. **Modify `backend/library/youtube_processing.py`** (~line 263, after `transcript.status == "completed"`):
   - Read `transcript.audio_duration` → `Optional[int]` (seconds) — **verified in SDK docs**
   - Read `transcript.speech_model_used` → `Optional[str]` — **verified** (NOT `speech_model` which is deprecated!)
     - Allowed values: `best`, `slam-1`, `universal`
   - Calculate cost using `get_assemblyai_price_per_minute(speech_model_used)`
   - Create `TranscriptionLog` record and commit

2. **Add error handling for "Insufficient Funds"** (HTTP 400 from AssemblyAI):
   - Catch in the `transcript.status == error` branch (check `transcript.error` message)
   - Set `document_state = ERROR`, `document_state_error = TRANSCRIPTION_INSUFFICIENT_FUNDS`
   - Log warning with remaining balance estimate

3. **Add new enum values** to `backend/library/models/stalker_document_status_error.py`:
   - `TRANSCRIPTION_ERROR = 18` — general transcription failure
   - `TRANSCRIPTION_INSUFFICIENT_FUNDS = 19` — out of budget
   - Also add these to the `document_status_error_types` lookup table (SQL + seed)

### SDK Attribute Reference (verified 2026-03-12)
- `transcript.audio_duration` → `int | None` (seconds)
- `transcript.speech_model_used` → `str | None` (values: `best`, `slam-1`, `universal`)
- `transcript.speech_model` → DEPRECATED, do not use
- `transcript.id` → `str` (job ID, already used in code)

### Price Mapping (for Story 2)
| `speech_model_used` value | AssemblyAI product | Price/min |
|---------------------------|-------------------|-----------|
| `best` | Universal-3 Pro | $0.0035 |
| `slam-1` | SLAM-1 | TBD (verify) |
| `universal` | Universal-2 | $0.0025 |
| `None` (default) | Universal-2 | $0.0025 |

### Acceptance Criteria
- Every successful AssemblyAI transcription creates a `transcription_log` record
- `audio_duration_seconds` and `cost_usd` are populated correctly
- `speech_model` column stores the value from `transcript.speech_model_used`
- Insufficient funds error is caught and sets proper document state

### Files
- `backend/library/youtube_processing.py`
- `backend/library/models/stalker_document_status_error.py` (add 2 new enum values)
- `backend/database/init/09-create-lookup-tables.sql` (seed new error types)

---

## Story 4: New Endpoint `GET /transcription_usage`

**Size:** S | **Priority:** P1

API endpoint to check transcription spending and remaining budget.

### Tasks

1. **Add env variable** `TRANSCRIPTION_BALANCE_USD` to `scripts/vars-classification.yaml`
   - type: config, required: false, default: "50.00", used_by: [docker, local]

2. **Add endpoint** `GET /transcription_usage` to `backend/server.py`
   - Requires `x-api-key` auth (same as all other endpoints)
   - Calls `TranscriptionLog.get_usage_summary(session)`
   - Returns JSON:
     ```json
     {
       "balance_initial_usd": 50.00,
       "total_spent_usd": 3.24,
       "balance_remaining_usd": 46.76,
       "total_seconds": 97200,
       "total_minutes": 1620,
       "transactions_count": 12,
       "by_provider": {
         "assemblyai": {"spent_usd": 3.24, "minutes": 1620, "count": 12}
       }
     }
     ```
   - `balance_initial_usd` from `TRANSCRIPTION_BALANCE_USD` env var (default 50.00)

3. **Unit test** for the endpoint response format

### Acceptance Criteria
- `curl -H "x-api-key: ..." http://localhost:5000/transcription_usage` returns valid JSON
- Balance calculation is correct (initial - spent = remaining)
- Works with empty `transcription_log` table (returns zeros)

### Files
- `backend/server.py`
- `scripts/vars-classification.yaml`
- `backend/tests/unit/test_transcription_usage.py` (new)

---

## Story 5: Unit Tests

**Size:** S | **Priority:** P2

### Tasks

1. **Test cost calculation** — verify `math.ceil(seconds/60) * price_per_minute` for various durations
2. **Test `get_assemblyai_price_per_minute()`** — known models map to correct prices, unknown model falls back
3. **Test `TranscriptionLog.get_usage_summary()`** — mock session, verify aggregation logic
4. **Test `/transcription_usage` endpoint** — mock DB, verify response shape and balance calculation

### Files
- `backend/tests/unit/test_transcript_prices.py` (new)
- `backend/tests/unit/test_transcription_usage.py` (new)

---

## Execution Order

```
Story 1 (DB table + model)  ──┐
Story 2 (update prices)     ──┼──→ Story 3 (log after transcription) ──→ Story 5 (tests)
                               └──→ Story 4 (usage endpoint)          ──→ Story 5 (tests)

Story 6 (remove AWS Transcribe) — independent, can run in parallel
```

**Decision:** AWS Transcribe is too expensive and never used — removed from the codebase. The `transcription_log` table is provider-agnostic but in practice only AssemblyAI will be logged.

## Story 6: Remove AWS Transcribe Dead Code

**Size:** M | **Priority:** P2 (can be done in same sprint or next)

AWS Transcribe is too expensive and never used — AssemblyAI is the only transcription provider. Remove all AWS Transcribe code to simplify the codebase.

### Tasks

1. **Delete** `backend/library/api/aws/transcript.py`
2. **Simplify `backend/library/transcript.py`**:
   - Remove `from library.api.aws.transcript import aws_transcript` import
   - Remove `'AWS': 0.02400` from pricing dict
   - Remove `provider == 'aws'` branch from `transcript()` function
3. **Simplify `backend/library/youtube_processing.py`**:
   - Remove `from library.api.aws.transcript import aws_transcript` import
   - Remove `s3_bucket_transcript = os.getenv("AWS_S3_TRANSCRIPT")` (line 72)
   - Remove entire `elif transcript_provider == "aws":` branch (lines 277-311)
   - Remove `boto3` and `requests` imports if no longer needed
4. **Simplify `backend/web_documents_do_the_needful_new.py`**:
   - Remove `AWS_S3_TRANSCRIPT` validation check (lines 71-73)
5. **Update config**: mark `AWS_S3_TRANSCRIPT` as deprecated in `scripts/vars-classification.yaml`, update `TRANSCRIPT_PROVIDER` description to remove `aws_transcribe` option
6. **Update Kubernetes configs** (if applicable):
   - `infra/kubernetes/kustomize/overlays/gke-dev/server_configmap.yaml`
   - `infra/kubernetes/helm/lenie-ai-server/values.yaml`
   - `infra/kubernetes/helm/lenie-ai-server/templates/configmap.yaml`
7. **Update CLAUDE.md docs**: remove AWS Transcribe mentions from `backend/library/CLAUDE.md`

### Acceptance Criteria
- No references to `aws_transcript` in Python code
- `transcript_provider` only supports `assemblyai` (and `local` placeholder)
- All tests pass after removal

---

## Pre-implementation Checklist

- [x] ~~Verify AssemblyAI SDK attribute names~~ — **Done (2026-03-12)**: use `transcript.audio_duration` (int, seconds) and `transcript.speech_model_used` (str, NOT deprecated `speech_model`). Values: `best`, `slam-1`, `universal`.
- [x] ~~Confirm `StalkerDocumentStatusError` enum~~ — **Done**: no transcription errors exist. Add `TRANSCRIPTION_ERROR = 18` and `TRANSCRIPTION_INSUFFICIENT_FUNDS = 19`.
- [ ] Verify SLAM-1 pricing — not listed separately on assemblyai.com/pricing, assumed same as `best` ($0.21/hr)

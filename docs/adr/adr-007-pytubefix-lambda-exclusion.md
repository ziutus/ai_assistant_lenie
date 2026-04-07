# ADR-007: pytubefix Excluded from Lambda — Serverless YouTube Processing Requires Alternative Compute

**Date:** 2026-02 (Sprint 6, Epic 20)
**Status:** Accepted (constraint identified), Decision Pending (future compute model)
**Decision Makers:** Ziutus

### Context

During the Lambda layer rebuild for Epic 20 (Secrets Management), `pytube` was replaced with `pytubefix` (the maintained fork). The `pytubefix` package has a transitive dependency on `nodejs-wheel-binaries` — a ~60 MB Node.js binary bundled as a Python wheel. This single dependency exceeds the AWS Lambda layer size limit (50 MB zipped / 250 MB unzipped), making it impossible to include `pytubefix` in any Lambda layer.

The previous `lenie_all_layer` (with `pytubefix`) produced a 66 MB ZIP. After removing `pytubefix`, the layer is ~1.6 MB.

### Analysis

Modules that use `pytubefix`:
- `backend/library/stalker_youtube_file.py` — YouTube URL validation, metadata extraction, video download
- `backend/library/youtube_processing.py` — orchestrates YouTube processing pipeline (imports `stalker_youtube_file`)

These modules are **not imported** by any Lambda function handler (`app-server-db`, `app-server-internet`, `sqs-into-rds`, `sqs-weblink-put-into`). YouTube processing currently runs only in:
- Flask server (`server.py`) in Docker/K8s deployments
- Batch scripts (`web_documents_do_the_needful_new.py`) on developer machines

### Decision

1. **Remove `pytubefix` from `lenie_all_layer`** — the layer now contains only: `urllib3`, `requests`, `beautifulsoup4`, `python-dotenv`.
2. **Document this as a permanent Lambda constraint** — `pytubefix` (and any package depending on `nodejs-wheel-binaries`) cannot be used in Lambda layers.
3. **Defer the compute model decision** for serverless YouTube processing to a future sprint (see B-67 in backlog).

### Constraint: Lambda Layer Size Limits

| Limit | Value |
|-------|-------|
| Layer ZIP (compressed) | 50 MB |
| Layer unzipped | 250 MB |
| All layers combined (unzipped) | 250 MB |
| Lambda container image | 10 GB |

Packages that exceed these limits cannot be included in layers. Alternative approaches:

| Option | Max Size | Cold Start | Cost Model |
|--------|----------|------------|------------|
| Lambda layer | 50 MB zipped | ~100-500 ms | Per-invocation |
| Lambda container image | 10 GB | ~5-10 s | Per-invocation |
| ECS Fargate task (on-demand) | Unlimited | ~30-60 s | Per-second (vCPU + memory) |
| ECS Fargate service | Unlimited | Always warm | Per-second (continuous) |

### Consequences

- **Positive:** `lenie_all_layer` reduced from 66 MB to 1.6 MB — well within Lambda limits.
- **Positive:** No impact on current Lambda functions — none of them use YouTube processing.
- **Negative:** YouTube processing in the serverless path is blocked until an alternative compute model is chosen and implemented.
- **Negative:** If a future feature requires YouTube metadata in a Lambda-triggered workflow, it will need either a Lambda container image (~10 GB limit, longer cold starts) or ECS Fargate task (more infrastructure to manage).

### Related Artifacts

- `infra/aws/serverless/lambda_layers/layer_create_lenie_all.sh` — layer build script (pytubefix removed)
- `infra/aws/serverless/CLAUDE.md` — "Known Limitations" section
- `infra/aws/CLAUDE.md` — "Lambda Serverless Constraints" section
- `_bmad-output/planning-artifacts/epics/backlog.md` — B-67: Choose Compute Model for Serverless YouTube Processing
- `backend/library/stalker_youtube_file.py` — pytubefix consumer
- `backend/library/youtube_processing.py` — pytubefix consumer (via stalker_youtube_file)

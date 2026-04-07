# ADR-011: Remove AWS Transcribe — Use AssemblyAI as Sole Transcription Provider

**Date:** 2026-03-12
**Status:** Accepted
**Decision Makers:** Ziutus

### Context

The transcription subsystem supports two providers: AWS Transcribe and AssemblyAI. The routing is handled by `backend/library/transcript.py` with a `provider` parameter (`aws` or `assemblyai`). In practice, **AWS Transcribe has never been used** — AssemblyAI is the default and only provider configured in any environment.

Cost comparison per minute of audio:

| Provider | Cost/min | Cost/hr |
|----------|----------|---------|
| AWS Transcribe | $0.0240 | $1.44 |
| AssemblyAI Universal-3 Pro | $0.0035 | $0.21 |
| AssemblyAI Universal-2 | $0.0025 | $0.15 |

AWS Transcribe is **6.9x–9.6x more expensive** than AssemblyAI with no quality advantage for this use case (Polish and English speech-to-text of YouTube videos).

Additionally, the AWS Transcribe flow requires uploading video files to S3 first (`AWS_S3_TRANSCRIPT` bucket), adding latency and S3 storage costs. AssemblyAI accepts local file uploads directly.

### Decision

1. **Remove all AWS Transcribe code** from the codebase.
2. **AssemblyAI is the sole transcription provider** — no provider routing needed.
3. **Keep the `provider` column** in the new `transcription_log` table for future extensibility (if a cheaper/better provider appears).

### Files Affected

| File | Change |
|------|--------|
| `backend/library/api/aws/transcript.py` | **DELETE** — entire module |
| `backend/library/transcript.py` | Remove AWS import, pricing, and routing branch |
| `backend/library/youtube_processing.py` | Remove AWS Transcribe branch (lines 277-311), S3 upload logic, boto3/requests imports |
| `backend/web_documents_do_the_needful_new.py` | Remove `AWS_S3_TRANSCRIPT` validation check |
| `scripts/vars-classification.yaml` | Mark `AWS_S3_TRANSCRIPT` as deprecated, simplify `TRANSCRIPT_PROVIDER` |
| `infra/kubernetes/kustomize/overlays/gke-dev/server_configmap.yaml` | Remove `AWS_S3_TRANSCRIPT` |
| `infra/kubernetes/helm/lenie-ai-server/values.yaml` | Remove `AWS_S3_TRANSCRIPT` |
| `infra/kubernetes/helm/lenie-ai-server/templates/configmap.yaml` | Remove `AWS_S3_TRANSCRIPT` |
| `backend/library/CLAUDE.md` | Update documentation |

### Rationale

1. **Cost.** At $1.44/hr vs $0.21/hr, AWS Transcribe is prohibitively expensive for a personal project with a $50 transcription budget. The same budget buys ~35 hours on AWS Transcribe vs ~238 hours on AssemblyAI.

2. **Dead code.** The AWS Transcribe path has never been executed in production. Keeping it increases maintenance burden and cognitive load without any benefit.

3. **Simpler architecture.** Removing the provider routing logic, S3 upload step, and `AWS_S3_TRANSCRIPT` configuration simplifies both the code and the deployment.

4. **No lock-in risk.** The `transcription_log` table retains a `provider` column. If a better option appears in the future, the logging infrastructure is ready. The actual transcription code can be added back with a new provider module.

### Consequences

- **Positive:** Simpler codebase — one provider, no routing logic, no S3 upload step.
- **Positive:** Fewer environment variables to configure (`AWS_S3_TRANSCRIPT`, `TRANSCRIPT_PROVIDER` becomes optional).
- **Positive:** Removes dependency on S3 bucket for transcription workflow.
- **Negative:** No fallback provider — if AssemblyAI is down or changes pricing, transcription is blocked until an alternative is implemented.
- **Negative:** Loss of AWS Transcribe multi-language auto-detection feature (not currently used).

### Related Artifacts

- `_bmad-output/implementation-artifacts/stories-assemblyai-usage-tracking.md` — Story 6: Remove AWS Transcribe Dead Code
- [ADR-007](#adr-007-pytubefix-excluded-from-lambda--serverless-youtube-processing-requires-alternative-compute) — Lambda constraints (YouTube processing already excluded from Lambda)
- `backend/library/api/asemblyai/asemblyai_transcript.py` — remaining transcription implementation

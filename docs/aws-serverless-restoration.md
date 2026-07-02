# AWS Serverless — Decommission Record & Restoration Guide

**Status as of:** 2026-07-02
**Account:** production application account (see `env.sh`, profile `default`), region `us-east-1`
**Why this document exists:** in July 2026 the unused parts of the AWS serverless stack (RDS and everything that existed only to serve it) were decommissioned to cut cost and complexity. The intent is to possibly restore a serverless document-serving path in ~6 months, when the application has evolved. This document captures the exact prior state, the lessons from the audit, and a step-by-step restoration procedure so that restoration is mostly mechanical.

Related: [architecture-infra.md](architecture-infra.md), [infra/aws/CLAUDE.md](../infra/aws/CLAUDE.md), [infra/aws/serverless/CLAUDE.md](../infra/aws/serverless/CLAUDE.md), [infra/aws/cloudformation/CLAUDE.md](../infra/aws/cloudformation/CLAUDE.md)

---

## 1. What still runs (do not touch)

The active ingestion path is untouched and works end-to-end:

| Resource | Purpose |
|---|---|
| `lenie-dev-url-add` Lambda | `/url_add` endpoint (Chrome extension) → writes to DynamoDB + S3, enqueues to SQS |
| `lenie-dev-weblink-put-into-sqs` Lambda | Alternative SQS ingestion path |
| `lenie-dev-sqs-size` Lambda | `/infra/sqs/size` endpoint (queue length in UI) |
| DynamoDB `lenie_dev_documents` | Sole cloud document store (daily writes) |
| S3 `lenie-dev-website-content` | Webpage content (`{uuid}.txt` / `{uuid}.html`) |
| API Gateway `lenie_split` (app) + `lenie_dev_infra` | `/url_add` + `/sqs/size`; custom domain `api.dev.lenie-ai.eu` |
| CloudFront + S3 hosting | app, app2, landing page |
| `imports/dynamodb_sync.py` (local) | The actual cloud→local sync path: DynamoDB + S3 → local PostgreSQL |

⚠️ Known consequence: the **hosted frontends** (`app.dev.lenie-ai.eu`, `app2.dev.lenie-ai.eu`) can no longer browse documents against the AWS API (those endpoints are gone) — they are only useful pointed at a reachable Docker/NAS backend. The hosting itself (S3+CloudFront) was left in place.

Sanitized configuration snapshots of the surviving Lambdas (runtime, layers, env **key names**, roles) are in [`infra/aws/serverless/config-snapshots/`](../infra/aws/serverless/config-snapshots/).

## 2. What was removed and when

### 2026-07-02 — RDS and its support infrastructure (PR [#180](https://github.com/ziutus/ai_assistant_lenie/pull/180))

Evidence of disuse: no `DatabaseConnections` since 2026-04-29, no `rds-manager` invocations since 2026-02-24, OpenVPN bastion stopped since 2026-01-23.

| Resource | How removed | Restoration data |
|---|---|---|
| RDS `lenie-dev` (db.t3.micro, 20 GB, PostgreSQL + pgvector) | `delete-db-instance` (was never actually CF-managed) | **Final snapshot: `lenie-dev-final-snapshot-20260702`** — full data as of deletion. Template: `templates/rds.yaml` (still in repo, supports snapshot restore) |
| OpenVPN EC2 bastion (`openvpn-own`, default VPC) | terminated | **No AMI/backup existed.** Must be rebuilt from scratch (accepted). Helper script survives: `infra/aws/tools/aws_ec2_route53.py` |
| Stack `lenie-dev-secrets` (RDS password secret) | stack deleted | `templates/secrets.yaml` in repo; generates a **new** password — after snapshot restore run `aws rds modify-db-instance --master-user-password` to match |
| Stack `lenie-dev-sqs-to-rds-lambda` | stack deleted | `templates/sqs-to-rds-lambda.yaml` in repo |
| Stack `lenie-dev-sqs-to-rds-step-function` | stack deleted | `templates/sqs-to-rds-step-function.yaml` in repo |
| `rds-manager`, `ec2-manager` Lambdas + `/database/*`, `/vpn_server/*` API paths | trimmed out of `api-gw-infra.yaml` | Full previous template: `git show 34d3306:infra/aws/cloudformation/templates/api-gw-infra.yaml`; Lambda sources still in `lambdas/rds-manager/`, `lambdas/ec2-manager/` |
| Frontend DB/VPN widgets, `useDatabase`/`useVpnServer` hooks | removed from `web_interface_react` | `git show 34d3306:web_interface_react/src/modules/shared/hooks/useDatabase.ts` (and `useVpnServer.ts`) |

### 2026-07-02 — `app-server-db` Lambda (manual, follow-up to PR #180)

Deleted directly (was never CF-managed). Served 8 document-CRUD endpoints in "AWS Serverless" frontend mode: `/website_list`, `/website_get`, `/website_save`, `/website_delete`, `/website_is_paid`, `/website_get_next_to_correct`, `/website_similar`, `/website_split_for_embedding`.

Configuration at deletion:
- Runtime `python3.11`, handler `lambda_function.lambda_handler`, ran **inside VPC** (default VPC `vpc-07f2…`, subnets ×2, SG ×1) to reach RDS — hence no internet access (no NAT Gateway)
- Role: `lenie_2_db-role-l3k9y1uv` (manually created, service-role path) with basic execution + tracer + VPC access policies
- Required env vars (per [serverless/CLAUDE.md](../infra/aws/serverless/CLAUDE.md)): `POSTGRESQL_HOST/USER/PASSWORD/PORT/DATABASE`, `OPENAI_API_KEY`, `OPENAI_ORGANIZATION`, `EMBEDDING_MODEL`, `BACKEND_TYPE=postgresql`
- Source: `infra/aws/serverless/lambdas/app-server-db/` (still in repo); packaged with `backend/library` via `zip_to_s3.sh` (`function_list_cf_app.txt`)
- API Gateway endpoint definitions: `git show e9e7e20:infra/aws/cloudformation/templates/api-gw-app.yaml` (full 11-endpoint version)

### 2026-07-02 — `app-server-internet` Lambda (deleted after audit)

Audit findings that led to deletion:
- **Zero invocations in ≥90 days** (the only one was our test)
- **The deployed zip was broken**: `Runtime.ImportModuleError: No module named 'library.webpage_parse_result'` — the module moved to `library/models/webpage_parse_result.py` in the repo, but the deployed package (last modified 2026-02-27) had the old import path in `lambda_function.py`. Every invocation would have failed.
- Served `/website_download_text_content` and `/ai_embedding_get` (webpage download + Bedrock/OpenAI embeddings)
- Its manually-created execution role `lenie_2_internet-role-rlzbsimx` had **`AdministratorAccess`** (!) plus Translate/Comprehend/Bedrock full access

What was done:
- Function deleted; old role and its custom policy deleted (AdministratorAccess risk eliminated). The old `app-server-db` role (`lenie_2_db-role-l3k9y1uv`) and its three custom policies were deleted too.
- A complete, ready-to-deploy least-privilege CF template is kept: [`templates/app-server-internet.yaml`](../infra/aws/cloudformation/templates/app-server-internet.yaml) (role: logs, X-Ray, `bedrock:InvokeModel` scoped to `amazon.titan-embed-*`, `ssm:GetParameter` scoped to `/lenie/dev/*`; function: correct layers/runtime/env). Commented out in `deploy.ini`.
- Both app-server endpoints removed from `api-gw-app.yaml`; the app API now serves **only `/url_add`**. Verified post-trim: `OPTIONS /url_add` → 200, `POST /url_add` (no key) → 403 through `api.dev.lenie-ai.eu`.
- The "AWS Serverless" option was removed from the `web_interface_react` connect screen (Docker/NAS is the only mode).

## 3. Anti-patterns found — do NOT restore these

1. **`AdministratorAccess` on a Lambda execution role** (`lenie_2_internet-role-rlzbsimx`). Restore from the least-privilege pattern in `templates/app-server-internet.yaml` / `api-gw-infra.yaml` instead.
2. **Plaintext secrets in Lambda environment variables** (`OPENAI_API_KEY`, `ASSEMBLYAI`, `POSTGRESQL_PASSWORD` were readable via `get-function-configuration`). On restore, either use `SECRETS_BACKEND=aws` (config_loader reads SSM at cold start — the code already supports it and the SSM parameters under `/lenie/dev/*` already exist) or `{{resolve:secretsmanager:...}}` in CF. Note: plain `{{resolve:ssm-secure:...}}` does **not** work for Lambda env vars.
   - ⚠️ **Rotation required**: `OPENAI_API_KEY` and `ASSEMBLYAI` values were exposed in a work session on 2026-07-02 — rotate before restoring anything that uses them.
3. **Lambdas created manually outside CloudFormation** (`app-server-db`, `app-server-internet`, their roles). This made auditing and cleanup manual. On restore, deploy everything via `deploy.sh` from templates.
4. **Broken deploy pipeline for app functions**: the zip packaging (`zip_to_s3.sh` + `function_list_cf_app.txt`) can drift from `backend/library` layout (this is exactly how `app-server-internet` broke silently). On restore, add a post-deploy smoke test invocation.
5. **SQS queue with no consumer**: `sqs-weblink-put-into` and `url-add` still enqueue to `lenie-dev-documents`, but nothing consumes it since `sqs-to-rds` was removed — messages expire after 14 days. Harmless, but on restore either wire the new consumer to this queue or stop enqueueing.

## 4. Restoration procedure (step by step)

Assumption: the future document store may be RDS again (snapshot restore) **or** DynamoDB-backed Lambdas — decide first. The steps below restore the RDS variant 1:1; for a DynamoDB variant, skip steps 2–5 and rewrite `app-server-db` against DynamoDB.

1. **Rotate secrets** (`OPENAI_API_KEY`, `ASSEMBLYAI`) and update SSM `/lenie/dev/*` via `python scripts/env_to_vault.py ssm set ...`.
2. **Restore RDS**: `aws rds restore-db-instance-from-db-snapshot --db-instance-identifier lenie-dev --db-snapshot-identifier lenie-dev-final-snapshot-20260702 ...` or redeploy `templates/rds.yaml` (supports snapshot parameter). Data will be 2026-07-02 vintage — re-sync newer documents from DynamoDB using `imports/dynamodb_sync.py` logic in reverse or re-run embeddings locally.
3. **Restore secrets stack**: uncomment `templates/secrets.yaml` in `deploy.ini`, deploy, then align the restored instance's master password with the newly generated secret.
4. **Restore SQS→RDS pipeline**: uncomment `templates/sqs-to-rds-lambda.yaml` and `templates/sqs-to-rds-step-function.yaml` in `deploy.ini`, package Lambda zips (`zip_to_s3.sh`), deploy.
5. **Restore infra API management endpoints**: re-add `rds-manager`/`ec2-manager` sections to `api-gw-infra.yaml` from `git show 34d3306:...`, restore `OpenvpnEC2Name` parameter, redeploy + `aws apigateway create-deployment --rest-api-id <infra-id> --stage-name v1`.
6. **Restore app-server Lambdas under CloudFormation** (do not recreate manually):
   - `app-server-internet`: template already exists (`templates/app-server-internet.yaml`); fix the import path in `lambdas/app-server-internet/lambda_function.py` (`library.webpage_parse_result` → `library.models.webpage_parse_result`), package, deploy, smoke-test.
   - `app-server-db`: write an analogous template (copy the internet one; add VPC config + PostgreSQL env from Secrets Manager resolve); source is in `lambdas/app-server-db/`.
7. **Restore API endpoints**: re-add the 8 `app-server-db` paths and 2 `app-server-internet` paths to `api-gw-app.yaml` from `git show e9e7e20:...`, deploy, create new API GW deployment.
8. **Restore frontend**: revert the "AWS Serverless" removals in `web_interface_react` (hooks `useDatabase`/`useVpnServer`, widgets, `connect.tsx` two-step validation) from git history (`git show 34d3306:...` for pre-decommission state).
9. **OpenVPN bastion (only if VPC-private RDS)**: rebuild from scratch (no backup existed); after creation, tag it, store instance id in SSM `/lenie/dev/openvpn-server/ec2-name`, and re-add the `aws-start-openvpn` Makefile target (removed in PR #180). Consider making an AMI this time.
10. **Verify**: run `make aws-smoke-test`; check CloudWatch for errors; confirm each restored endpoint responds through `api.dev.lenie-ai.eu`.

## 5. Key git reference points

| Commit / tag | What it preserves |
|---|---|
| `34d3306` | Last commit with full pre-decommission state: complete `api-gw-infra.yaml`, frontend DB/VPN widgets, Makefile target |
| `e9e7e20` (merge of PR #180) | Full 11-endpoint `api-gw-app.yaml` (trimmed in a later commit) |
| PR [#180](https://github.com/ziutus/ai_assistant_lenie/pull/180) | Complete decommission diff with rationale |
| RDS snapshot `lenie-dev-final-snapshot-20260702` | Database content (**lives in AWS, not git** — do not delete it without checking this doc) |

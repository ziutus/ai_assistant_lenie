# Infrastructure Metrics — Single Source of Truth

> Last verified: 2026-02-21 | Post-Sprint 4 (Epic 15 API Gateway consolidation complete)

This file is the authoritative source for infrastructure counts. All other documentation files should reference or be consistent with values here.

## Flask Server (Docker / Kubernetes)

**Entry point:** `backend/server.py` | **Total endpoints: 19**

| # | Path | Method | Category |
|---|------|--------|----------|
| 1 | `/` | GET | Info |
| 2 | `/url_add` | POST | Document CRUD |
| 3 | `/website_list` | GET | Document CRUD |
| 4 | `/website_get` | GET | Document CRUD |
| 5 | `/website_save` | POST | Document CRUD |
| 6 | `/website_delete` | GET | Document CRUD |
| 7 | `/website_is_paid` | POST | Metadata |
| 8 | `/website_get_next_to_correct` | GET | Metadata |
| 9 | `/ai_get_embedding` | POST | AI Operations |
| 10 | `/website_similar` | POST | AI Operations |
| 11 | `/website_download_text_content` | POST | Content Processing |
| 12 | `/website_text_remove_not_needed` | POST | Content Processing |
| 13 | `/website_split_for_embedding` | POST | Content Processing |
| 14 | `/healthz` | GET | Health & Info |
| 15 | `/metrics` | GET | Health & Info |
| 16 | `/startup` | GET | Health & Info |
| 17 | `/readiness` | GET | Health & Info |
| 18 | `/liveness` | GET | Health & Info |
| 19 | `/version` | GET | Health & Info |

All routes except `/startup`, `/readiness`, `/liveness`, `/version` require `x-api-key` header.

## AWS Serverless (Lambda + API Gateway)

### API Gateways

**3 REST APIs in AWS** (2 API Gateway templates + 1 Lambda template with embedded API GW):

**api-gw-app (`lenie_split`) — 11 endpoint paths:**

| # | Path | Method(s) | Lambda Target |
|---|------|-----------|---------------|
| 1 | `/website_list` | GET | `lenie_2_db` |
| 2 | `/website_get` | GET | `lenie_2_db` |
| 3 | `/website_save` | POST | `lenie_2_db` |
| 4 | `/website_delete` | GET, POST | `lenie_2_db` |
| 5 | `/website_is_paid` | POST | `lenie_2_db` |
| 6 | `/website_get_next_to_correct` | GET | `lenie_2_db` |
| 7 | `/website_similar` | POST | `lenie_2_db` |
| 8 | `/website_split_for_embedding` | POST | `lenie_2_db` |
| 9 | `/website_download_text_content` | POST | `lenie_2_internet` |
| 10 | `/ai_embedding_get` | POST | `lenie_2_internet` |
| 11 | `/url_add` | POST | `${ProjectCode}-${Environment}-url-add` |

Each path also has an OPTIONS method for CORS (not counted as functional endpoints).

**api-gw-infra (`lenie_dev_infra`) — 7 endpoint paths:**

| # | Path | Method | Lambda Target |
|---|------|--------|---------------|
| 1 | `/infra/sqs/size` | GET | `${ProjectCode}-${Environment}-sqs-size` |
| 2 | `/infra/vpn_server/start` | POST | `${ProjectCode}-${Environment}-ec2-start` |
| 3 | `/infra/vpn_server/stop` | POST | `${ProjectCode}-${Environment}-ec2-stop` |
| 4 | `/infra/vpn_server/status` | GET | `${ProjectCode}-${Environment}-ec2-status` |
| 5 | `/infra/database/start` | POST | `${ProjectCode}-${Environment}-rds-start` |
| 6 | `/infra/database/stop` | POST | `${ProjectCode}-${Environment}-rds-stop` |
| 7 | `/infra/database/status` | GET | `${ProjectCode}-${Environment}-rds-status` |

**url-add (`lenie_dev_add_from_chrome_extension`) — 1 endpoint path:**

| # | Path | Method | Lambda Target |
|---|------|--------|---------------|
| 1 | `/url_add` | POST | `${ProjectCode}-${Environment}-url-add` |

### Flask vs AWS Endpoint Differences

**Endpoints only in Flask server.py (no AWS API Gateway equivalent):**
`/` (root), `/website_text_remove_not_needed`, `/healthz`, `/metrics`, `/startup`, `/readiness`, `/liveness`, `/version`

**Endpoints with different implementation in Flask vs AWS:**
`/url_add` — Flask: direct DB write; AWS: SQS+DynamoDB+S3 flow (available via api-gw-app and standalone url-add REST API)

**Endpoints only in AWS (not in Flask):**
All 7 `/infra/*` endpoints (infrastructure management — no equivalent in Docker/K8s deployment)

### Lambda Functions

**Total: 12 Lambda functions in AWS**

**CF-managed via deploy.ini (10 functions):**

| # | Function Name | Template | Type |
|---|--------------|----------|------|
| 1 | `${PC}-${Env}-sqs-size` | `api-gw-infra.yaml` | Inline (simple) |
| 2 | `${PC}-${Env}-rds-start` | `api-gw-infra.yaml` | Inline (simple) |
| 3 | `${PC}-${Env}-rds-stop` | `api-gw-infra.yaml` | Inline (simple) |
| 4 | `${PC}-${Env}-rds-status` | `api-gw-infra.yaml` | Inline (simple) |
| 5 | `${PC}-${Env}-ec2-status` | `api-gw-infra.yaml` | Inline (simple) |
| 6 | `${PC}-${Env}-ec2-start` | `api-gw-infra.yaml` | Inline (simple) |
| 7 | `${PC}-${Env}-ec2-stop` | `api-gw-infra.yaml` | Inline (simple) |
| 8 | `${PC}-${Env}-sqs-to-rds-lambda` | `sqs-to-rds-lambda.yaml` | S3 packaged (app) |
| 9 | `${PC}-${Env}-weblink-put-into-sqs` | `lambda-weblink-put-into-sqs.yaml` | S3 packaged (app) |
| 10 | `${PC}-${Env}-url-add` | `url-add.yaml` | S3 packaged (app) |

**Non-CF-managed (2 functions) — referenced by api-gw-app.yaml:**

| # | Function Name | Purpose |
|---|--------------|---------|
| 11 | `lenie_2_db` | App endpoints requiring PostgreSQL (inside VPC) |
| 12 | `lenie_2_internet` | App endpoints requiring internet (outside VPC) |

`${PC}` = ProjectCode (`lenie`), `${Env}` = Environment (`dev`)

## CloudFormation

**Templates in deploy.ini [dev]: 26**
**Total .yaml files in templates/: 33**

### deploy.ini [dev] — 26 templates by layer

| Layer | Templates | Count |
|-------|-----------|-------|
| 1. Foundation | env-setup, budget, 1-domain-route53 | 3 |
| 2. Networking | vpc, security-groups | 2 |
| 3. Security | secrets | 1 |
| 4. Storage | s3, s3-cloudformation, dynamodb-documents, s3-website-content, s3-app-web, sqs-documents, sqs-application-errors | 7 |
| 5. Compute | lambda-layer-lenie-all, lambda-layer-openai, lambda-layer-psycopg2, ec2-lenie, lenie-launch-template, lambda-weblink-put-into-sqs, sqs-to-rds-lambda, url-add | 8 |
| 6. API | api-gw-infra, api-gw-app | 2 |
| 7. Orchestration | sqs-to-rds-step-function | 1 |
| 8. CDN | cloudfront-app, helm | 2 |
| **Total** | | **26** |

### Templates NOT in deploy.ini (7 files)

| Template | Reason |
|----------|--------|
| `rds.yaml` | Deployed separately, managed lifecycle via Step Functions |
| `lambda-rds-start.yaml` | REDUNDANT — rds-start Lambda now managed by api-gw-infra.yaml |
| `identityStore.yaml` | Organization governance (deployed separately) |
| `organization.yaml` | Organization governance (deployed separately) |
| `scp-block-all.yaml` | Organization SCP (deployed separately) |
| `scp-block-sso-creation.yaml` | Organization SCP (deployed separately) |
| `scp-only-allowed-reginos.yaml` | Organization SCP (deployed separately) |

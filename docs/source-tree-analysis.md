# Source Tree Analysis

> Generated: 2026-02-13 | Project: lenie-server-2025 | Type: Multi-part Monorepo

## Project Root

```
lenie-server-2025/
├── CLAUDE.md                          # Project documentation for Claude Code
├── README.md                          # Project overview
├── Makefile                           # Build automation (local/aws/gcloud targets)
├── .env_example                       # Environment variable template
├── .pre-commit-config.yaml            # Pre-commit hooks (TruffleHog secret detection)
├── .circleci/config.yml               # CircleCI pipeline
├── .gitlab-ci.yml                     # GitLab CI pipeline (Qodana security)
├── Jenkinsfile                        # Jenkins pipeline (AWS EC2, Semgrep)
│
├── backend/                    ★ Flask REST API (Python 3.11)
│   ├── server.py                      # Main Flask application (19 endpoints)
│   ├── pyproject.toml                 # Dependencies & build config (uv)
│   ├── uv.lock                        # Frozen dependency lock
│   ├── Dockerfile                     # Docker build (python:3.11-slim + uv)
│   ├── CLAUDE.md                      # Backend documentation
│   │
│   ├── library/                ★ Core business logic & integrations
│   │   ├── ai.py                      # LLM provider router (OpenAI/Bedrock/Vertex/Sherlock)
│   │   ├── embedding.py               # Embedding provider router
│   │   ├── stalker_web_document.py    # Domain model (base, 30 attrs)
│   │   ├── stalker_web_document_db.py # Domain model + PostgreSQL persistence
│   │   ├── stalker_web_documents_db_postgresql.py  # Query layer (psycopg2)
│   │   ├── text_functions.py          # Text splitting, regex utils
│   │   ├── text_transcript.py         # Transcript/chapter parsing
│   │   ├── lenie_markdown.py          # Markdown processing & splitting
│   │   ├── document_markdown.py       # DocumentMarkDown class
│   │   ├── text_detect_language.py    # Language detection abstraction
│   │   ├── stalker_youtube_file.py    # YouTube metadata & processing
│   │   ├── transcript.py              # Transcription router
│   │   ├── google_auth.py             # Google OAuth 2.0
│   │   │
│   │   ├── models/                    # Data models & enums
│   │   │   ├── ai_response.py         # AiResponse class
│   │   │   ├── embedding_result.py    # EmbeddingResult class
│   │   │   ├── webpage_parse_result.py # WebPageParseResult class
│   │   │   ├── stalker_document_status.py       # 15 processing states enum
│   │   │   ├── stalker_document_status_error.py # 14 error states enum
│   │   │   └── stalker_document_type.py         # 6 document types enum
│   │   │
│   │   ├── api/                       # External service integrations
│   │   │   ├── openai/                # OpenAI (chat + embeddings)
│   │   │   │   ├── openai_my.py       # Chat completions (GPT-3.5/4/4o)
│   │   │   │   └── openai_embedding.py # text-embedding-ada-002
│   │   │   ├── aws/                   # AWS services
│   │   │   │   ├── bedrock_ask.py     # Bedrock LLM (Titan/Nova/Claude)
│   │   │   │   ├── bedrock_embedding.py # Titan embeddings (v1/v2)
│   │   │   │   ├── s3_aws.py          # S3 operations
│   │   │   │   ├── transcript.py      # AWS Transcribe
│   │   │   │   ├── text_detect_language_aws.py # AWS Comprehend
│   │   │   │   └── credentionals.py   # STS credential validation
│   │   │   ├── google/                # Google Cloud
│   │   │   │   └── google_vertexai.py # Gemini 2.0 (Vertex AI)
│   │   │   ├── cloudferro/sherlock/   # CloudFerro (Polish LLM)
│   │   │   │   ├── sherlock.py        # Bielik-11B chat
│   │   │   │   └── sherlock_embedding.py # BAAI/bge embeddings
│   │   │   └── asemblyai/            # Speech-to-text
│   │   │       └── asemblyai_transcript.py # AssemblyAI ($0.12/hr)
│   │   │
│   │   └── website/                   # Website processing
│   │       ├── website_download_context.py # HTML download & parsing
│   │       ├── website_paid.py        # Paywall detection
│   │       └── website_text_clean_regexp.py # Site-specific regex cleanup
│   │
│   ├── database/               ★ PostgreSQL schema & initialization
│   │   └── init/                      # SQL init scripts (pgvector, tables, indexes)
│   │
│   ├── tests/                  ★ Test suite (pytest)
│   │   ├── unit/                      # 9 unit tests (markdown, text, paywall)
│   │   └── integration/               # 5 integration tests (API endpoints)
│   │
│   ├── data/                          # Site-specific cleanup rules (JSON regex)
│   ├── imports/                       # Bulk import scripts
│   ├── test_code/                     # Experimental/prototype scripts
│   │
│   ├── web_documents_do_the_needful_new.py  # Batch: full pipeline
│   ├── webdocument_md_decode.py       # Batch: markdown processing
│   ├── webdocument_prepare_regexp_by_ai.py  # Batch: AI regex generation
│   ├── markdown_to_embedding.py       # Batch: markdown → embeddings
│   └── youtube_add.py                 # CLI: YouTube video processing
│
├── web_interface_react/        ★ Main React Frontend (7 pages)
│   ├── src/
│   │   ├── index.js                   # Entry: AuthorizationProvider + Router
│   │   ├── App.js                     # Route definitions
│   │   └── modules/shared/
│   │       ├── context/
│   │       │   └── authorizationContext.js  # Global state
│   │       ├── hooks/                 # 7 custom hooks (CRUD, AI, infra)
│   │       ├── components/            # 6 reusable components
│   │       ├── pages/                 # 7 page components
│   │       ├── constants/             # App version, LLM config
│   │       └── styles/                # Global CSS
│   ├── Dockerfile                     # Docker build (node:24.0)
│   └── package.json                   # React 18, axios, formik, router
│
├── web_chrome_extension/       ★ Browser Extension (Manifest v3)
│   ├── manifest.json                  # Chrome Extension v3 manifest
│   ├── popup.html                     # Two-tab UI (Add + Settings)
│   ├── popup.js                       # All logic (~183 lines)
│   ├── bootstrap.min.css              # Local Bootstrap
│   └── CHANGELOG.md                   # Version history (v1.0.22)
│
├── infra/                      ★ Infrastructure as Code
│   ├── docker/
│   │   ├── compose.yaml               # 3-service stack (Flask, PostgreSQL, React)
│   │   ├── .env                       # Docker environment
│   │   └── Postgresql/Dockerfile      # Custom pgvector image
│   │
│   ├── aws/
│   │   ├── cloudformation/            # 29 CloudFormation templates
│   │   │   ├── deploy.sh              # Universal deployment script
│   │   │   ├── deploy.ini             # Stack configuration
│   │   │   ├── templates/             # YAML templates (VPC, RDS, Lambda, API GW, etc.)
│   │   │   └── parameters/            # Per-environment parameters
│   │   ├── serverless/                # Lambda functions
│   │   │   ├── lambdas/
│   │   │   │   ├── app-server-db/     # DB endpoints (VPC)
│   │   │   │   ├── app-server-internet/ # Internet endpoints
│   │   │   │   ├── sqs-weblink-put-into/ # URL ingestion
│   │   │   │   ├── rds-start/stop/status/ # RDS lifecycle
│   │   │   │   ├── ec2-start/stop/status/ # EC2 lifecycle
│   │   │   │   └── sqs-size/          # Queue monitoring
│   │   │   └── lambda_layers/         # psycopg2, lenie_all, openai
│   │   ├── eks/                       # EKS documentation
│   │   ├── terraform/                 # Terraform IaC (alternative)
│   │   └── tools/
│   │       └── aws_ec2_route53.py     # EC2 start + DNS update
│   │
│   ├── kubernetes/
│   │   ├── kustomize/                 # Base + overlays (GKE dev, docker-desktop)
│   │   └── helm/                      # Helm chart (v0.2.14)
│   │
│   └── gcloud/
│       ├── terraform-server/          # GCP Terraform (Cloud Run, DNS)
│       └── cloud-run-shell/           # Cloud Run container
│
└── docs/                       ★ Documentation (this directory)
    ├── API_Usage.md
    ├── CI_CD.md, CI_CD_Tools.md
    ├── CircleCI.md, GitLabCI.md, Jenkins.md
    ├── AWS_Infrastructure.md, AWS_Amplify_Deployment.md
    ├── Docker_Local.md, Code_Quality.md
    └── Python_Dependencies.md
```

## Critical Folders

| Folder | Purpose | Entry Points |
|--------|---------|-------------|
| `backend/` | Flask API server | `server.py` |
| `backend/library/` | Core business logic, LLM/embedding abstraction | `ai.py`, `embedding.py` |
| `backend/library/api/` | External service integrations | Provider-specific modules |
| `backend/library/models/` | Domain models and enums | `stalker_document_status.py` |
| `backend/database/init/` | PostgreSQL schema initialization | SQL scripts |
| `web_interface_react/src/` | Main frontend source | `index.js` → `App.js` |
| `web_interface_react/src/modules/shared/hooks/` | API communication layer | `useManageLLM.js` |
| `web_chrome_extension/` | Browser extension | `popup.js` |
| `infra/docker/` | Local development stack | `compose.yaml` |
| `infra/aws/cloudformation/` | AWS infrastructure templates | `deploy.sh` |
| `infra/aws/serverless/lambdas/` | AWS Lambda functions | `lambda_function.py` per function |
| `infra/kubernetes/kustomize/` | K8s deployment | `base/kustomization.yaml` |

## Integration Points

```
web_interface_react ──(REST API, axios)──→ backend/server.py (19 endpoints)
web_chrome_extension ──(POST /url_add)──→ AWS API Gateway → sqs-weblink-put-into Lambda
infra/docker ──(deploys)──→ backend + web_interface_react + PostgreSQL
infra/aws/cloudformation ──(provisions)──→ VPC, RDS, Lambda, API Gateway, SQS, DynamoDB
infra/kubernetes ──(deploys)──→ backend + web_interface_react + PostgreSQL on GKE
```

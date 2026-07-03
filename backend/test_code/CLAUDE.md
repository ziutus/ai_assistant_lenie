# Test Code — CLAUDE.md

Experimental and exploratory scripts that test backend library modules, external API integrations, and prototype features before they are integrated into the main service. These are **developer tools**, not production code.

## Directory Structure

```
backend/test_code/
├── cloudferro_ark_labs_models.py     # CloudFerro & ARK Labs model listing
├── credentials.json                  # Google OAuth app credentials
├── dateparser_user.py                # Date parsing library tests
├── describe_image.py                 # Image analysis via AWS Bedrock Claude
├── embeddings_search.py              # Full RAG pipeline (CLI tool)
├── firecrawl.py                      # Web crawling via Firecrawl (incomplete)
├── gcloud_firestore.py               # DynamoDB → Firestore migration
├── gcloud_firestore_example.py       # Basic Firestore CRUD example
├── google_calendar_to_obsidian.py    # Google Calendar → Obsidian sync
├── obsidian_clean_jurnal.py          # Obsidian journal cleanup & Storytel metadata
├── openroute.py                      # OpenRouter API testing
├── read_pdf.py                       # PDF text extraction via pypdf
├── serper_dev.py                     # Web search via Serper API
├── token.json                        # Google OAuth token (auto-generated)
├── vault_tests.py                    # HashiCorp Vault integration tests
└── tmp/                              # Temporary data files (git-ignored)
    └── storytel_*.{html,json,md}     # Storytel audiobook metadata samples
```

## Script Categories

### Vector Search & RAG

| Script | Purpose |
|--------|---------|
| `embeddings_search.py` | Full RAG pipeline: language detection → translation → embedding → pgvector similarity search → LLM answer with sources. CLI with flags: `--question`, `--minimal_similarity`, `-model`, `-nc`, `-en`, `-pl` |

### LLM Provider Testing

| Script | Purpose |
|--------|---------|
| `cloudferro_ark_labs_models.py` | List models from CloudFerro Sherlock & ARK Labs APIs |
| `model_identity_comparison.py` | Ask multiple models N times "what's your name and who made you?" — compares consistency of responses across western and Chinese models (OpenRouter, OpenAI, Bedrock, CloudFerro). Outputs JSON/CSV/TXT summaries. |
| `openroute.py` | Test OpenRouter API (Claude Sonnet 4 models) |
| `describe_image.py` | Image analysis using AWS Bedrock Claude 3 Haiku |

### Cloud Platform Integration

| Script | Purpose |
|--------|---------|
| `gcloud_firestore.py` | Migrate articles from DynamoDB to Google Firestore (batch operations, retry logic, cost monitoring) |
| `gcloud_firestore_example.py` | Basic Firestore CRUD operations with dateparser |

### Content Processing & Utilities

| Script | Purpose |
|--------|---------|
| `read_pdf.py` | Extract text from PDF files using `pypdf` |
| `firecrawl.py` | Multi-page web crawling via Firecrawl library (incomplete) |
| `serper_dev.py` | Web search via Serper (Google Search) API with MD5-based caching |
| `dateparser_user.py` | Tests `dateparser` library with mixed Polish/English date formats |
| `vault_tests.py` | HashiCorp Vault: AppRole auth, secret retrieval, health checks |

### Personal Productivity

| Script | Purpose |
|--------|---------|
| `google_calendar_to_obsidian.py` | Sync Google Calendar events to Obsidian journal files (OAuth 2.0, multi-calendar, Markdown formatting). Flags: `--auto`, `--dry-run` |
| `obsidian_clean_jurnal.py` | Download Storytel audiobook metadata via Playwright/requests, clean UTM params, rename journal files with weekday names |

## Relationship to Main Backend

These scripts directly import and test production `library/` modules:

- **`library.ai`** — LLM provider abstraction (used by `embeddings_search.py`, Bielik scripts)
- **`library.embedding`** — Vector embedding generation
- **`library.stalker_web_documents_db_postgresql`** — PostgreSQL + pgvector queries
- **`library.stalker_cache`** — Query result caching
- **`library.text_detect_language`** — Language detection

Code proven here is progressively promoted into the main `server.py` endpoints or `backend/library/` modules.

## Common Patterns

- **Environment**: All scripts use `dotenv.load_dotenv()` for `.env`-based configuration
- **Auth**: Multiple methods — API keys, OAuth 2.0 (Google), Bearer tokens, AppRole (Vault)
- **Dry run**: Several scripts support `--dry-run` or `dry_run=True` for safe preview
- **CLI**: `argparse` used for configurable scripts (`embeddings_search.py`, `google_calendar_to_obsidian.py`)
- **Error handling**: Retry logic with auto re-authentication on token expiry (`gcloud_firestore.py`)

## Running Scripts

```bash
# From the backend/ directory (requires .env file)
cd backend
python test_code/embeddings_search.py --question "What is RAG?" --minimal_similarity 0.7
python test_code/read_pdf.py
python test_code/vault_tests.py
```

Scripts require the same `.env` configuration as the main backend (see root `CLAUDE.md` for environment variables).

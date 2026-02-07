# Tests — CLAUDE.md

Pytest test suite for the backend. Split into **unit tests** (pure function testing, no external dependencies) and **integration tests** (REST API endpoints via Flask test client, requires running PostgreSQL database).

## Directory Structure

```
backend/tests/
├── unit/
│   ├── test_md_extract_links.py              # Markdown link extraction
│   ├── test_md_image_as_link.py              # Image-as-link extraction
│   ├── test_md_images_with_links.py          # Image metadata extraction
│   ├── test_md_link_inside.py                # Fix links split across lines
│   ├── test_md_remove_new_line.py            # Newline removal in strings
│   ├── test_md_squre_brackets_in_one_line.py # Join bracket text across lines
│   ├── test_split_for_embedding.py           # Text chunking for embeddings
│   ├── test_text_transcript.py               # Transcript timestamp parsing
│   └── test_website_paid.py                  # Paywall detection
│
└── integration/
    ├── test_page_exist.py                    # POST /website_exist
    ├── test_website_crud.py                  # Full CRUD cycle (save/get/update/delete)
    ├── test_website_get.py                   # GET /website_get with error cases
    ├── test_website_get_list.py              # GET /website_list
    └── test_website_is_paid.py               # POST /website_is_paid
```

## Running Tests

```bash
# All tests with HTML report
pytest --self-contained-html --html=pytest-results/

# Unit tests only (no external dependencies)
pytest backend/tests/unit/

# Integration tests (requires PostgreSQL + .env)
pytest backend/tests/integration/

# Single test file
pytest backend/tests/unit/test_split_for_embedding.py
```

Configuration in `backend/pyproject.toml` under `[tool.pytest.ini_options]`.

## Unit Tests

All unit tests inherit from `unittest.TestCase` and test pure library functions with no mocking or database access.

### Markdown Processing (6 files)

Tests for `library.lenie_markdown` module — the largest tested area:

| File | Function Tested | Description |
|------|----------------|-------------|
| `test_md_extract_links.py` | `process_markdown_and_extract_links()` | Extract URLs from markdown content |
| `test_md_image_as_link.py` | `md_get_images_as_links()` | Extract images encoded as `[![](...)](#)` |
| `test_md_images_with_links.py` | `get_images_with_links_md()` | Extract image alt text, description, owner, URL |
| `test_md_link_inside.py` | `links_correct()` | Join URLs split across lines (`google.\ncom` → `google.com`) |
| `test_md_remove_new_line.py` | `remove_new_line_only_in_string()` | Remove line breaks only within matched strings |
| `test_md_squre_brackets_in_one_line.py` | `md_square_brackets_in_one_line()` | Join `[text\nsplit]` → `[text split]` (6 test cases) |

### Text Processing (2 files)

| File | Function Tested | Description |
|------|----------------|-------------|
| `test_split_for_embedding.py` | `library.text_functions.split_text_for_embedding()` | Split long text into chunks for AI embedding generation |
| `test_text_transcript.py` | `library.text_transcript.split_text_and_time()` | Parse `HH:MM[:SS]` timestamps from transcripts (6 test cases, pytest-style assertions) |

### Website Classification (1 file)

| File | Function Tested | Description |
|------|----------------|-------------|
| `test_website_paid.py` | `library.website.website_paid.website_is_paid()` | Detect paywalled sites (wyborcza.pl → True, testfree.com → False) |

## Integration Tests

All integration tests use Flask `app.test_client()` from `server.py`. They test REST API endpoints end-to-end and **require a running PostgreSQL database**.

| File | Endpoints Tested | Description |
|------|-----------------|-------------|
| `test_page_exist.py` | `POST /website_exist` | Check if URL exists in DB (JSON body, form data, missing data error) |
| `test_website_crud.py` | `POST /save_website`, `GET /website_get`, `GET /website_delete` | Full lifecycle: create → retrieve → update → verify → delete |
| `test_website_get.py` | `GET /website_get` | Retrieve by ID with error handling (missing ID → 400, non-existent → 404) |
| `test_website_get_list.py` | `GET /website_list` | List all websites, validates response structure |
| `test_website_is_paid.py` | `POST /website_is_paid` | Paywall check via API (google.com → `is_paid: false`) |

## Test Conventions

- **Framework**: `unittest.TestCase` base class, run via `pytest`
- **Assertions**: Mostly `self.assertEqual`/`self.assertTrue` (unittest style); `test_text_transcript.py` uses bare `assert` (pytest style)
- **Test data**: Real Polish URLs and content (interia.pl, onet.pl, wyborcza.pl)
- **No mocking**: Tests use real library functions and Flask test client
- **No conftest.py**: No shared fixtures or parametrization
- **No teardown**: CRUD test creates unique URLs via UUID to avoid conflicts

## Modules Under Test

| Module | Source File | Test Coverage |
|--------|-----------|---------------|
| `library.lenie_markdown` | `backend/library/lenie_markdown.py` | 6 unit test files |
| `library.text_functions` | `backend/library/text_functions.py` | 1 unit test file |
| `library.text_transcript` | `backend/library/text_transcript.py` | 1 unit test file |
| `library.website.website_paid` | `backend/library/website/website_paid.py` | 1 unit + 1 integration |
| Flask REST API | `backend/server.py` | 5 integration test files |

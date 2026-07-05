# Tests — CLAUDE.md

Pytest test suite for the backend. Split into **unit tests** (41 files, ~690 tests — pure functions, ORM models with no DB connection, Flask endpoints with mocked sessions) and **integration tests** (6 files — REST API endpoints via Flask test client, require a running PostgreSQL database).

## Two Test Environments

Unit tests are designed to run in two environments:

```bash
# Lightweight (uvx) — no project dependencies installed.
# Modules that need sqlalchemy/flask/boto3 skip themselves; pure-function tests run.
cd backend && PYTHONPATH=. uvx pytest tests/unit/ -q
# → ~169 passed, ~29 skipped

# Full venv — everything runs (~690 tests).
cd backend && .venv/Scripts/python -m pytest tests/unit/ -q
```

Integration tests additionally require PostgreSQL and a `.env` file:

```bash
cd backend && .venv/Scripts/python -m pytest tests/integration/ -q
```

Configuration in `backend/pyproject.toml` under `[tool.pytest.ini_options]`. There is **no conftest.py** — run from `backend/` with `PYTHONPATH=.` (some tests open script sources via paths relative to the test file or to cwd).

## Unit Test Areas

### ORM & Database Layer
| File | Covers |
|------|--------|
| `test_db_engine.py` | Engine singleton, session factories, `Base` |
| `test_db_models.py` | `WebDocument` columns (30), STI subclasses (7), `dict()` output (33 keys), lookup models |
| `test_orm_crud.py` | `WebDocument` CRUD, `dict()` compatibility |
| `test_repository_queries.py` | `WebsitesDBPostgreSQL` repository queries |
| `test_get_list_query.py` | `get_list()` ORM query construction |
| `test_embedding_crud_orm.py` | Embedding add/delete via ORM |
| `test_similarity_search_orm.py` | `get_similar()` pgvector ORM path |
| `test_sql_parameterization.py` | SQL parameterization (no string interpolation) |
| `test_import_log_tracker.py` | `ImportLog` model + `ImportLogTracker` context manager |
| `test_alembic_setup.py` | Alembic configuration, Flask session teardown |

### Services & Flask Endpoints (mocked sessions)
| File | Covers |
|------|--------|
| `test_document_service.py` | `DocumentService` (create/import document) |
| `test_search_service.py` | `SearchService` (embeddings, similarity) |
| `test_flask_endpoints_orm.py` | ORM-backed endpoints; error responses use generic messages (details logged, not leaked) |
| `test_flask_endpoints_document_states.py` | `GET /document_states` |
| `test_website_get_validation.py` | `/website_get` input validation |
| `test_metrics_endpoint.py` | `/metrics` |
| `test_ai_intent_parser.py` | AI intent parser |
| `test_config_loader.py` | Config loader re-export (`unified_config_loader`) |

### Batch & Import Scripts
| File | Covers |
|------|--------|
| `test_batch_pipeline_orm.py` | `web_documents_do_the_needful_new.py` — AST/source checks (ORM imports, no legacy calls); `youtube_add.py` source checks |
| `test_dynamodb_sync_orm.py` / `test_dynamodb_sync_auto_since.py` | `dynamodb_sync.py` ORM usage; `--since` auto-detection (incl. `--dry-run` needs no DB) |
| `test_unknown_news_import_orm.py` | Feed entry import logic (now in `feed_monitor.py`) |
| `test_youtube_processing_orm.py` | `youtube_processing.py` ORM migration |
| `test_feed_monitor_utils.py` | Pure helpers: `parse_date`, `strip_html`, `_parse_selection`, `apply_skip_filters`, `detect_document_type`, `build_feed_url` |
| `test_article_browser_utils.py` | Pure helpers: `_trim_to_sentences`, `_article_full_text` |
| `test_control_questions.py` | `parse_sections`, `sections_for_tags`, tag-needle invariants |
| `test_md_decode_onet.py` | `clean_onet_artifacts()` from `webdocument_md_decode.py` |

### Article Processing (`library/`)
| File | Covers |
|------|--------|
| `test_article_cleaner.py` | `clean_article_text()` — portal artifact cleanup, `[imgN]`/`[linkN]` markers |
| `test_article_pipeline.py` | `ensure_raw_markdown()` + `extract_article()` (cache/S3/LLM pipeline, no I/O) |
| `test_article_tagging.py` | LLM thematic tagging & country extraction |
| `test_article_review_tracking.py` | `reviewed_at` / `obsidian_note_paths` tracking |

### Markdown & Text Processing (legacy, `unittest.TestCase` style)
| File | Function Tested |
|------|----------------|
| `test_md_extract_links.py` | `process_markdown_and_extract_links()` |
| `test_md_image_as_link.py` | `md_get_images_as_links()` |
| `test_md_images_with_links.py` | `get_images_with_links_md()` |
| `test_md_link_inside.py` | `links_correct()` |
| `test_md_remove_new_line.py` | `remove_new_line_only_in_string()` |
| `test_md_squre_brackets_in_one_line.py` | `md_square_brackets_in_one_line()` |
| `test_split_for_embedding.py` | `split_text_for_embedding()` |
| `test_text_transcript.py` | `split_text_and_time()` |
| `test_website_paid.py` | `website_is_paid()` |
| `test_transcript_prices.py` / `test_transcription_usage.py` | AssemblyAI price mapping, usage aggregation |

## Integration Tests

All use Flask `app.test_client()` from `server.py` and **require PostgreSQL**.

| File | Endpoints / Area |
|------|-----------------|
| `test_page_exist.py` | `POST /website_exist` |
| `test_website_crud.py` | Full lifecycle: create → retrieve → update → delete |
| `test_website_get.py` | `GET /website_get` with error cases |
| `test_website_get_list.py` | `GET /website_list` |
| `test_website_is_paid.py` | `POST /website_is_paid` |
| `test_fk_constraints.py` | FK constraint validation on lookup tables |

## Test Conventions

- **New tests**: pytest style — plain classes, bare `assert`, fixtures, `monkeypatch`, `parametrize`. **Legacy tests** (markdown/text group): `unittest.TestCase`.
- **Heavy third-party deps** (`sqlalchemy`, `flask`): test modules guard with `pytest.importorskip("sqlalchemy")` at the top — in the lightweight uvx environment the whole module skips cleanly.
- **Modules under test with heavy module-level imports** (`feed_monitor`, `article_browser`, `webdocument_md_decode`): tests install minimal stubs in `sys.modules` *only for the import of the module under test*, then remove them so the `importorskip` pattern in other modules keeps working. See the docstring in `test_feed_monitor_utils.py` for the `_ensure_importable` / `_remove_stubs` helpers.
- **Lazy-imported dependencies** (e.g. `library.document_prepare` in `article_pipeline`): faked via `monkeypatch.setitem(sys.modules, ...)` per test — the real module (which pulls the optional `markitdown` extra) is never imported. See `test_article_pipeline.py`.
- **Source-check tests**: `test_batch_pipeline_orm.py` parses script sources with `ast` to enforce ORM-only imports; script paths are resolved relative to the test file or assume cwd=`backend/`.
- **No DB in unit tests**: ORM tests use model metadata and mocked sessions only.
- Do not put stubs permanently into `sys.modules` at test-module level — it breaks `importorskip` detection in other files collected in the same session.

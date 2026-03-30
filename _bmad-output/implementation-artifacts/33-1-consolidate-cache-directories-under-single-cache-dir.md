# Story 33.1: Consolidate Cache Directories Under Single CACHE_DIR

Status: done

## Story

As a **developer**,
I want all processing scripts to use a single, configurable cache directory with well-defined subdirectories,
so that cached files are easy to find, manage, and clean up.

## Acceptance Criteria

1. **AC-1: Unified CACHE_DIR root** — All scripts use `cfg.get("CACHE_DIR") or "tmp"` as the root cache directory. The default changes from `"tmp/markdown"` to `"tmp"`.

2. **AC-2: Subdirectory structure** — Cache is organized as:
   ```
   {CACHE_DIR}/
   ├── markdown/{doc_id}/          # HTML->markdown processing
   ├── youtube_to_text/{doc_id}/   # YouTube transcript processing
   └── article_notes/{doc_id}/     # article_browser.py personal notes
   ```

3. **AC-3: No hardcoded paths** — All scripts resolve cache root via `cfg.get("CACHE_DIR") or "tmp"`. No `f"tmp/..."`, `"cache"`, or `"tmp/markdown_output"` literals remain.

4. **AC-4: dynamodb_sync.py --data-dir default** — Default changes from `"tmp/markdown"` to `os.path.join(CACHE_DIR, "markdown")`.

5. **AC-5: youtube_processing.py uses cfg.get()** — Replace `os.getenv("CACHE_DIR", "cache")` with `cfg.get("CACHE_DIR") or "tmp"`, subdirectory `youtube_to_text/`.

6. **AC-6: Old directories cleaned** — `backend/cache/` removed (empty). `backend/imports/tmp/` and `backend/test_code/tmp/` contents migrated or confirmed empty. `.gitignore` covers `backend/tmp/`.

7. **AC-7: os.path.join() everywhere** — All path construction uses `os.path.join()`, no f-string path concatenation (`f"{dir}/{file}"`).

## Tasks / Subtasks

- [x] Task 1: Define CACHE_DIR constant pattern (AC: 1, 2)
  - [x] 1.1 Update `dynamodb_sync.py` — change default from `"tmp/markdown"` to `os.path.join(cfg.get("CACHE_DIR") or "tmp", "markdown")` (line 239)
  - [x] 1.2 Update `article_browser.py` — change `cfg.get("CACHE_DIR") or "tmp/markdown"` to `os.path.join(cfg.get("CACHE_DIR") or "tmp", "markdown")` at lines 381, 730, 907
  - [x] 1.3 Update `webdocument_prepare_regexp_by_ai.py` — same pattern change (line 49)
  - [x] 1.4 Update `webdocument_md_decode.py` — same pattern change (line 97), also fix f-string concat at line 230 to `os.path.join()`
  - [x] 1.5 Update `migrate_data_to_cache.py` — same pattern change (line 45)

- [x] Task 2: Fix hardcoded paths (AC: 3, 5)
  - [x] 2.1 Fix `web_documents_do_the_needful_new.py` — replace hardcoded `f"tmp/{s3_uuid}.html"` (lines 306, 314, 318, 560, 568, 572) with `os.path.join(cache_dir, str(s3_uuid), f"{s3_uuid}.html")`. Also fix lines 86-87: add `or "tmp"` default when `cfg.get('CACHE_DIR')` is None.
  - [x] 2.2 Fix `youtube_processing.py` — replace `os.getenv("CACHE_DIR", "cache")` (line 66) with `cfg.get("CACHE_DIR") or "tmp"`, use subdirectory `youtube_to_text/`
  - [x] 2.3 Fix `markdown_to_embedding.py` — replace hardcoded `"tmp/markdown_output"` (line 18) with `os.path.join(cfg.get("CACHE_DIR") or "tmp", "markdown")`. Add `from library.config_loader import load_config` and `cfg = load_config()`.
  - [x] 2.4 Fix `obsidian_clean_jurnal.py` — replace `TMP_DIR = "tmp"` (line 24) with `cfg.get("CACHE_DIR") or "tmp"` (test_code, lower priority)

- [x] Task 3: Fix path construction (AC: 7)
  - [x] 3.1 Fix `webdocument_md_decode.py` line 230: replace `f"{cache_dir_base}/{document_id}"` with `os.path.join(cache_dir_base, str(document_id))`
  - [x] 3.2 Fix `markdown_to_embedding.py` line 21: replace `f"{cache_directory}/{document_id}.json"` with `os.path.join(cache_directory, f"{document_id}.json")`
  - [x] 3.3 Audit all changed files for remaining f-string path patterns

- [x] Task 4: Cleanup old directories (AC: 6)
  - [x] 4.1 Remove empty `backend/cache/` directory
  - [x] 4.2 Verify `backend/imports/tmp/` — migrate any content to `backend/tmp/youtube_to_text/` if applicable
  - [x] 4.3 Verify `backend/test_code/tmp/` — keep if test fixtures, or migrate
  - [x] 4.4 Confirm `.gitignore` covers `backend/tmp/` (already does via `*/tmp/`)

- [x] Task 5: Verification (AC: all)
  - [x] 5.1 Grep for remaining hardcoded `"tmp/"`, `"cache/"`, `"tmp/markdown"` literals in `backend/`
  - [x] 5.2 Grep for `os.getenv("CACHE_DIR")` to ensure all migrated to `cfg.get()`
  - [x] 5.3 Run `ruff check backend/` — no new lint errors introduced
  - [x] 5.4 Run `pytest backend/tests/unit/` — all 70 tests pass (22 skipped)

## Dev Notes

### Current State Analysis

**Already using `cfg.get("CACHE_DIR")`** (need default change only):
| File | Line | Current Default |
|------|------|----------------|
| `dynamodb_sync.py` | 239 | `or "tmp/markdown"` |
| `webdocument_prepare_regexp_by_ai.py` | 49 | `or "tmp/markdown"` |
| `webdocument_md_decode.py` | 97 | `or "tmp/markdown"` |
| `article_browser.py` | 381, 730, 907 | `or "tmp/markdown"` |
| `migrate_data_to_cache.py` | 45 | `or "tmp/markdown"` |

**Needs full migration:**
| File | Issue |
|------|-------|
| `web_documents_do_the_needful_new.py` | Hardcoded `f"tmp/{s3_uuid}.html"` at lines 306/314/318/560/568/572. Lines 86-87 check `cfg.get('CACHE_DIR')` but crash if None. |
| `youtube_processing.py` | Uses `os.getenv("CACHE_DIR", "cache")` (line 66) instead of `cfg.get()`. Default is `"cache"` not `"tmp"`. |
| `markdown_to_embedding.py` | Hardcoded `"tmp/markdown_output"` (line 18). No config_loader import. |
| `obsidian_clean_jurnal.py` | Hardcoded `TMP_DIR = "tmp"` (line 24). Test code, lower priority. |

### Critical Patterns to Follow

**Config access pattern (correct):**
```python
from library.config_loader import load_config
cfg = load_config()
cache_dir_root = cfg.get("CACHE_DIR") or "tmp"
cache_dir_markdown = os.path.join(cache_dir_root, "markdown")
```

**Per-document cache dir pattern (established by document_prepare.py):**
```python
doc_cache_dir = os.path.join(cache_dir_markdown, str(document_id))
os.makedirs(doc_cache_dir, exist_ok=True)
html_path = os.path.join(doc_cache_dir, f"{document_id}.html")
```

**Library functions receive cache_dir as parameter** — do NOT modify `document_prepare.py` or `article_extractor.py`. Only modify the callers that compute and pass the cache_dir value.

### Recent Context: Commit f7b2383

The most recent commit (`feat: unify S3 cache directory with document_prepare convention`) already:
- Refactored `dynamodb_sync.py` to save S3 files to `{CACHE_DIR}/{doc_id}/{doc_id}.html`
- Created `migrate_data_to_cache.py` utility for migrating old `data/` files
- Established the `{cache_dir}/{doc_id}/{doc_id}.ext` naming convention

This story **continues** that effort by extending the pattern to all remaining scripts.

### Out of Scope

- `infra/aws/serverless/lambdas/tmp/` and `infra/aws/serverless/lambda_layers/tmp/` — build artifacts, different purpose
- Library modules (`document_prepare.py`, `article_extractor.py`) — already receive `cache_dir` as parameter, no changes needed
- `stalker_youtube_file.py` — already receives `cache_directory` as parameter from callers

### Project Structure Notes

- All import scripts are in `backend/imports/`
- Batch processing scripts are in `backend/` root (e.g., `web_documents_do_the_needful_new.py`)
- Test code is in `backend/test_code/` (experimental, lower priority)
- Config loaded via `library.config_loader` → re-export of `unified_config_loader`

### References

- [Source: _bmad-output/planning-artifacts/epics/epic-33.md#Story 33.1]
- [Source: commit f7b2383 — feat: unify S3 cache directory with document_prepare convention]
- [Source: backend/library/document_prepare.py — established cache_dir parameter pattern]
- [Source: backend/library/config_loader.py — cfg.get()/cfg.require() API]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6 (1M context)

### Debug Log References
None — implementation was straightforward with no issues.

### Completion Notes List
- **Task 1**: Changed default from `"tmp/markdown"` to `os.path.join(cfg.get("CACHE_DIR") or "tmp", "markdown")` in 5 files: dynamodb_sync.py, article_browser.py (3 locations), webdocument_prepare_regexp_by_ai.py, webdocument_md_decode.py, migrate_data_to_cache.py.
- **Task 2**: Fixed hardcoded paths — web_documents_do_the_needful_new.py (added `or "tmp"` fallback, replaced 6 hardcoded `f"tmp/..."` with `os.path.join(cache_dir, ...)`), youtube_processing.py (replaced `os.getenv` with `cfg.get()`, added `youtube_to_text/` subdirectory), markdown_to_embedding.py (added config_loader import, replaced `"tmp/markdown_output"` with config-based path), obsidian_clean_jurnal.py (replaced hardcoded `"tmp"` with `cfg.get("CACHE_DIR") or "tmp"`).
- **Task 3**: Replaced all f-string path concatenation with `os.path.join()` — webdocument_md_decode.py (10 locations: cache_dir construction + 9 file paths), markdown_to_embedding.py (4 locations), web_documents_fix_missing_markdown.py (2 locations, bonus fix not in original story).
- **Task 4**: Removed empty `backend/cache/` directory. Verified `backend/imports/tmp/youtube_to_text/` aligns with new convention. Verified `backend/test_code/tmp/` contains storytel test fixtures (kept). Confirmed `.gitignore` covers via `*/tmp/` pattern.
- **Task 5**: Verification passed — zero `"tmp/markdown"` literals remaining, zero `os.getenv("CACHE_DIR")` remaining, ruff check shows no new errors (all pre-existing), pytest 70 passed / 22 skipped / 0 failed.

### Change Log
- 2026-03-28: Implemented story 33-1 — consolidated all cache directory usage under single CACHE_DIR with `os.path.join()` path construction.
- 2026-03-29: Code review fixes — added missing `markdown/` subdirectory in `web_documents_do_the_needful_new.py` and `web_documents_fix_missing_markdown.py`, fixed YouTube cache_dir parameter, updated help text in dynamodb_sync.py and migrate_data_to_cache.py, updated backend/CLAUDE.md.

### File List
- `backend/imports/dynamodb_sync.py` — changed CACHE_DIR default, updated help text
- `backend/imports/article_browser.py` — changed CACHE_DIR default (3 locations)
- `backend/imports/migrate_data_to_cache.py` — changed CACHE_DIR default, updated help text and docstring
- `backend/webdocument_prepare_regexp_by_ai.py` — changed CACHE_DIR default
- `backend/webdocument_md_decode.py` — changed CACHE_DIR default + replaced 10 f-string path concats with os.path.join()
- `backend/web_documents_do_the_needful_new.py` — added `or "tmp"` fallback, replaced 6 hardcoded paths, added `markdown/` subdirectory, fixed YouTube cache_dir to include `youtube_to_text/`
- `backend/library/youtube_processing.py` — replaced os.getenv with cfg.get(), added youtube_to_text/ subdirectory
- `backend/markdown_to_embedding.py` — added config_loader, replaced hardcoded path + 4 f-string concats
- `backend/test_code/obsidian_clean_jurnal.py` — replaced hardcoded TMP_DIR with cfg.get()
- `backend/web_documents_fix_missing_markdown.py` — replaced hardcoded paths, added `markdown/` subdirectory (bonus fix)
- `backend/cache/` �� removed (empty directory)
- `backend/CLAUDE.md` — updated markdown_to_embedding.py cache path description
- `backend/imports/CLAUDE.md` — updated --data-dir help text
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — status: in-progress → review
- `_bmad-output/implementation-artifacts/33-1-consolidate-cache-directories-under-single-cache-dir.md` — story file updated

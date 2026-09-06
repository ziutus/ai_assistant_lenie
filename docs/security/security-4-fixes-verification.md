# Security fixes: verification on 2026-09-06

Branch: `fix/security-4-issues`; unchanged HEAD: `5bb7267e1fdf615b10b5bf94d980ed3cdc98bf5f`.
Changes remain uncommitted. No push or PR. `_bmad/bmm/config.yaml` was not modified.

## 1. Document deletion requires a write-capable key

- `backend/server.py:2927-2951`: DELETE replaces GET at `/website_delete`; query ID takes precedence over JSON ID. IDs must be positive PostgreSQL integers; invalid input returns 400 before constructing the service. Missing documents retain the existing idempotent 200 response and explicitly roll back the read transaction. Database exceptions roll back and return the existing generic 500.
- Real auth middleware now rejects read_only DELETE with 403 and missing keys with 401; user/service DELETE succeeds. Authenticated GET and HEAD return 405.
- `backend/server.py:2962`: the scan also found HEAD falling through the email footer rule's GET branch into POST-style writes. HEAD now shares the read branch. This is the trivial same-class method-dispatch fix authorized by the task.
- Clients: `web_interface_react/src/modules/shared/hooks/useManageLLM.ts:471,567` now use `axios.delete`, retaining query parameters and API-key headers. Repository search found no delete caller in `web_chrome_extension/` or `web_interface_app2/`.
- Tests: `backend/tests/unit/test_flask_endpoints_orm.py:390-484,520-530`; `backend/tests/integration/test_website_crud.py:62`.
- Compatibility: external callers must migrate to DELETE. No other real domain-data mutation was found in the scanned server.py GET/HEAD handlers. Auth's existing last_used_at telemetry is unchanged.

## 2. Feed fetches validate and pin public destinations

- New `backend/library/safe_http.py:1-124`: HTTP/HTTPS only; reject credentials, malformed URLs, internal hostname suffixes and non-public IP literals. Resolve each hop once, reject the entire result if any address is non-global/reserved/multicast or IPv4-mapped IPv6, then connect directly to a validated sockaddr using a local urllib3 connection subclass. Socket creation performs no second DNS lookup. Both IPv4 and IPv6 are supported, with fallback only among already validated addresses.
- urllib3 retains the original hostname for Host, TLS SNI and certificate verification, with CERT_REQUIRED and the Requests CA bundle. No TLS disabling, global DNS monkeypatch, environment proxy, or cross-hop pool reuse. Tests inspect the actual mocked socket destination, emitted Host header and TLS verification arguments.
- Redirects are disabled in the HTTP client and followed manually, validating each hop, with at most five redirects. The response closes on success, redirects and errors. The decoded response limit is 5 MiB. Existing connect/read timeouts are forwarded. HTTP errors remain Requests errors; the worker's existing exception handler records failures.
- `backend/library/feed_parser.py:16,118` wires the helper into all feed types. Public RSS, WordPress RSS, Atom/YouTube and JSON parsing are covered without network I/O.
- `backend/library/feed_source_service.py:6,21-22` rejects obvious internal URLs at validation time; `backend/library/feed_routes.py:487-491,519-523` returns 400 and rolls back rejected create/PATCH input. DNS-based decisions happen at fetch time, so a hostname changing after a write cannot bypass the fetch checks.
- Tests: `backend/tests/unit/test_feed_parser.py:4-10,53-194`; PATCH regression at `backend/tests/unit/test_flask_endpoints_orm.py:503-517`. No client changes.
- Residual limitations: URL validation is not an outbound firewall; HTTP without TLS still has normal HTTP transport risks. Feeds over 5 MiB or requiring URL credentials/proxies are intentionally rejected/unsupported. The webpage/tracking-link downloaders were brought onto the same `safe_http` path in a follow-up — see section 5.

## 3. Upload preflight does not list storage

- `backend/server.py:170-171`: OPTIONS `/uploads` returns empty 204 before argument parsing, storage construction or listing. It remains unauthenticated.
- Tests: `backend/tests/unit/test_flask_endpoints_orm.py:487-500` verifies empty 204, no lister/storage call, unauthenticated GET 401 and authenticated GET listing.
- The scan of explicit OPTIONS routes in server.py and backend/library found all other data handlers already return early. `/` still returns its intentionally public landing response and does not access storage; no additional OPTIONS fixes were needed.
- No client changes or additional residual risk identified for this fix.

## 4. Bound the in-process API-key cache

- `backend/library/auth.py:37,77-103`: default limit 10,000 entries; configurable capacity and injectable clock for deterministic tests. Under the existing lock, overflow first reclaims every expired entry, then evicts the entry with the earliest expiry if still over capacity. Reclamation does not require revisiting the expired keys.
- The get/set/invalidate protocol, positive and negative TTL constants, single/all invalidation and last_used_at throttling are unchanged. Entries expire at their deadline.
- Tests: `backend/tests/unit/test_auth_api_keys.py:92-136` covers overflow, independent expiration reclamation, expiry-order eviction, positive/negative hits, invalidation and concurrent get/set/invalidate.
- No client changes. At capacity, insertion scans up to 10,001 entries; this is deliberately a small local implementation. Expired entries below capacity can remain allocated until lookup/overflow, but total memory stays bounded. Rate limiting remains a separate follow-up, not implemented.

## Global verification

The worktree has no `backend/.venv`. Tests used the full existing environment at
`C:/Users/ziutus/git/_lenie-all/lenie-server-2025/backend/.venv/Scripts/python.exe`,
with cwd set to this worktree's backend and `PYTHONPATH=.` so the code under test was this checkout.
The environment used `SECRETS_BACKEND=env`, `ENV_DATA=unit-test`, dummy test model/provider values,
`PORT=5000`, and local dummy PostgreSQL test settings. No live secrets were loaded.

Command (PowerShell, after setting those environment variables):

```powershell
& C:/Users/ziutus/git/_lenie-all/lenie-server-2025/backend/.venv/Scripts/python.exe -m pytest tests/unit/ -q --basetemp ../.security-final-temp
```

Final result: **25 failed, 2796 passed, 24 warnings in 75.20s**. No collection/setup errors.
An archive of unchanged HEAD was run with the same interpreter/environment and a separate writable basetemp:
**25 failed, 2741 passed, 24 warnings in 73.19s**. The failed test IDs match exactly;
there are **55 additional passing cases and zero introduced failures**.
The final feed-parser-only run also passed: **38 passed in 1.75s**.
Initial attempts exposed missing ENV_DATA and inaccessible default pytest temporary directories;
setting dummy config and an explicit writable basetemp resolved those environment obstacles.

`uvx ruff check backend/` was attempted. The default uv directories were inaccessible;
a retry with workspace-local UV_CACHE_DIR and UV_TOOL_DIR was blocked fetching PyPI by network permissions.
Fallback: the existing full environment's `ruff.exe check backend/` completed and reported exactly two
F401 findings, both reproduced against unchanged HEAD:

- `backend/library/content_group_suggestion_service.py:12`: unused `get_active_groups`.
- `backend/library/information_provenance.py:8`: unused `sqlalchemy.delete`.

Running that ruff executable on all ten touched Python files returned **All checks passed!**
`git diff --check` passed. No package installation, dependency bump or pip invocation occurred.
Verification logs and the baseline snapshot are retained under the ignored
`backend/.pytest_cache/security-verification/` directory; recursive deletion was blocked by command policy.

Integration tests were not run: although localhost:5432 accepts TCP, no usable test-database connection
was available; the attempted connection using dummy test credentials failed in psycopg2 with
UnicodeDecodeError while decoding the connection error. Port 5433 timed out. This does not establish
that the listening database is configured for these integration tests.

## 5. Webpage and tracking-link fetchers pin DNS (follow-up)

The initial pass wired only the feed worker through `safe_http`. A second pass
routed the two older fetchers through the same DNS-pinned path.

- `backend/library/website/website_download_context.py`: `download_raw_html()` no
  longer does `validate_url_target()` + `requests.get(allow_redirects=False)` in a
  hand-rolled loop (which let Requests re-resolve DNS at connect time). It now
  calls `safe_http.safe_get()`, which resolves once, rejects any non-public
  address, connects the socket to the validated address (hostname kept for
  Host/SNI/cert verification) and re-validates every redirect hop. External
  contract unchanged: `bytes` on HTTP 200, `None` on any other non-redirect
  status, `ValueError` for a rejected target or too many redirects, transport
  errors propagate as `requests` exceptions. Response body capped at 15 MiB
  (`MAX_HTML_BYTES`). `validate_url_target()` is kept as the upfront literal/DNS
  pre-check and is still exported/imported unchanged.
- `backend/library/tracking_urls.py`: `resolve_tracking_url()` likewise fetches
  through `safe_http.safe_get()` (HEAD, then GET fallback for ESPs that reject
  HEAD). Contract unchanged: only `is_tracking_url()` matches are fetched, the
  Base64 `_embedded_destination()` shortcut still avoids the network, the
  canonicalized final URL is returned, and any failure logs a warning and
  returns the original URL.
- `backend/library/safe_http.py`: gained a `method=` argument (first hop only;
  redirects always follow with GET) and its user-facing error strings were
  de-"feed"-ed since it is now shared. Feed callers and their tests are
  unaffected.
- Tests: `backend/tests/unit/test_website_download_context.py` and
  `backend/tests/unit/test_tracking_urls.py` were rewritten to drive the pinned
  path (mocking the resolver / connection pool, not `requests.get`), including a
  DNS-rebinding regression (host public at validation, internal at connect time —
  socket still connects to the validated public address) and a
  redirect-to-internal block. `PYTHONPATH=. .venv/Scripts/python -m pytest
  tests/unit/test_website_download_context.py tests/unit/test_tracking_urls.py
  tests/unit/test_feed_parser.py` → 62 passed; downstream
  `test_document_service.py`, `test_chunk_review_promotion_routes.py`,
  `test_auth_api_keys.py`, `test_flask_endpoints_orm.py` → 173 passed, 1 failed
  (the same pre-existing `TestUrlAdd::test_duplicate_returns_existing_document_details`
  baseline failure). `ruff check` on all touched files: clean.

## Additional same-class findings left unchanged

- `infra/aws/serverless/lambdas/app-server-db/lambda_function.py:232-253` dispatches deletion by path without checking HTTP method. This dormant AWS implementation and its legacy API configuration were not changed.
- Within server.py, the extra HEAD email-footer fall-through was fixed as described above; no further real GET/HEAD domain mutations or private OPTIONS fall-throughs were identified.

## Exact pre-existing failing test IDs

Each ID below failed in both the unchanged base and final checkout under the same test environment.
Some depend on absent provider configuration; others assert older schema/response contracts.
They were not changed as part of these security fixes.

- `tests/unit/test_contact_routes.py::TestContactsListArchivedFilter::test_filters_to_any_selected_contact_group`
- `tests/unit/test_db_models.py::TestDict::test_dict_has_39_keys`
- `tests/unit/test_db_models.py::TestDict::test_dict_keys`
- `tests/unit/test_document_analysis_article_mode.py::TestArticleMode::test_single_chunk_run_skips_merge_topics_and_still_tags`
- `tests/unit/test_document_analysis_book_mode.py::TestScopeChapterRun::test_no_scope_chapter_leaves_scope_null`
- `tests/unit/test_document_analysis_book_mode.py::TestScopeChapterRun::test_scope_chapter_analyzes_only_that_chapter`
- `tests/unit/test_document_analysis_transcript_chapters.py::TestCreateRunUsesChapterSplit::test_chunk_count_matches_video_chapters`
- `tests/unit/test_document_analysis_transcript_chapters.py::TestCreateRunUsesChapterSplit::test_falls_back_to_sentence_split_without_chapter_list`
- `tests/unit/test_document_analysis_transcript_chapters.py::TestCreateRunUsesChapterSplit::test_reuses_earlier_ner_without_refreshing_entities`
- `tests/unit/test_document_editing.py::test_reopen_invalidates_derived_rows_and_resets_status`
- `tests/unit/test_document_relationship_graph.py::test_relationship_graph_returns_only_stored_links`
- `tests/unit/test_feed_saved_for_later.py::test_saved_for_later_transition_records_user_and_timestamp[error]`
- `tests/unit/test_feed_saved_for_later.py::test_saved_for_later_transition_records_user_and_timestamp[llm_analysis_requested]`
- `tests/unit/test_feed_saved_for_later.py::test_saved_for_later_transition_records_user_and_timestamp[new]`
- `tests/unit/test_flask_endpoints_entities.py::TestWebsiteEntitiesGet::test_returns_grouped_entities`
- `tests/unit/test_flask_endpoints_entities.py::TestWebsiteEntitiesGet::test_returns_ner_unavailable_timestamp_when_set`
- `tests/unit/test_flask_endpoints_entities.py::TestWebsiteEntitiesRefresh::test_place_verification_failure_does_not_fail_request`
- `tests/unit/test_flask_endpoints_entities.py::TestWebsiteEntitiesRefresh::test_refreshes_verifies_and_returns_entities`
- `tests/unit/test_flask_endpoints_orm.py::TestUrlAdd::test_duplicate_returns_existing_document_details`
- `tests/unit/test_legacy_aws_pull_service.py::test_dynamodb_query_paginates`
- `tests/unit/test_orm_crud.py::TestDictCompatibility::test_all_keys_present_including_none`
- `tests/unit/test_removed_lines.py::test_chunk_payload_marks_photo_caption_candidates`
- `tests/unit/test_time_periods.py::test_document_time_periods_endpoint`
- `tests/unit/test_timeline_events.py::test_document_events_endpoint`
- `tests/unit/test_tones.py::test_document_tones_endpoint`

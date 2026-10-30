# ADR-032: Database-backed allowlist of language models

**Date:** 2026-10-29
**Status:** Accepted
**Decision makers:** Ziutus

## Context

The set of language models Lenie may call lived in code: a tuple in `llm_model_registry.py` (what a reviewer
may pick), the name tuples in `ai.py` (`OPENAI_MODELS`, `GOOGLE_MODELS`, `SHERLOCK_MODELS`, which decide where
`ai_ask()` sends a call) and the per-task defaults (`FEED_DEFAULT_MODEL`, the preferred model for transcript
chapters). Models come and go on the provider's schedule, not ours:

- `gemini-2.0-flash-lite-001` was retired on 2026-06-01 and nobody noticed until a call failed;
- `gemini-2.5-flash-lite` was retired by Google on 2026-10-20 and is still the built-in default of the feed
  review suggestions;
- adding two cheap OpenRouter models on 2026-10-29 took a branch, a PR and a deploy for what is data.

The repository already moves such data to tables with REST and a short cache: cleanup rules
([ADR-027](adr-027-cleanup-rules-db-backed.md)), NER gazetteers ([ADR-029](adr-029-ner-gazetteer-db-backed.md)),
prompt templates, `llm_pricing`, and the household choices in `app_settings`.

## Options

1. **Keep the lists in code.** Reviewed in a PR, covered by tests. Cost: the full deploy cycle for every
   provider announcement.
2. **Table that only extends the code lists (the ADR-029 model).** A row can add a model but never remove one,
   so it cannot express "this model is retired".
3. **Table is the allowlist; the code list is only the fallback (chosen).**

## Decision

Option 3.

- Table `llm_models` (`model_id` unique, `label`, `provider`, `external`, `verified`, `status`, `retires_on`,
  `note`). `status` is `active`, `deprecated` (still offered, with `status` and `retires_on` in the picker
  data) or `retired` (hidden from every picker and no longer routed). The first migration seeds it with the
  list that was in code.
- `library/llm_model_store.py` reads the rows through a short own session with a 60 s cache (REST writes bust
  it). **An LLM call never fails because of this lookup:** any database error, including the `SystemExit` of
  `config_loader.require()`, yields `SEED_MODELS`, the same list as the migration seed (a unit test keeps the
  two identical). Unlike ADR-029 the database **replaces** the seed, because retiring a model must be
  expressible.
- `llm_model_registry` builds the picker data from the store; every endpoint that validates a chosen model
  (`is_selectable`) therefore follows the table. A saved household choice that is no longer selectable already
  falls back to the task's default, so retiring a model moves its users to the default automatically.
- `ai_ask()` routes a model id that has none of its built-in rules by the `provider` recorded in the table
  (`openai`, `cloudferro`, `google-vertexai`; `openrouter/…` and `arklabs/…` keep routing by prefix). A new
  Gemini or Bielik id therefore needs no code change. A retired or unlisted id is still `Unknown model`.
- REST `GET/POST /llm_models`, `PATCH/DELETE /llm_models/<id>` (`library/llm_model_routes.py`); writes need a
  `kind=service` key. `model_id` and `provider` are immutable (delete and re-add). `POST` validates the shape
  (`openrouter/<vendor>/<model>` only for provider `openrouter`) and returns a warning when a non-OpenRouter
  model has no active `llm_pricing` row, because its calls would then have an unknown cost.

What stays in code, on purpose:

- **Provider adapters** (how to call OpenAI, Vertex, OpenRouter, CloudFerro) and the capabilities that are
  properties of an adapter (`_RESPONSE_FORMAT_PROVIDERS`, `_SYSTEM_PROMPT_PROVIDERS`). A new provider is code.
- **Per-task preferences** (`FEED_DEFAULT_MODEL`, the preferred chapter model, `gpt-4o-mini` for tool tags).
  Each is already guarded by `is_selectable`, so retiring the preferred model in the table makes the task fall
  back to its next choice without a deploy; and the household default is a UI-saved `app_settings` value.
- **Prices** stay in `llm_pricing` (versioned, immutable rows) and, for OpenRouter, in its live catalog.

## Consequences

- Retiring or adding a model is one REST call, effective within the cache TTL.
- The migration seeds `openrouter/google/gemini-2.5-flash-lite` as `deprecated` (retires 2026-10-20) instead of
  hiding it, so behaviour does not change silently; set it to `retired` once its calls fail, and the feed review
  default moves on by itself.
- **Risks and mitigations.**
  - *A typo in a row fails at call time.* `POST` validates the shape and warns about a missing price; the
    `verified` flag records that a human has called the model.
  - *A bad id from a provider announcement is not detected automatically.* `retires_on` makes the picker able to
    warn ahead of the date; polling the OpenRouter catalog for vanished ids is a follow-up.
  - *Rows are not in git.* Back them up with the database; `GET /llm_models` is the export.
- **Not in this change:** the React page that lists the models and warns about `retires_on` (the REST API is
  enough for a skill or curl), and moving adapter capabilities into the table.

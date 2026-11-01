# Building a feature that calls an LLM

There is no single mechanism, but there is a settled pattern. Copy it from an existing feature instead of
inventing one: topic suggestions (`content_group_suggestion_service.py`, `/feed-review`), tool tags
(`tool_tag_suggester.py`, `/tool-recommendations`), chapter proposals (`transcript_chapters`), geopolitics
(`geopolitics_detect.py`, `/geopolitics`).

## 1. Call the model through `ai_ask()`

`library/ai.py` routes by model name to the provider and writes exactly one `llm_usage_logs` row per call
(tokens, latency, cost in `response.usage`). Pass an `operation` name (shows up in `/llm-costs`) and the
`document_id` when there is one. Never call a provider SDK directly. Ask for JSON with
`response_format` only when `supports_structured_output()` says the model honours it.

Cost: read it from `response.usage`, never compute it. `library/llm_usage/report.py` (`usage_report`,
`combine_usage_reports`) shapes one or several calls for a response, and returns "unknown" rather than 0 when
a model has no price.

## 2. Let the reader choose the model, and show the price

- Add a **task** to `_TASKS` in `library/llm_model_registry.py`. Each task has its own allowlist; do not borrow
  another feature's list (a model that is fine for tags may be wrong for yours). Add it to
  `_STRUCTURED_OUTPUT_TASKS` if the answer must be a JSON schema.
- The models themselves are rows of the `llm_models` table ([ADR-032](adr/adr-032-llm-models-db-backed.md));
  adding or retiring a model is a REST call, not a deploy. Prices come from `llm_pricing` or, for OpenRouter,
  from the live catalog (`selectable_models(task)` returns `input_price_per_million`,
  `output_price_per_million`, `context_length`, ...).
- Household default: a key in `app_settings` (`app_settings.get_setting/set_setting`), exposed as
  `GET/PUT /<feature>/model` returning `{default_model, saved, models}`. The default is "saved choice while still
  allowed, else the built-in, else the first available model" (`geopolitics_detect.default_model()`).
- Validate every `model` in a request with `is_selectable(model, TASK)`; answer 400 otherwise.
- Frontend: a `<select>` whose option text is `modelOptionText(option)` from `utils/modelDetails.ts` (price per
  1 mln tokens, context window, "niedostępny: …" for models without credentials, `disabled` for those), the
  default marked "— domyślny", and "Ustaw jako domyślny". Show the cost of the finished call from the response.

## 3. Prompts

Prompts that a person should be able to tune live in the `prompt_templates` table (versioned, Jinja2 in a
sandbox, UI at `/prompt-templates`, `library/prompt_templates.py`). **Today the table serves only the
`content_group_suggestion` task** (`VARIANTS`, `VARIABLES`, `DEFAULTS` are per task in code). A new feature's
prompt is a code constant until a task is registered there; keep it in one function and record a
`PROMPT_VERSION` so results can be traced to the wording that produced them.

## 4. Never trust the answer

- Parse defensively (fences, prose around the JSON); an unparseable answer is "nothing found", not an error.
- Validate every field against the database and the source text (known ids, parsable dates, quotes that occur
  verbatim in the document). Count what you reject, by reason, and show it.
- Store LLM output as a **proposal** with `detection_method`, `model` and the source passage; a human confirms
  with one click (`proposed` → `confirmed`/`rejected`, as in `document_links` and geopolitics). A rejected
  proposal must not come back on the next run.
- Make a rerun idempotent (dedup key or unique constraint) and cap the work (fragment size and count).
- A hallucinated or confident-sounding single claim must not change shared state on its own; cap confidence
  until independent sources agree.

## 5. Tests

Stub `ai_ask` (`monkeypatch.setattr(module, "ai_ask", fake)`) and feed it realistic and hostile answers
(garbage, fenced JSON, invented ids, relative dates). Test the validation and the idempotence, not the model.
Prove the real thing once against the real model on a real document, and roll the result back
(`session.rollback()`) when it is only a diagnostic.

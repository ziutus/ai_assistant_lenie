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
sandbox, UI at `/prompt-templates`, `library/prompt_templates.py`). The table is generic over `(task, variant)`:
`content_group_suggestion` (feed review, documents) and `geopolitics_events` (`event_extraction`) use it today.

To put a new prompt there:

1. Register the task in `VARIANTS`, its closed variable set in `VARIABLES` and the built-in text in `DEFAULTS`
   (`library/prompt_templates.py`). The built-in text is the fallback while the table has no active row, so
   write it so it renders exactly like the prompt it replaces, and test that equality with a captured golden
   string (`tests/unit/test_geopolitics_prompt.py`).
2. Give `_samples(task)` the variable sets the template must render with (every `{% if %}` branch), so an
   unknown variable or a syntax error is a 400 at save time, never a failed job.
3. In the feature, resolve the prompt with `get_active(session, task, variant)` and render it with the same
   variables; store the label (`template.label`, e.g. `event_extraction-v3` or `…-builtin`) on every row the
   model produced, so a wording can be judged by what it produced (`geo_events.prompt_version`).
4. `POST /prompt_templates/preview` renders a draft without calling a model; give the task a branch in
   `prompt_template_routes.preview_prompt_template` that builds the variables from a real object (a document
   id) or a sample.
5. UI: add the variant to `VARIANT_LABELS` / `TASK_OF` in `promptTemplates.tsx`.

The model/prompt comparison report (`/prompt_templates/comparison`) is still specific to topic suggestions.

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

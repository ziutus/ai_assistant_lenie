---
name: 'lenie-person-review'
description: 'Review the persons (persName entities) of one Lenie document: find spelling variants to merge (Silva / Silwa), nicknames and mishearings, wrong types, and shared-surname mentions (Bolsonaro) that need general knowledge to tell apart; propose fixes with evidence, apply them only after approval'
---

Review the list of people NER found in ONE document and fix it. Machine rules cannot tell
"Silwa" from "Silva" in a transcript, nor which Bolsonaro (Jair, Eduardo, Flavio, Michelle) a
sentence is about; this skill uses the model's general knowledge **plus the quoted context of
the document** to propose merges, renames and type changes, and applies them through the
existing REST endpoints only after the user approves.

Work and talk with the user in Polish. Repository paths are relative to the repository root.

## Input

- `document_id` (a number or a link such as `http://192.168.200.7:3000/ner/11222/2`; the last
  path number is the chapter, not needed here). Optional: a chapter to focus on, or a
  surname to look at first ("Bolsonaro").

## Runtime and API configuration

Base URL `http://192.168.200.7:5055`, header `x-api-key: $LENIE_API_KEY` (`user` or `service`
key; a `read_only` key can only run Steps 1-4). Never print the key or write it to the
repository.

**Prefer a temporary key.** If `LENIE_API_KEY` is missing, expired (HTTP 401) or read-only and
writes are needed, do NOT create a key yourself. Ask the user to run, on the dev machine with
the NAS database settings (see `backend/imports/CLAUDE.md`, "Running scripts against the NAS
production DB"):

```
python imports/api_key_admin.py create --kind service --name <agent>-person-review-<yyyy-mm-dd> --ttl 2h
```

The key is printed once and stops working after the TTL (at most 7 days). A running
backend caches key lookups for up to 5 minutes, never past the key's expiry.

Bash examples use `curl`; in PowerShell use `$env:LENIE_API_KEY`, `Invoke-RestMethod` and send
JSON as UTF-8 bytes (Polish names break otherwise). Check every HTTP status; after an
uncertain write, re-read the entities before retrying.

## Step 1: Read the persons

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" "http://192.168.200.7:5055/website_entities?id=<DOC>"
```

Take the `persName` items: `id` (the entity row id used by every write below), `text`,
`variants` (surface forms), `mention_count`, and for resolved ones `person_id`, `link_id`,
`canonical_name`, `confidence` (`wikidata_matched` / `alias_matched` / `manual_confirmed` /
`manual_review`). The document title, `byline` and tags (`GET /website_get?id=<DOC>`) tell you
the subject area (Brazilian politics, a US podcast ...), which decides who a name is.

For a book or a long transcript also use `GET /document/<DOC>/chapter_entities` (counts local
to each chapter) and `GET /document/<DOC>/entity_occurrences?text=<name>` (per-chapter
occurrences of a name).

## Step 2: Classify every person

Sort each row into exactly one bucket. Decide from the document, not from the name alone.

1. **OK** - a full, correct name, or a single distinctive surname.
2. **Spelling variant of another row** - "Silwa" / "Silva", "Hegset" / "Hegseth", "Stone" /
   "Andy Stone". Typical signs: one-letter or transliteration differences (v/w, y/j, ó/u),
   one form is a surname-only or first-name-only version of a fuller row, the same
   `person_id`. -> **merge** (Step 5a).
3. **Nickname or mishearing of a known person** ("Łacha Piachu" = Icchak Herzog). -> **real
   name** (5b); a speech-to-text slip of another entity of the document -> **transcription
   error** (5c).
4. **Not a person** (organization, place, product, event, noise). -> retype (5d) or the
   exclusion menu; say which.
5. **Shared surname** - a bare surname that several real people carry and the text refers to
   them under one row (Bolsonaro, Kaczynski, Le Pen, Kim, Trump, Silva). -> **split case**
   (Step 6).

Use general knowledge to pick the canonical form (e.g. "Luiz Inacio Lula da Silva" for
"Silva"/"Silwa" in a text about Brazil) but only propose a name you are confident about; say
"unsure" otherwise.

## Step 3: Collect evidence

For every non-OK row quote the sentences that justify the decision (chapter and a short exact
quote, from `GET /document/<DOC>/chapter_sections?with_sentences=1`, or the chapter text).
A proposal without a quote from this document is not a proposal. Check the registry for what
the name already resolves to (`GET /persons?q=<name>`: `canonical_name`, `description`,
`aliases`, `wikidata_qid`).

## Step 4: Present the proposal and WAIT

Show one table. Columns: row `id` and text, bucket, proposed action and endpoint, target,
evidence quote, confidence (high / medium / unsure), side effects. Include, per action, this
**global side effect** in plain words when it applies:

- Merging row A into row B (`persons/merge`) and `real_name` both add A's text and variants as
  **aliases of B's registry person**, so *later documents* resolve that spelling straight to B.
  That is right for "Silwa" -> "Silva". For a bare family surname it is risky ("Bolsonaro"
  becoming an alias of Jair would mislabel every later Eduardo): propose it only when the user
  accepts it, otherwise leave the row and report it as unresolved.
- Nothing is applied before the user answers. No answer or a partial answer = apply only
  what was explicitly approved.

## Step 5: Apply the approved actions

Order: merges, real names, transcription errors, retypes, deletions. After **every** write
re-read `GET /website_entities?id=<DOC>`: a merge deletes the source row, so ids change.

- **5a Merge** two rows of this document:
  `POST /document/<DOC>/persons/merge` `{"source_entity_id": S, "target_entity_id": T}`.
  Counts and surface forms fold into T; the decision is audited as `person_merged` and
  replayed after later entity refreshes. Several spellings of one person = several calls, one
  pair at a time; stop at the first failure.
- **5b Real name**: `POST /website_entities/<id>/real_name` `{"name": "Icchak Herzog"}` -
  finds or creates the registry person and makes the mention its alias (global, see above).
- **5c Transcription error**: `POST /website_entities/<id>/transcription_error`
  `{"correct_name": "Hegseth"}` - folds into another entity of the same document, creates no
  alias, and with a byline teaches the channel glossary.
- **5d Wrong type**: `POST /website_entities/<id>/to_organization|to_place|to_product`
  (optional `{"text": "..."}`); noise: `DELETE /website_entities/<id>` or `POST
  /ner_exclusions` (ask which).
- A person row that has no `link_id` (never resolved) can only be merged or retyped.

Never test a write on a real id "to see the error" (a harmless-looking PATCH once erased
data); use only the approved actions.

## Step 6: Shared surnames (the Bolsonaro case)

What the backend supports today: every `document_entities` row is one **text** (a surname, a
full name) with one person link. A full-name mention in the text ("Eduardo Bolsonaro") is
already its own row. What it cannot do is assign individual sentences of a bare "Bolsonaro"
row to different people.

1. List the rows that contain the surname (`Jair Bolsonaro`, `Eduardo Bolsonaro`,
   `Bolsonaro`, ...) and the registry persons behind them.
2. Read every context of the bare row (`entity_occurrences` + the chapter sentences). For each
   occurrence write who it is, with the quote and your confidence.
3. Decide by outcome:
   - **All bare mentions are the same person** (e.g. the former president Jair): propose
     merging the bare row into that person's full-name row (5a), with the alias warning from
     Step 4. If the full-name row does not exist, select the fragment with `POST
     /document/<DOC>/entities/add_mention` `{"text": "<exact text>", "entity_type": "persName",
     "name": "<full name>"}` first (409 `entity_exists` means it already is a row).
   - **Bare mentions are mixed** (Jair in one chapter, Eduardo in another): the current
     backend cannot split one row between people. Report it as **unresolved**: list the
     occurrences with the person you identified for each, so a follow-up feature (assigning a
     mention to a person) or a manual text edit can use it. Do not force-merge.
   - **Unsure**: say so and leave the row.
4. Never invent that a person is in the document: only people the text actually names or
   unambiguously refers to.

## Step 7: Verify and report

Re-read the entities and show a before / after list of the persons (text, `canonical_name`,
mention counts). Report in Polish: what was merged or renamed, what was left on purpose, and
the unresolved shared-surname occurrences. If a mechanism looks like a code bug rather than a
data fix, stop and suggest `/lenie-entity-diagnose` instead of working around it.

## Rules

- Reads need no approval; every POST / PATCH / DELETE needs the user's explicit approval of
  that exact action.
- Do not create API keys, change the registry (`PATCH /persons/<id>`), or touch other
  documents. This skill reviews one document.
- Keep Polish diacritics intact in names and quotes; check what you send for stray `?` after a
  PowerShell round-trip.

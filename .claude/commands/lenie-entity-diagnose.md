---
name: 'lenie-entity-diagnose'
description: 'Diagnose why a NER place/person/organization entity in a document was not recognized, geocoded, or linked correctly'
---

Read the complete workflow at `docs/agent/entity-diagnose-workflow.md` and follow it exactly.

Ask for the `document_id` and either the exact entity text or the chapter/fragment where the user noticed the problem, if not already given. Inspect the entity's `document_entities` row, its source-text context in `document_chunks`, and the type-specific resolution mechanism (geocoding for places, the person registry for persName, the organization registry for orgName) before proposing a fix. Check whether this is a live code bug or stale data sitting under a mechanism that was already fixed after the record was created (workflow Stage 2b). Do not implement a fix without a concrete example from the actual document and a regression test based on it.

Before touching any code, deploying to NAS, or mutating production data (PATCH/POST/SQL on `192.168.200.7`): explain to the user why the bug occurred and what fix you propose (code change vs. data-only fix vs. both), then wait for explicit approval (workflow Stage 3). Reads/diagnosis (SELECT, GET) don't need approval; changes do.

Once approved, delegate the actual code implementation to Codex (workflow Stage 4 — `Agent` with `subagent_type: "codex:codex-rescue"`) and evaluate its diff and regression test yourself rather than writing the fix directly; only implement it yourself if Codex delegation is unavailable, and say so explicitly. After deploy and verification, update the relevant documentation (workflow Stage 6) so a future diagnosis of the same mechanism finds it already covered, then append one entry to the case log (workflow Stage 7, `docs/ner-entity-diagnose-case-log.md`) using its template.

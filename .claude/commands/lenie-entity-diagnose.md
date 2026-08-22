---
name: 'lenie-entity-diagnose'
description: 'Diagnose why a NER place/person/organization entity in a document was not recognized, geocoded, or linked correctly'
---

Read the complete workflow at `docs/agent/entity-diagnose-workflow.md` and follow it exactly.

Ask for the `document_id` and either the exact entity text or the chapter/fragment where the user noticed the problem, if not already given. Inspect the entity's `document_entities` row, its source-text context in `document_chunks`, and the type-specific resolution mechanism (geocoding for places, the person registry for persName, the organization registry for orgName) before proposing a fix. Do not implement a fix without a concrete example from the actual document and a regression test based on it.

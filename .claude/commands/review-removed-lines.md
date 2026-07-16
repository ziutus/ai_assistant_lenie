---
name: 'review-removed-lines'
description: 'Analyze pending document_removed_lines candidates and improve website cleanup rules'
---

Read the complete workflow at `docs/agent/document-removed-lines-workflow.md` and follow it exactly.

Start by listing only `pending` candidates and grouping them by portal and structural pattern. Inspect source context and existing cleanup rules before proposing a decision. Do not mark any row as resolved until the corresponding rule and regression tests are implemented and verified. Use `backend/scripts/review_removed_lines.py` to record every final decision.


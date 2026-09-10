---
name: 'lenie-review-removed-lines'
description: 'Analyze pending document_removed_lines candidates and improve website cleanup rules'
---

Read the complete workflow at `docs/agent/document-removed-lines-workflow.md` and follow it exactly.

Start by listing only `pending` candidates and grouping them by portal and structural pattern. Inspect source context and existing cleanup rules before proposing a decision. Do not mark any row as resolved until the corresponding rule and regression tests are implemented and verified. Use `backend/scripts/review_removed_lines.py` to record every final decision.

For simple whole-line or fixed-phrase cases, prefer `backend/scripts/review_removed_lines.py --promote-rule`: it inserts a `cleanup_rules` row and records `rule_added` with a `cleanup_rules:<id>` reference — no PR, no deploy. Keep context-dependent logic and risky regexes in `article_cleaner.py` with tests.

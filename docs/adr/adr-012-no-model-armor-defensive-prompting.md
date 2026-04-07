# ADR-012: No Google Cloud Model Armor — Defensive Prompting for Prompt Injection Protection

**Date:** 2026-03-15
**Status:** Accepted
**Decision Makers:** Ziutus

### Context

Project Lenie ingests content from untrusted external sources (RSS feeds, web pages, YouTube transcripts, emails) and processes it through LLMs for summarization, embedding generation, and analysis. This creates a potential **prompt injection** attack surface — malicious content embedded in an article or email could manipulate LLM behavior when Lenie processes it.

[Google Cloud Model Armor](https://cloud.google.com/security/products/model-armor) was evaluated as a dedicated sanitization layer. It scans prompts and API responses for prompt injection, content safety violations, and adversarial inputs. Integration is available via the Google Workspace CLI (`gws modelarmor +sanitize-prompt`, `gws modelarmor +sanitize-response`) or directly via the Model Armor API.

### Decision

**Do not integrate Google Cloud Model Armor.** Instead, rely on a combination of defensive prompting, input sanitization, and content-as-data separation already present in the codebase.

### Rationale

1. **Disproportionate complexity for the threat model.** Model Armor requires a GCP project, template configuration, API calls per document, and ongoing cost. For a single-user personal project processing public RSS feeds and web pages, the attack surface is low — an attacker would need to compromise a specific RSS feed that Lenie monitors to inject adversarial content.

2. **Existing mitigations are sufficient.** The codebase already implements several layers of defense (see [`docs/security/prompt-injection-defense.md`](security/prompt-injection-defense.md)):
   - HTML stripping and content sanitization before LLM processing
   - Content treated as data (not instructions) in LLM prompts
   - Skip filters removing suspicious content patterns at import time
   - No autonomous agent actions — LLM outputs are stored, not executed

3. **Cost.** Model Armor API calls add per-document cost. Given Lenie processes hundreds of articles weekly, this would be a recurring expense with marginal security benefit for the current threat model.

4. **Vendor lock-in.** Integrating Model Armor ties the security layer to GCP. Lenie currently uses a multi-cloud approach (AWS, OpenAI, AssemblyAI) and adding a GCP dependency for security scanning contradicts the project's flexibility goals.

5. **Revisit trigger.** This decision should be reconsidered if:
   - Lenie becomes multi-user (untrusted users submitting content)
   - LLM outputs start triggering autonomous actions (API calls, database modifications, email sending)
   - A prompt injection incident occurs through the current feed/import pipeline

### Consequences

- **Positive:** No additional infrastructure, cost, or GCP dependency.
- **Positive:** Simpler architecture — security handled by existing code patterns.
- **Negative:** No dedicated prompt injection detection layer — relies on defense-in-depth rather than a specialized scanner.
- **Negative:** If the threat model changes (multi-user, autonomous actions), this decision must be revisited promptly.

### Related Artifacts

- [`docs/security/prompt-injection-defense.md`](security/prompt-injection-defense.md) — detailed description of current defenses
- [`docs/security/pre-commit-verification.md`](security/pre-commit-verification.md) — secret detection (related security control)
- `backend/imports/feed_monitor.py` — `strip_html()`, `apply_skip_filters()` — input sanitization
- `backend/library/ai.py` — LLM interaction layer
- [ADR-005](#adr-005-remove-ai_ask-endpoint--delegate-ai-analysis-to-claude-desktop-via-mcp) — MCP architecture (Claude Desktop handles AI analysis, reducing in-app LLM attack surface)

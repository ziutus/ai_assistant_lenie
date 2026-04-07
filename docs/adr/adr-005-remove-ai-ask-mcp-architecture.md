# ADR-005: Remove `/ai_ask` Endpoint — Delegate AI Analysis to Claude Desktop via MCP

**Date:** 2026-02 (Sprint 3, Epic 10)
**Status:** Accepted
**Decision Makers:** Ziutus

### Context

The `/ai_ask` endpoint allowed sending a text query to an LLM (OpenAI, Bedrock, Vertex AI, Bielik) directly from the React frontend. It was the only way to run AI analysis on collected documents from within the Lenie application.

Meanwhile, the workflow for working with collected knowledge evolved. Claude Desktop (and Claude Code) emerged as the primary interface for AI-powered text analysis, offering far richer capabilities than a single API call — multi-turn conversations, tool use, structured output, and deep reasoning. The missing piece was connecting Claude to Lenie's document store.

### Decision

1. **Remove the `/ai_ask` endpoint** from all layers (server.py, Lambda, API Gateway, React frontend).
2. **Preserve the `ai_ask()` function** in `backend/library/ai.py` — it is still used internally by `youtube_processing.py` for AI-generated video summaries.
3. **Adopt an MCP-based architecture** for AI analysis of collected documents:
   - **Lenie AI** serves as the knowledge base and document retrieval system, exposing its data to Claude Code/Desktop via an MCP server.
   - **Claude Desktop/Code** performs the AI analysis — summarizing, comparing, fact-checking, and synthesizing information from retrieved articles.
   - **Obsidian** serves as the knowledge output system — Claude Code places organized, summarized notes into Obsidian via a separate MCP server.

### Rationale

1. **Separation of concerns.** Lenie's role is to collect, store, and retrieve documents — not to be an AI chat interface. AI analysis is better handled by a dedicated tool (Claude Desktop) that is purpose-built for multi-turn reasoning and tool use.

2. **Superior AI capabilities.** Claude Desktop provides conversational analysis, multi-document synthesis, and structured reasoning that a single `/ai_ask` API call could never match. The user gets a far more powerful analytical experience.

3. **MCP as the integration layer.** The Model Context Protocol (MCP) allows Claude to pull documents from Lenie on demand and push structured notes to Obsidian. This creates a clean pipeline: **Lenie (collect & retrieve) → Claude (analyze) → Obsidian (organize & store knowledge)**.

4. **Reduced maintenance surface.** Removing the endpoint simplifies the API, reduces the attack surface, and eliminates the need to manage LLM API keys in the frontend.

### Consequences

- **Positive:** Clean separation — Lenie focuses on document management, Claude handles AI analysis, Obsidian stores knowledge output.
- **Positive:** Users get dramatically better AI analysis through Claude Desktop's full capabilities vs. a simple ask-and-answer endpoint.
- **Positive:** The MCP-based pipeline enables workflows impossible with a REST endpoint: multi-document comparison, cross-reference checking, structured note generation.
- **Negative:** Requires MCP server implementation for Lenie (future work).
- **Negative:** Users who don't have Claude Desktop lose in-app AI analysis capability (acceptable trade-off for a personal project).

### Related Artifacts

- Story 10.1: Remove `/ai_ask` endpoint
- Story 12.1: Codebase-wide stale reference verification
- `backend/library/ai.py:25` — `ai_ask()` function (preserved for internal use)
- `backend/library/youtube_processing.py:290` — internal consumer of `ai_ask()`

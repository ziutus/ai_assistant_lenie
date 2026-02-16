# Story 9.1: Update README.md with Project Vision & Roadmap

Status: done

## Story

As a developer (or future contributor),
I want to read README.md and understand the project's target architecture (Lenie-AI as MCP server for Claude Desktop + Obsidian vault) and phased roadmap,
so that I know where the project is heading and can plan contributions accordingly.

## Acceptance Criteria

1. **AC1 — Vision Statement**: README.md contains a clear description of the target vision: Lenie-AI as an MCP server for Claude Desktop + Obsidian vault workflow (FR18)
2. **AC2 — Phased Roadmap**: README.md contains a phased roadmap: current state → MCP server foundation → Obsidian integration (FR19)
3. **AC3 — Self-Contained Overview**: README.md contains: project purpose, current architecture summary, target vision, and phased roadmap — readable without consulting other files (NFR8)
4. **AC4 — Onboarding Ready**: README.md is self-contained — a new developer can understand the project's purpose and direction from this single file

## Tasks / Subtasks

- [x] Task 1: Add "Target Vision" section to README.md (AC: #1)
  - [x] 1.1: Write vision section describing Lenie-AI as MCP server for Claude Desktop
  - [x] 1.2: Describe Obsidian vault workflow integration concept
  - [x] 1.3: Explain the transition from current architecture (Flask REST API + React SPA) to MCP server model
- [x] Task 2: Add "Roadmap" section to README.md (AC: #2)
  - [x] 2.1: Document Phase 1 (Current State) — what exists today: Flask backend, React frontend, Chrome extension, AWS serverless deployment, PostgreSQL + pgvector
  - [x] 2.2: Document Phase 2 (MCP Server Foundation) — implement MCP protocol, expose search/retrieve as MCP tools, Claude Desktop integration
  - [x] 2.3: Document Phase 3 (Obsidian Integration) — vault synchronization, semantic search from Obsidian via Claude Desktop + MCP
- [x] Task 3: Update existing README.md sections for coherence (AC: #3, #4)
  - [x] 3.1: Review and update project description/introduction to align with vision
  - [x] 3.2: Add or update "Current Architecture" summary section (concise overview of backend, frontend, AWS, database)
  - [x] 3.3: Ensure "Documentation" section links are current and accurate
  - [x] 3.4: Remove or update outdated content (e.g., "Planned Improvements" section if superseded by roadmap)
- [x] Task 4: Final validation (AC: #1, #2, #3, #4)
  - [x] 4.1: Verify README.md is self-contained — a new developer can understand purpose, current state, and future direction
  - [x] 4.2: Verify no references to removed resources (DynamoDB cache tables, /url_add2) appear in README.md
  - [x] 4.3: Run markdown lint or visual review for formatting correctness

## Dev Notes

### Story Context

This is the first story in Epic 9 (Project Vision & Documentation Update). Epic 7 (Step Function Update & API Gateway Simplification) and Epic 8 (DynamoDB Cache Table Removal) are both complete, meaning the codebase is in its post-cleanup state. The README update should reflect this clean state.

### What Exists Today (Current README.md)

The current `README.md` (~157 lines) contains:
- Project description referencing Peter Watts' "Starfish"
- Core capabilities (links, webpage content, YouTube transcription)
- Components list (web interface, Chrome extension, Python backend)
- "Supported Platforms" table
- "Differences Compared to Corporate Knowledge Bases" — credibility assessment discussion
- "Challenges to Solve" — paywalls, platform scraping, content analysis costs
- "Scalability and Reliability" section
- "Used Technologies" — Python, PostgreSQL, React, Vault, AWS, Docker, K8s, Lambda
- "Services That Can Be Used" table (Textract, AssemblyAI)
- "Documentation" links table (8 docs)
- "Planned Improvements" — single item about Lambda Layers checker
- "Why Do We Need Our Own LLM?" — Polish language context with Bielik example

**What is MISSING**: No target vision, no roadmap, no current architecture summary, no MCP server mention, no Obsidian integration concept.

### Target Vision (from PRD)

The PRD defines the target vision as:
> "Private knowledge base in Obsidian vault, managed by Claude Desktop, powered by Lenie-AI as an MCP server for searching and managing content."

**Phase 2 (MCP Server Foundation):**
- Implement MCP server protocol — expose search/retrieve endpoints as MCP tools
- Claude Desktop integration — configure Lenie-AI as MCP server in Claude Desktop
- API adaptation — adjust endpoint patterns for MCP tool consumption

**Phase 3 (Obsidian Integration):**
- Obsidian vault integration — synchronization, linking, note creation
- Semantic search from within Obsidian via Claude Desktop + MCP
- Advanced vector search refinements for personal knowledge management

[Source: _bmad-output/planning-artifacts/prd.md#Product Scope]

### Current Architecture Summary (for README)

From CLAUDE.md and infra/aws/README.md, the current architecture is:
- **Backend**: Flask REST API (Python 3.11) with 19 endpoints, `x-api-key` auth
- **Frontend**: React 18 SPA (Create React App), served via CloudFront + S3
- **Database**: PostgreSQL 17 with pgvector (1536-dim embeddings, IVFFlat cosine index)
- **AWS Serverless**: API Gateway → 2 Lambda functions (DB + Internet), SQS async processing, Step Functions for cost optimization (auto start/stop RDS)
- **Browser Extension**: Chrome/Kiwi Manifest v3, captures pages → POST /url_add
- **AI Services**: OpenAI, AWS Bedrock, Google Vertex AI, CloudFerro Bielik
- **Docker**: docker compose with Flask + PostgreSQL + React

### Implementation Guidance

**File to modify**: `README.md` (root of repository)

**Approach**: Edit the existing README.md, do NOT rewrite from scratch. Preserve the existing content that is still relevant (project description, challenges, credibility discussion) while adding new sections and updating outdated parts.

**Section placement recommendation**:
1. Keep/update opening description
2. NEW: "Target Vision" section — after introduction, before components
3. NEW: "Roadmap" section — after Target Vision
4. Keep/update "Components" (rename to "Current Architecture" or keep and add architecture summary)
5. Keep "Supported Platforms"
6. Keep "Differences Compared to Corporate Knowledge Bases"
7. Keep "Challenges to Solve"
8. Update "Used Technologies" if needed
9. Keep "Documentation" links — verify all links still work
10. Replace "Planned Improvements" with reference to Roadmap or remove if redundant
11. Keep "Why Do We Need Our Own LLM?" — still relevant

**Writing style**: Match existing README tone — direct, informative, with occasional personality. English language. The author is a single developer explaining the project to potential contributors or his future self.

**Anti-patterns to avoid**:
- Do NOT add corporate-style marketing language
- Do NOT create overly detailed technical specs in README (that's what CLAUDE.md and docs/ are for)
- Do NOT reference removed resources (DynamoDB cache tables, /url_add2, old SNS topics, SES identities)
- Do NOT duplicate content already in CLAUDE.md — README should summarize and link

### Testing Approach

This is a documentation-only story. Testing means:
- Visual review of markdown rendering
- Verify self-containment: can a new developer understand the project from README alone?
- Verify no stale references to removed AWS resources
- Verify all documentation links in "Documentation" section still point to existing files

### Project Structure Notes

- `README.md` is at repository root
- Documentation links point to `docs/` directory
- `CLAUDE.md` at root contains detailed architecture — README should summarize, not duplicate
- Image `bielik_psy_pl.png` is referenced in README — verify it still exists

### References

- [Source: _bmad-output/planning-artifacts/prd.md#Executive Summary] — Target vision definition
- [Source: _bmad-output/planning-artifacts/prd.md#Product Scope] — Phase 2 and Phase 3 details
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 3 Story 3.1] — Acceptance criteria
- [Source: README.md] — Current content to be updated
- [Source: CLAUDE.md] — Current architecture reference (do not duplicate)
- [Source: infra/aws/README.md] — AWS infrastructure details

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

No debug issues encountered — documentation-only story.

### Completion Notes List

- Added "Target Vision" section describing Lenie-AI as MCP server for Claude Desktop + Obsidian vault workflow
- Added "Roadmap" section with 3 phases: Current State, MCP Server Foundation, Obsidian Integration
- Renamed "Components" to "Current Architecture" with expanded descriptions of all 6 components (Backend, Web Interface, Browser Extension, Database, AWS Serverless, Docker)
- Added link to CLAUDE.md for full architecture reference
- Removed "Planned Improvements" section (superseded by Roadmap)
- Verified all 8 Documentation table links point to existing files
- Verified bielik_psy_pl.png image still exists
- Verified zero stale references to removed resources (DynamoDB cache tables, /url_add2, sqs-to-rds)
- Introduction paragraphs preserved as-is — already aligned with vision
- Writing style matches existing README tone: direct, informative, personal

### Change Log

- 2026-02-16: Implemented story 9-1 — added Target Vision and Roadmap sections, renamed Components to Current Architecture with expanded details, removed obsolete Planned Improvements section
- 2026-02-16: Code review fixes — resolved content duplication (Phase 1 → cross-ref to Current Architecture), added Phase 4 (ECS/EKS scaling) to Roadmap, added web_add_url_react removal to Phase 2, standardized list formatting, added AI Services and Kubernetes to Current Architecture, cleaned up "Used Technologies" section

### File List

- README.md (modified) — added Target Vision, Roadmap (4 phases), Current Architecture sections; removed Planned Improvements; cleaned up Used Technologies

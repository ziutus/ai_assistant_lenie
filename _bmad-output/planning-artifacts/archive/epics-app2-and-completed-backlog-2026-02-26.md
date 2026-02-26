# Backlog: Multi-User Admin Interface & Frontend Platform — Archived Epics

> **Status:** ALL DONE — Archived 2026-02-26
> **Epics:** 19
> **Completed backlog items:** Landing page deployment, app2 infrastructure, B-49, B-51

## Backlog: Frontend & Multi-User Platform

### Overview

Work completed outside of Sprint 4/5 scope: landing page deployment and app2 (multi-user UI) infrastructure setup. Epic 19 captures the development of the target multi-user admin interface.

### Completed Work (Non-Sprint)

**Landing Page (www.lenie-ai.eu):**
- Migrated landing page to monorepo (`web_landing_page/`): Next.js 14.2 + React 18 + Tailwind 3.4
- Completed TypeScript migration (45 files JSX→TSX)
- Deployed on S3 + CloudFront via CloudFormation stacks (`s3-landing-web`, `cloudfront-landing`)
- Status: **LIVE** — publicly accessible at `www.lenie-ai.eu`

**app2 Infrastructure (app2.dev.lenie-ai.eu):**
- Created `s3-app2-web.yaml` — S3 bucket with CloudFront OAC, AES256 encryption, fully blocked public access
- Created `cloudfront-app2.yaml` — CloudFront distribution with SPA routing, TLSv1.2, Route53 alias
- Added both templates to `deploy.ini [dev]` (Layer 4 and Layer 8)
- `web_interface_app2/` — admin panel scaffolded from purchased layout (original reference layout removed from repo)
- Status: **Deployed** — admin panel with API key authentication live at `app2.dev.lenie-ai.eu`

---

## Epic 19: Multi-User Admin Interface (app2) — DONE

All 4 stories completed (2026-02-24). Admin panel at `app2.dev.lenie-ai.eu` is scaffolded, has API key login gate, professional layout, and connected backend API.

Developer has a new admin interface at `app2.dev.lenie-ai.eu` — scaffolded from a purchased layout (now removed from repo) with API key authentication, API integration, and own code in `web_interface_app2/`.

**Stories:** 19-1, 19-2, 19-3, 19-4

Implementation notes:
- Authentication uses `x-api-key` (same as backend) instead of originally planned username/password env vars — simpler, sufficient for dev/single-user. AWS Cognito migration planned for Phase 9 (B-33).
- Infrastructure provisioned and deployed (S3 + CloudFront stacks)
- Original purchased layout reference removed from repo (commit e8a44fd); design incorporated into `web_interface_app2/`
- Tech stack: Vite 6, React 18, Redux, React Bootstrap, TypeScript, Sass
- Current single-user app: `web_interface_react/` at `app.dev.lenie-ai.eu`
- Deploy script created with SSM integration (B-51)
- Domain: `app2.dev.lenie-ai.eu` (fixed from `app2.lenie-ai.eu` in B-43)

### Story 19.1: Scaffold Multi-User App Project

As a **developer**,
I want to create a new web application project (`web_interface_app2/`) with a modern React + TypeScript stack,
so that development of the multi-user interface can begin with a clean, properly structured codebase.

**Acceptance Criteria:**

**Given** the purchased layout uses React 18, Redux, React Bootstrap, TypeScript, and Sass
**When** the developer scaffolds the new project
**Then** the project uses a compatible modern stack (Vite + React 18 + TypeScript + Redux Toolkit + React Bootstrap)
**And** the project is created in `web_interface_app2/` directory
**And** it builds and runs on port 3001

**Given** the app2 CloudFront distribution exists
**When** the developer configures the build
**Then** static export is compatible with S3 + CloudFront SPA hosting (index.html fallback)

**Status:** done
**Completed:** 2026-02-24 (commit 478b62c)

### Story 19.2: Add Login Page and Route Protection

As a **developer**,
I want app2 to require login before showing any content,
so that the admin interface is not publicly accessible to unauthorized users.

**Acceptance Criteria:**

**Given** app2 is publicly accessible at `app2.dev.lenie-ai.eu` without authentication
**When** the developer adds a login page
**Then** all routes except `/login` redirect to the login page when the user is not authenticated
**And** the login page has a simple form with API key field

**Given** the user submits a valid API key
**When** the login form processes the submission
**Then** the app stores the API key in localStorage
**And** the user is redirected to the main dashboard
**And** all protected routes become accessible

**Given** the user submits an incorrect API key
**When** the login form processes the submission
**Then** an error message is displayed
**And** the user remains on the login page

**Implementation note:** Original spec called for username/password with env vars (`APP2_AUTH_USERNAME`, `APP2_AUTH_PASSWORD`). Actual implementation uses `x-api-key` authentication — the same API key used by the backend. This is simpler and sufficient for single-user/dev use. Migration to AWS Cognito (B-33) planned for Phase 9.

**Status:** done
**Completed:** 2026-02-24 (commits: 478b62c, a5422fc, 9c279e7, 5c57356)

### Story 19.3: Implement Core Layout and Navigation

As a **developer**,
I want to implement the core layout structure (sidebar, header, main content area) inspired by the purchased layout,
so that the application has a professional multi-user admin interface look and feel.

**Acceptance Criteria:**

**Given** `web_interface_app2/` already contains the layout scaffolded from the purchased template
**When** the developer reviews the layout structure
**Then** the app has a professional visual structure with own code (sidebar navigation, header bar, content area)
**And** responsive design works on desktop and tablet

**Given** the current app has 7 pages (document list, search, link/webpage/youtube/movie editors)
**When** the developer plans the navigation
**Then** the sidebar includes routes for all existing features plus user management (future)

**Given** Story 19.2 (login) is implemented
**When** the layout is rendered
**Then** all layout pages are behind the authentication guard

**Implementation note:** Layout scaffolded from purchased template. Purchased template reference (`web_interface_target/`) removed from repo (commit e8a44fd) — design already incorporated into app2 codebase.

**Status:** done
**Completed:** 2026-02-24 (commit 478b62c)

### Story 19.4: Connect Backend API

As a **developer**,
I want the new multi-user interface to connect to the existing backend API,
so that all current functionality (document CRUD, search, AI operations) works through the new UI.

**Acceptance Criteria:**

**Given** the backend API is accessible at `api.dev.lenie-ai.eu`
**When** the developer integrates API calls
**Then** all existing endpoints work: document list, get, save, delete, search, download content, AI embedding
**And** the `x-api-key` authentication header is included in all requests

**Given** the current app (`web_interface_react/`) has working API integration
**When** the developer reviews its implementation
**Then** the API service layer is adapted for the new app (axios, error handling, auth)

**Implementation note:** Hardcoded API key removed (commit 5c57356), API key now provided via login page. Redux store manages API server configuration.

**Status:** done
**Completed:** 2026-02-24 (commits: 478b62c, 5c57356)

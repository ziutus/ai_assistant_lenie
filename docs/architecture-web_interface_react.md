# Architecture — Main Frontend (web_interface_react)

> Generated: 2026-02-13 | Part: web_interface_react | Type: React 18 SPA

## Architecture Pattern

**Context + Hooks + Pages**: Global state via AuthorizationContext, API communication via custom hooks, page-based routing.

```
AuthorizationProvider (global state)
  └── BrowserRouter (React Router v6)
      └── App (route definitions)
          └── Layout (sidebar navigation + content area)
              └── Authorization (API config panel)
              └── Page Component (Formik form)
                  ├── SharedInputs (common fields)
                  ├── InputsForAllExceptLink (content + AI tools)
                  └── FormButtons (save/delete actions)
```

## Technology Stack

| Category | Technology | Version |
|----------|-----------|---------|
| Framework | React | ^18.2.0 |
| Build | Create React App | 5.0.1 |
| Routing | React Router | ^6.26.1 |
| Forms | Formik | ^2.4.6 |
| HTTP | axios | ^1.5.1 |
| i18n | react-i18next + i18next | ^15/^23 (installed, not configured) |
| Code formatting | Prettier | ^3.3.3 |

## Application Architecture

### Provider Hierarchy

```javascript
<React.StrictMode>
  <AuthorizationProvider>
    <BrowserRouter>
      <App /> // Routes
    </BrowserRouter>
  </AuthorizationProvider>
</React.StrictMode>
```

### Global State (AuthorizationContext)

- **API config**: `apiUrl`, `apiKey`, `apiType` (AWS Serverless / Docker)
- **Infrastructure status**: `databaseStatus`, `vpnServerStatus`, `sqsLength`
- **Document filters**: `selectedDocumentType`, `selectedDocumentState`, `searchInDocument`, `searchType`

### Routing (7 routes)

| Route | Page | Document Type |
|-------|------|--------------|
| `/` → `/list` | Redirect | — |
| `/list` | Document list | All types |
| `/search` | Vector similarity search | — |
| `/link/:id?` | Link editor | link |
| `/webpage/:id?` | Webpage editor + AI tools | webpage |
| `/youtube/:id?` | YouTube editor | youtube |
| `/movie/:id?` | Movie editor | movie |
| `/upload-file` | File upload (alpha) | — |

### Custom Hooks (API layer)

7 hooks encapsulating all backend communication:

| Hook | Endpoints | Purpose |
|------|-----------|---------|
| `useManageLLM` | 9 endpoints | Core CRUD + AI operations |
| `useList` | `/website_list` | Document list fetching |
| `useSearch` | `/ai_embedding_get`, `/website_similar` | Vector similarity search |
| `useDatabase` | `/infra/database/*` | RDS lifecycle (AWS only) |
| `useVpnServer` | `/infra/vpn_server/*` | VPN control (AWS only) |
| `useSqs` | `/infra/sqs/size` | Queue monitoring (AWS only) |
| `useFileSubmit` | Hardcoded AWS endpoint | Image upload |

### Backend Mode Toggle

The app supports two API backends:
- **AWS Serverless**: Two Lambda endpoints (DB + Internet) via API Gateway
- **Docker**: Single Flask endpoint (localhost:5000)

Key difference: `useSearch` uses two-step process for AWS (get embedding → search) vs single call for Docker.

## Component Architecture

### Reusable Components (6)

| Component | Responsibility |
|-----------|---------------|
| `Layout` | Sidebar navigation, hamburger menu, version display |
| `Authorization` | API config panel, infrastructure status (3x3 grid) |
| `Input` | Generic form input (text, textarea, select) |
| `Select` | Select dropdown wrapper |
| `SharedInputs` | Common document fields (ID, URL, title, summary, tags, etc.) |
| `FormButtons` | Save/delete action buttons with loading state |

### Specialized Component

| Component | Used By |
|-----------|---------|
| `InputsForAllExceptLink` | webpage, youtube, movie pages — content fields + AI tool buttons |

### AI Tool Buttons (in InputsForAllExceptLink)

1. **Split for Embedding** — calls `/website_split_for_embedding`
2. **Clean Text** — calls `/website_text_remove_not_needed`

## Form State Management

All editing pages use **Formik** with 20 fields: `id, author, source, language, url, tags, title, summary, text, text_md, text_english, document_type, document_state, document_state_error, chapter_list, note, next_id, previous_id, next_type, previous_type`

No client-side validation schema defined. Validation handled server-side.

## Styling

- Custom CSS (no design system or component library)
- CSS Modules per component (`.module.css`)
- Global styles in `index.css` (buttons, loader animation, error text)
- Color scheme: Blue buttons, yellow/green/red status indicators

## Docker Deployment

- Build: node:24.0 with yarn
- Production: node:24.0-slim
- Port: 3000
- User: lenie-ai-client (UID 1001)

## User Activity Monitoring (Historical Note)

The frontend previously used **AWS CloudWatch RUM** (`aws-rum-web`) to track real user interactions — page views, errors, HTTP calls, and custom events (document list filtering, document deletion). The integration used a Cognito Identity Pool for anonymous authentication and was disabled on localhost.

This was removed during frontend cleanup because it was still in an experimental/testing phase and added unnecessary complexity to the codebase. The decision was made to keep the frontend clean and focused on core functionality for now.

**Future consideration:** User activity monitoring may be reintroduced later — either via CloudWatch RUM again or an alternative solution (e.g., self-hosted analytics, PostHog, or custom event tracking) to understand how users interact with the application.

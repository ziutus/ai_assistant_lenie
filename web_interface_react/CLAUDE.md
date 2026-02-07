# Frontend (React) — CLAUDE.md

React 18 single-page application for managing documents and running AI operations (translation, text correction, embedding, similarity search). Built with Create React App.

**App version**: 0.2.11 | **Package version**: 0.1.0

## Directory Structure

```
web_interface_react/
├── public/                             # Static assets (index.html, icons, manifest)
├── src/
│   ├── index.js                        # Entry point (AuthorizationProvider + Router)
│   ├── App.js                          # Route definitions (React Router v6)
│   ├── utils.js                        # Utility components
│   ├── modules/shared/
│   │   ├── context/
│   │   │   └── authorizationContext.js  # Global state: API config, DB/VPN status, filters
│   │   ├── hooks/
│   │   │   ├── useManageLLM.js         # Core document CRUD + AI operations
│   │   │   ├── useList.js              # Document list fetching
│   │   │   ├── useSearch.js            # Vector similarity search
│   │   │   ├── useDatabase.js          # RDS start/stop/status
│   │   │   ├── useVpnServer.js         # VPN server control
│   │   │   ├── useSqs.js              # SQS queue size check
│   │   │   └── useFileSubmit.js        # Image file upload
│   │   ├── components/
│   │   │   ├── Layout/                 # Sidebar navigation + content area
│   │   │   ├── Authorization/          # API key, DB/VPN status panel
│   │   │   ├── Input/                  # Reusable text/textarea input
│   │   │   ├── Select/                 # Reusable select dropdown
│   │   │   ├── SharedInputs/           # Common document form fields
│   │   │   └── FormButtons/            # Save/delete action buttons
│   │   ├── pages/
│   │   │   ├── list.jsx                # Document list with type/state filtering
│   │   │   ├── search.jsx              # Vector similarity search
│   │   │   ├── link.jsx                # Link document editing
│   │   │   ├── webpage.jsx             # Webpage editing + AI processing
│   │   │   ├── youtube.jsx             # YouTube transcript editing
│   │   │   ├── movie.jsx               # Movie transcript editing
│   │   │   └── file.jsx                # File upload (alpha)
│   │   ├── constants/
│   │   │   └── variables.js            # App version, LLM config
│   │   └── styles/
│   │       └── index.css               # Global styles (buttons, loader, errors)
├── Dockerfile                          # Docker build (node:24.0, yarn, port 3000)
├── package.json                        # Dependencies & scripts
├── .prettierrc                         # Code formatting
├── .stylelintrc                        # CSS linting
└── .gitignore
```

## Pages & Routes

All routes wrapped in `<Layout>` and `<Authorization>`. React Router v6 with optional `:id?` parameter for document editing.

| Route | Page | Purpose |
|-------|------|---------|
| `/` | — | Redirects to `/list` |
| `/list` | `list.jsx` | Browse documents with type/state/text filters |
| `/search` | `search.jsx` | Vector similarity search across embeddings |
| `/link/:id?` | `link.jsx` | Edit link documents (metadata only) |
| `/webpage/:id?` | `webpage.jsx` | Edit webpages with AI tools (correct, translate, split, clean) |
| `/youtube/:id?` | `youtube.jsx` | Edit YouTube transcripts |
| `/movie/:id?` | `movie.jsx` | Edit movie transcripts |
| `/upload-file` | `file.jsx` | Upload image files (alpha) |

## Architecture

### Provider Hierarchy

```
AuthorizationProvider → BrowserRouter → App (routes) → Layout → Page
```

### Global State (`authorizationContext.js`)

- **API config**: `apiUrl`, `apiKey`, `apiType` (AWS Serverless / Docker)
- **Infrastructure status**: `databaseStatus`, `vpnServerStatus`, `sqsLength`
- **Document filters**: `selectedDocumentType`, `selectedDocumentState`, `searchInDocument`, `searchType`
- **AWS RUM**: CloudWatch Real User Monitoring (disabled on localhost)

### Custom Hooks

| Hook | Purpose | Key API Endpoints |
|------|---------|-------------------|
| `useManageLLM` | Document CRUD, AI processing (correct, translate, split, clean) | `/website_get`, `/website_save`, `/website_delete`, `/website_download_text_content`, `/ai_ask`, `/translate`, `/website_split_for_embedding`, `/website_text_remove_not_needed` |
| `useList` | Fetch document list with filters | `/website_list` |
| `useSearch` | Vector similarity search | `/ai_embedding_get` + `/website_similar` (AWS) or `/website_similar` only (Docker) |
| `useDatabase` | RDS instance management | `/infra/database/status\|start\|stop` |
| `useVpnServer` | VPN server management | `/infra/vpn_server/status\|start\|stop` |
| `useSqs` | SQS queue size | `/infra/sqs/size` |
| `useFileSubmit` | Image upload | Separate AWS endpoint |

### Component Patterns

- **Pages** — entry-point components wrapping Formik form + shared components
- **SharedInputs** — common fields reused across all document types (ID, URL, title, summary, tags, author, source, language, state)
- **InputsForAllExceptLink** — extra fields for webpage/youtube/movie (markdown, text, AI tool buttons, translation, chapters, note)
- **FormButtons** — save/delete actions with loading state
- **Input / Select** — generic form primitives with CSS modules

## Backend API Communication

- **HTTP client**: axios
- **Auth header**: `x-api-key: {apiKey}` on all requests
- **Content-Type**: `application/x-www-form-urlencoded`
- **API type toggle**: AWS Serverless (two Lambda endpoints) or Docker (single Flask endpoint)

### Endpoint Categories

| Category | Endpoints |
|----------|----------|
| **Document CRUD** | `GET /website_list`, `GET /website_get`, `POST /website_save`, `GET /website_delete`, `GET /website_get_next_to_correct` |
| **Content processing** | `POST /website_is_paid`, `POST /website_download_text_content`, `POST /website_text_remove_not_needed`, `POST /website_split_for_embedding` |
| **AI operations** | `POST /ai_embedding_get`, `POST /website_similar`, `POST /ai_ask`, `POST /translate` |
| **Infrastructure** | `/infra/database/*`, `/infra/vpn_server/*`, `/infra/sqs/size` |

## Form State Management

Uses **Formik** (v2.4.6) for all document editing pages. Document fields:

```
id, author, source, language, url, tags, title, summary,
text, text_md, text_english, document_type, document_state,
document_state_error, chapter_list, note,
next_id, previous_id, next_type, previous_type
```

## Dependencies

| Library | Version | Purpose |
|---------|---------|---------|
| react | ^18.2.0 | UI framework |
| react-router-dom | ^6.26.1 | Client-side routing |
| axios | ^1.5.1 | HTTP client |
| formik | ^2.4.6 | Form state management |
| react-i18next | ^15.0.2 | i18n support (installed, not yet configured) |
| i18next | ^23.15.1 | i18n core |
| aws-rum-web | ^1.19.0 | AWS CloudWatch RUM |
| react-scripts | 5.0.1 | CRA build tools |

## Running

```bash
npm start         # Dev server (port 3000)
npm run build     # Production build
npm test          # Run tests (@testing-library/react)
```

## Docker Build

```
Base: node:24.0
Install: yarn install
Production: node:24.0-slim
User: lenie-ai-client (UID 1001)
Port: 3000
Command: yarn start
```

## i18n

`react-i18next` and `i18next` are installed as dependencies but not yet configured. UI strings are currently hardcoded in Polish.

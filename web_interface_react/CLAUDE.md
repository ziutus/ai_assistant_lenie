# Frontend (React) — CLAUDE.md

React 18 single-page application for managing documents and running AI operations (text correction, embedding, similarity search). Built with **Vite** and **TypeScript**.

**App version**: 0.3.13.0 | **Package version**: 0.3.13.0

## Directory Structure

```
web_interface_react/
├── public/                             # Static assets (favicon, icons, manifest)
├── src/
│   ├── main.tsx                        # Entry point (AuthorizationProvider + Router)
│   ├── App.tsx                         # Route definitions (React Router v6) + RequireAuth guard
│   ├── App.test.tsx                    # Vitest smoke tests
│   ├── utils.tsx                       # Utility components
│   ├── vite-env.d.ts                   # Vite + CSS module type declarations
│   ├── types/
│   │   └── index.ts                    # TypeScript interfaces (WebDocument, ApiType, etc.)
│   ├── modules/shared/
│   │   ├── context/
│   │   │   └── authorizationContext.tsx # Global state: API config (from localStorage), DB/VPN status, filters
│   │   ├── services/
│   │   │   └── storage.ts              # localStorage persistence for connection config
│   │   ├── hooks/
│   │   │   ├── useManageLLM.ts         # Core document CRUD + AI operations
│   │   │   ├── useList.ts              # Document list fetching
│   │   │   ├── useSearch.ts            # Vector similarity search
│   │   │   ├── useDatabase.ts          # RDS start/stop/status
│   │   │   ├── useVpnServer.ts         # VPN server control
│   │   │   ├── useSqs.ts              # SQS queue size check
│   │   │   └── useFileSubmit.ts        # Image file upload
│   │   ├── components/
│   │   │   ├── Layout/                 # Sidebar navigation + content area
│   │   │   ├── Authorization/          # DB/VPN status panel, connection indicator, disconnect
│   │   │   ├── Input/                  # Reusable text/textarea input
│   │   │   ├── Select/                 # Reusable select dropdown
│   │   │   ├── SharedInputs/           # Common document form fields
│   │   │   └── FormButtons/            # Save/delete action buttons
│   │   ├── pages/
│   │   │   ├── connect.tsx             # Connection configuration (/connect)
│   │   │   ├── list.tsx                # Document list with type/state filtering
│   │   │   ├── search.tsx              # Vector similarity search
│   │   │   ├── link.tsx                # Link document editing
│   │   │   ├── webpage.tsx             # Webpage editing + AI processing
│   │   │   ├── youtube.tsx             # YouTube transcript editing
│   │   │   ├── movie.tsx               # Movie transcript editing
│   │   │   └── file.tsx                # File upload (alpha)
│   │   ├── constants/
│   │   │   └── variables.ts            # App version
│   │   └── styles/
│   │       └── index.css               # Global styles (buttons, loader, errors)
├── index.html                          # Root HTML (Vite entry point)
├── vite.config.ts                      # Vite + Vitest configuration
├── tsconfig.json                       # TypeScript strict configuration
├── Dockerfile                          # Multi-stage: Vite build + nginx
├── nginx.conf                          # SPA routing + cache headers
├── package.json                        # Dependencies & scripts
├── .prettierrc                         # Code formatting
├── .stylelintrc                        # CSS linting
└── .gitignore
```

## Pages & Routes

All protected routes wrapped in `RequireAuth` → `Layout` → `Authorization`. Unauthenticated users redirected to `/connect`.

| Route | Page | Purpose |
|-------|------|---------|
| `/connect` | `connect.tsx` | Backend connection configuration (API type, URL, key) |
| `/` | — | Redirects to `/list` |
| `/list` | `list.tsx` | Browse documents with type/state/text filters |
| `/search` | `search.tsx` | Vector similarity search across embeddings |
| `/link/:id?` | `link.tsx` | Edit link documents (metadata only) |
| `/webpage/:id?` | `webpage.tsx` | Edit webpages with AI tools (split, clean) |
| `/youtube/:id?` | `youtube.tsx` | Edit YouTube transcripts |
| `/movie/:id?` | `movie.tsx` | Edit movie transcripts |
| `/upload-file` | `file.tsx` | Upload image files (alpha) |

## Architecture

### Provider Hierarchy

```
AuthorizationProvider (init from localStorage) → BrowserRouter → App → RequireAuth → Layout → Page
```

### Connection Flow

1. User opens app → `RequireAuth` checks for API key in context (loaded from localStorage)
2. No key → redirect to `/connect`
3. User enters API type, URL, API key → validates via `GET /website_list?type=link&limit=1`
4. On success → saves to localStorage, sets context, redirects to `/list`
5. On page refresh → `AuthorizationProvider` loads config from localStorage

### Global State (`authorizationContext.tsx`)

- **API config** (persisted to localStorage): `apiUrl`, `apiKey`, `apiType` (AWS Serverless / Docker), `infraApiUrl`
- **Infrastructure status**: `databaseStatus`, `vpnServerStatus`, `sqsLength`
- **Document filters**: `selectedDocumentType`, `selectedDocumentState`, `searchInDocument`, `searchType`

### localStorage Keys

| Key | Value |
|-----|-------|
| `lenie_apiType` | "AWS Serverless" or "Docker" |
| `lenie_apiUrl` | Server API URL |
| `lenie_infraApiUrl` | Infrastructure API URL |
| `lenie_apiKey` | API authentication key |

### Custom Hooks

| Hook | Purpose | Key API Endpoints |
|------|---------|-------------------|
| `useManageLLM` | Document CRUD, AI processing (split, clean) | `/website_get`, `/website_save`, `/website_delete`, `/website_download_text_content`, `/website_split_for_embedding`, `/website_text_remove_not_needed` |
| `useList` | Fetch document list with filters | `/website_list` |
| `useSearch` | Vector similarity search | `/ai_embedding_get` + `/website_similar` (AWS) or `/website_similar` only (Docker) |
| `useDatabase` | RDS instance management | `/infra/database/status\|start\|stop` |
| `useVpnServer` | VPN server management | `/infra/vpn_server/status\|start\|stop` |
| `useSqs` | SQS queue size | `/infra/sqs/size` |
| `useFileSubmit` | Image upload | Separate AWS endpoint |

## Backend API Communication

- **HTTP client**: axios
- **Auth header**: `x-api-key: {apiKey}` on all requests
- **Content-Type**: `application/x-www-form-urlencoded`
- **API type toggle**: AWS Serverless (custom domain `api.dev.lenie-ai.eu`) or Docker (localhost:5000)

### Default URLs

| API Type | Server URL | Infra URL |
|----------|-----------|-----------|
| AWS Serverless | `https://api.dev.lenie-ai.eu` | `https://api.dev.lenie-ai.eu/infra` |
| Docker | `http://localhost:5000` | `http://localhost:5000` |

## TypeScript

All source files are TypeScript (`.ts`/`.tsx`). Key type definitions in `src/types/index.ts`:
- `ApiType` — union type for API backend mode
- `WebDocument` — document form fields interface
- `AuthorizationState` — global context interface
- `SearchResult`, `ListItem` — API response types

Strict mode enabled (`tsconfig.json`: `strict: true`).

## Dependencies

| Library | Version | Purpose |
|---------|---------|---------|
| react | ^18.3.1 | UI framework |
| react-router-dom | ^6.30.3 | Client-side routing |
| axios | ^1.13.5 | HTTP client |
| formik | ^2.4.9 | Form state management |
| react-i18next | ^15.7.4 | i18n support (installed, not yet configured) |
| i18next | ^23.16.8 | i18n core |
| vite | ^6.0.7 | Build toolchain |
| typescript | ^5.7.3 | Type checking |
| vitest | ^2.1.8 | Test framework |

## Running

```bash
npm run dev       # Dev server (port 3000)
npm run build     # TypeScript check + Vite production build (output: build/)
npm run preview   # Preview production build
npm test          # Run Vitest tests
npm run lint      # TypeScript type check only
```

## Docker Build

```
Stage 1: node:24 → npm ci && npm run build
Stage 2: nginx:alpine → serve build/ on port 80
Config: nginx.conf with SPA routing (all paths → index.html)
```

## i18n

`react-i18next` and `i18next` are installed as dependencies but not yet configured. UI strings are currently hardcoded in Polish.

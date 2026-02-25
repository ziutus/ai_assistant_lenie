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
│   │   └── index.ts                    # Re-exports from @lenie/shared + app-specific AuthorizationState
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

- **API config** (persisted to localStorage): `apiUrl`, `apiKey`, `apiType` (AWS Serverless / Docker)
- **Infrastructure status**: `databaseStatus`, `vpnServerStatus`, `sqsLength`
- **Document filters**: `selectedDocumentType`, `selectedDocumentState`, `searchInDocument`, `searchType`

### localStorage Keys

| Key | Value |
|-----|-------|
| `lenie_apiType` | "AWS Serverless" or "Docker" |
| `lenie_apiUrl` | API URL (single URL for both app and infra endpoints) |
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

| API Type | API URL |
|----------|---------|
| AWS Serverless | `https://api.dev.lenie-ai.eu` |
| Docker | `http://localhost:5000` |

App endpoints use the base URL (e.g., `/website_list`), infra endpoints use `/infra` prefix (e.g., `/infra/database/status`). Both share the same domain via API Gateway custom domain base path mappings.

## TypeScript

All source files are TypeScript (`.ts`/`.tsx`). Strict mode enabled (`tsconfig.json`: `strict: true`).

### Shared Types (`@lenie/shared`)

Domain types are defined in `shared/` (project root) and imported via `@lenie/shared` alias:
- `ApiType` — union type for API backend mode
- `WebDocument` — document form fields interface
- `emptyDocument` — factory constant
- `DEFAULT_API_URLS` — default backend URLs per API type
- `SearchResult`, `ListItem` — API response types

The alias is configured in both `tsconfig.json` (`paths`) and `vite.config.ts` (`resolve.alias`). The local `src/types/index.ts` re-exports shared types and adds app-specific `AuthorizationState`.

See `docs/shared-types.md` for full details.

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

## AWS Deployment

Deploy to S3 + CloudFront (`app.dev.lenie-ai.eu`). The script resolves S3 bucket and CloudFront distribution ID from SSM Parameter Store.

```bash
./deploy.sh                      # Full build + deploy to S3 + CF invalidation
./deploy.sh --skip-build         # Deploy existing build/ only
./deploy.sh --skip-invalidation  # Skip CF cache invalidation
```

SSM parameters used:
- `/${PROJECT_CODE}/${ENVIRONMENT}/s3/app-web/name` — S3 bucket name
- `/${PROJECT_CODE}/${ENVIRONMENT}/cloudfront/app/id` — CloudFront distribution ID

Environment variables: `PROJECT_CODE` (default: `lenie`), `ENVIRONMENT` (default: `dev`), `AWS_REGION` (default: `us-east-1`).

## Docker Build

```
Stage 1: node:24 → npm ci && npm run build (build context is repo root; copies shared/ + web_interface_react/)
Stage 2: nginx:alpine → serve build/ on port 80
Config: nginx.conf with SPA routing (all paths → index.html)
```

Note: The Dockerfile expects the build context to be the repository root (set in `infra/docker/compose.yaml`). It copies `shared/` into `../shared/` relative to the app workdir so Vite can resolve `@lenie/shared`.

## i18n

`react-i18next` and `i18next` are installed as dependencies but not yet configured. UI strings are currently hardcoded in Polish.

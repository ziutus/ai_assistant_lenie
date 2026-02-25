# Shared TypeScript Types

Shared domain types used by both frontend applications (`web_interface_react` and `web_interface_app2`).

## Overview

The `shared/` directory at the project root contains TypeScript type definitions and constants that are common across frontend applications. This avoids duplication of domain types like `WebDocument`, `ApiType`, and default API URLs.

**No build step required** — Vite transpiles shared `.ts` files directly via esbuild. TypeScript resolves imports via `tsconfig.json` paths.

## Directory Structure

```
shared/
├── tsconfig.json           # Standalone type-check config
└── types/
    ├── index.ts            # Barrel re-exports
    ├── api.ts              # ApiType, DEFAULT_API_URLS
    └── documents.ts        # WebDocument, emptyDocument, SearchResult, ListItem
```

## Exported Types and Values

### `api.ts`

| Export | Kind | Description |
|--------|------|-------------|
| `ApiType` | type | `"AWS Serverless" \| "Docker"` — backend deployment mode |
| `DEFAULT_API_URLS` | const | Default backend URLs per API type |

### `documents.ts`

| Export | Kind | Description |
|--------|------|-------------|
| `WebDocument` | interface | Document form fields (id, title, text, metadata, etc.) |
| `emptyDocument` | const | Factory value with all fields set to empty strings/null |
| `SearchResult` | interface | Vector similarity search result |
| `ListItem` | interface | Document list item (id, title, url, state, type) |

## How It Works

Both frontends use the same mechanism to import shared types:

1. **tsconfig.json `paths`** — maps `@lenie/shared/*` to the `shared/` directory (relative to each project)
2. **Vite `resolve.alias`** — maps `@lenie/shared` at build time so Vite/esbuild can resolve and transpile the `.ts` files

### web_interface_react

```json
// tsconfig.json
"baseUrl": ".",
"paths": {
  "@lenie/shared/*": ["../shared/*"]
}
```

```ts
// vite.config.ts
resolve: {
  alias: {
    '@lenie/shared': path.resolve(__dirname, '../shared'),
  },
},
```

The local `src/types/index.ts` re-exports all shared types plus defines the app-specific `AuthorizationState` interface (which depends on React's `Dispatch` type).

### web_interface_app2

```json
// tsconfig.json (baseUrl is ./src, so extra ../)
"@lenie/shared/*": ["../../shared/*"]
```

```ts
// vite.config.ts
'@lenie/shared': path.resolve(__dirname, '../shared'),
```

## What Stays App-Specific

Types that depend on framework-specific imports (React) or app-specific auth flows are NOT in shared:

- `AuthorizationState` (`web_interface_react`) — uses `React.Dispatch`
- `AuthState`, `AuthContextType` (`web_interface_app2`) — specific login flow

## Type-Checking

```bash
# Check shared types standalone (run from a frontend dir that has TypeScript)
cd web_interface_react && npx tsc -p ../shared/tsconfig.json --noEmit

# Check each frontend (includes shared types via tsconfig include)
cd web_interface_react && npm run lint
cd web_interface_app2 && npm run lint
```

## Docker Build

The `web_interface_react` Dockerfile expects the build context to be the repository root. It copies `shared/` before building:

```dockerfile
COPY shared/ ../shared/
COPY web_interface_react/ .
RUN npm run build
```

The `infra/docker/compose.yaml` sets the build context accordingly:

```yaml
lenie-ai-fronted:
  build:
    context: ../..
    dockerfile: web_interface_react/Dockerfile
```

## Adding New Shared Types

1. Add the type/value to the appropriate file in `shared/types/` (or create a new file)
2. Re-export from `shared/types/index.ts`
3. Import in frontends via `@lenie/shared/types`
4. If the frontend has a local re-export layer (like `web_interface_react/src/types/index.ts`), add the re-export there too

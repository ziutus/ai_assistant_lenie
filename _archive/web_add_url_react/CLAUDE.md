# Add URL App (React) — CLAUDE.md

Minimal single-page React application for submitting URLs to the Lenie backend. Unlike the main frontend (`web_interface_react/`), this app does **only one thing** — adds new documents via `POST /url_add`. No routing, no document browsing, no AI tools, no infrastructure controls.

**Version**: 0.2.0

## Directory Structure

```
web_add_url_react/
├── src/
│   ├── index.js              # Entry point (React.StrictMode, no providers/router)
│   ├── App.js                # All logic in one file (form, state, API call)
│   ├── App.css               # App styling (cyan background, flex layout)
│   ├── index.css              # Global font styles
│   ├── App.test.js            # Unit test placeholder
│   ├── reportWebVitals.js     # Performance metrics
│   └── setupTests.js          # Jest setup
├── public/                    # Static assets (index.html, icons, manifest)
├── Dockerfile                 # Multi-stage: node → nginx:alpine (port 80)
├── package.json               # Dependencies & scripts
├── TODO.md                    # Single TODO (environment detection)
└── README.md                  # Standard CRA readme
```

## How It Works

Everything lives in `App.js` (~165 lines). No custom hooks, no components, no context.

### Form Fields

| Field | Type | Visibility |
|-------|------|-----------|
| API URL | text | Always (default: AWS API Gateway endpoint) |
| API Key | text | Always (auto-populated from `?apikey=` query param) |
| URL | text | Always |
| Document type | select: `webpage`, `link`, `youtube`, `movie`, `text_message` | Always |
| Source | text | Always |
| Language | select: `pl`, `en`, `other` | Always |
| Note | textarea | Always |
| Text | textarea | Always |
| Make AI summary | checkbox | Only when type = `youtube` |
| Chapter list | textarea | Only when type = `youtube` or `movie` |

### API Key from URL

The app reads `apikey` from query parameters on load:
```
https://app-url/?apikey=my-secret-key
```
This allows pre-configured bookmarks or links from other tools.

## API Communication

| Property | Value |
|----------|-------|
| **Endpoint** | `POST {apiUrl}/url_add` |
| **Default base URL** | `https://1bkc3kz7c9.execute-api.us-east-1.amazonaws.com/v1` |
| **Auth header** | `x-api-key` |
| **Content-Type** | `application/json` |

### Request Payload

```json
{
  "url": "https://example.com/article",
  "type": "webpage",
  "source": "own",
  "language": "pl",
  "chapterList": "",
  "makeAISummary": false,
  "text": "",
  "note": "User note"
}
```

On success the form auto-clears. On error an alert message is displayed.

## Comparison with `web_interface_react/`

| Aspect | This app | Main frontend |
|--------|----------|---------------|
| **Purpose** | Add URLs only | Full document management |
| **Pages** | 1 (no routing) | 7 routes (React Router v6) |
| **API endpoints** | 1 (`/url_add`) | 19+ |
| **State** | Plain `useState` | AuthContext + Formik |
| **Components** | 1 (`App.js`) | 30+ modular components |
| **Dependencies** | 4 runtime (react, react-dom, axios, web-vitals) | 10+ (+ formik, router, i18next, aws-rum) |
| **Docker** | nginx:alpine (port 80) | node:24.0-slim (port 3000) |

## Dependencies

Minimal stack — React 18, axios, CRA tooling:

```
react@^18.3.1, react-dom@^18.3.1, axios@^1.5.1,
react-scripts@5.0.1, web-vitals@^2.1.4
```

No Router, no state library, no i18n, no form validation library.

## Running

```bash
npm start        # Dev server (port 3000)
npm run build    # Production build (static files in build/)
npm test         # Jest tests
```

## Docker Build

Multi-stage: build with `node:latest`, serve with `nginx:alpine` on port 80.

```dockerfile
FROM node:latest AS build    # npm install + npm run build
FROM nginx:alpine            # Copy build/ to nginx html dir
EXPOSE 80
```

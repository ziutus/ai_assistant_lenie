# Component Inventory — Main Frontend (web_interface_react)

> Generated: 2026-02-13 | Part: web_interface_react | Type: React 18 SPA

## Component Hierarchy

```
AuthorizationProvider
└── BrowserRouter
    └── App (routes)
        └── Layout (sidebar + content)
            ├── Authorization (API config panel)
            └── Page Component
                ├── SharedInputs (common fields)
                ├── InputsForAllExceptLink (content fields + AI tools)
                └── FormButtons (save/delete actions)
```

## Page Components (7)

| Component | Route | Purpose | Unique Features |
|-----------|-------|---------|-----------------|
| `list.jsx` | `/list` | Document list with filtering | Type/state/text filters, delete per item, pagination |
| `search.jsx` | `/search` | Vector similarity search | Dual-path: AWS (2 calls) vs Docker (1 call), translate toggle |
| `link.jsx` | `/link/:id?` | Link document editor | SharedInputs + FormButtons only (no text content) |
| `webpage.jsx` | `/webpage/:id?` | Webpage editor + AI tools | Full editing with split/clean |
| `youtube.jsx` | `/youtube/:id?` | YouTube transcript editor | Chapter list, no clean text button |
| `movie.jsx` | `/movie/:id?` | Movie transcript editor | Chapter list, no clean text button |
| `file.jsx` | `/upload-file` | File upload (alpha) | Direct AWS endpoint, .jpg only |

## Reusable Components (6)

### Layout/Layout.jsx
- **Props**: `children`
- **Renders**: Hamburger menu + fixed sidebar navigation + content area
- **Features**: Responsive, collapsible "Type" submenu, active link highlighting, version display (v0.2.11)

### Authorization/authorization.jsx
- **Props**: None (uses context)
- **Renders**: API configuration panel (3x3 grid)
- **Fields**: API Type (AWS/Docker), Server URL, API Key, SQS Length, DB Status, VPN Status
- **Color coding**: Yellow=unknown, Green=available, Red=stopped

### Input/input.jsx
- **Props**: `id, name, value, label, type, onChange, disabled, multiline, children, className`
- **Renders**: `<input>`, `<textarea>` (if multiline), or `<select>` (if type='select')
- **CSS Module**: Focus border (blue), disabled state, max-height 200px for textarea

### Select/select.jsx
- **Props**: `id, name, value, label, onChange, disabled, children`
- **Renders**: `<select>` dropdown

### SharedInputs/sharedInputs.jsx
- **Props**: `formik, isLoading, handleGetLinkByID, handleGetEntryToReview, handleGetPageByUrl`
- **Fields**: Author, ID + navigation (prev/next), Source, Language, Document State (dropdown), Document State Error, URL + Open/Read, Title, Summary, Tags

### SharedInputs/InputsForAllExceptLink.jsx
- **Props**: `formik, handleSplitTextForEmbedding, handleRemoveNotNeededText, isLoading`
- **Fields**: Markdown content, Website content (with AI buttons), Text stats (length, words, embedding parts), English text, Chapter list, Note
- **AI Tool Buttons**: Split for Embedding, Clean Text

### FormButtons/formButtons.jsx
- **Props**: `message, formik, isError, isLoading, handleSaveWebsiteNext, handleSaveWebsiteToCorrect, handleDeleteDocumentNext`
- **Buttons**: "Zapisz do poprawy" (Save), "Zapisz i następny" (Save & Next), "Usuń" (Delete)

## Custom Hooks (7)

| Hook | Purpose | Key API Calls |
|------|---------|---------------|
| `useManageLLM` | Document CRUD + AI processing | `/website_get`, `/website_save`, `/website_delete`, `/website_split_for_embedding`, `/website_text_remove_not_needed` |
| `useList` | Document list fetching | `/website_list` |
| `useSearch` | Vector similarity search | `/ai_embedding_get` (AWS), `/website_similar` |
| `useDatabase` | RDS start/stop/status | `/infra/database/status\|start\|stop` |
| `useVpnServer` | VPN server control | `/infra/vpn_server/status\|start\|stop` |
| `useSqs` | SQS queue size check | `/infra/sqs/size` |
| `useFileSubmit` | Image file upload | Hardcoded AWS endpoint |

## State Management

### AuthorizationContext (global state)
- **API config**: `apiUrl`, `apiKey`, `apiType` (AWS Serverless / Docker)
- **Infrastructure status**: `databaseStatus`, `vpnServerStatus`, `sqsLength`
- **Document filters**: `selectedDocumentType`, `selectedDocumentState`, `searchInDocument`, `searchType`
- **AWS RUM**: CloudWatch Real User Monitoring (disabled on localhost)

### Formik (form state per page)
All document editing pages use Formik with fields: `id, author, source, language, url, tags, title, summary, text, text_md, text_english, document_type, document_state, document_state_error, chapter_list, note, next_id, previous_id, next_type, previous_type`

## Styling

- **Global**: `index.css` — button styles (blue), loader animation, error text (red), flex utilities
- **CSS Modules**: Per-component `.module.css` files for layout, authorization, input, select
- **No design system**: Custom CSS, no component library

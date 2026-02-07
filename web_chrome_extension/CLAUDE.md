# Browser Extension — CLAUDE.md

Chrome/Kiwi browser extension for capturing webpages and sending them to the Lenie AI backend. No build step — load unpacked directly from this folder.

**Version**: 1.0.22 | **Manifest**: v3

## Directory Structure

```
web_chrome_extension/
├── manifest.json          # Extension manifest (permissions, icons, popup)
├── popup.html             # Popup UI (2 tabs: Add + Settings)
├── popup.js               # All extension logic (extraction, API calls, storage)
├── bootstrap.min.css      # Bootstrap styling (local, no CDN)
├── icon16.png             # Toolbar icon 16x16
├── icon48.png             # Extension page icon 48x48
├── icon128.png            # Chrome Web Store icon 128x128
├── README.md              # Documentation (Polish)
├── CHANGELOG.md           # Version history
└── .gitignore             # Excludes .idea/
```

## Features

1. **URL capture** — grabs current page URL from the active tab
2. **Metadata extraction** — auto-detects title (`document.title`), description (`<meta name="description">`), language (`<html lang>` or `navigator.language`)
3. **Content extraction** — captures full page text (`innerText`) and HTML (`outerHTML`) via `chrome.scripting.executeScript()`
4. **Content type classification** — `webpage` (default), `link`, `youtube`, `movie`
5. **YouTube detection** — auto-switches type to `youtube` when URL matches `youtube.com/watch`, shows chapter list field
6. **Source tracking** — dropdown with predefined sources (Own, Maruda, Tomasz Szer, Rafał Skonieczko)
7. **Paywall flag** — boolean Yes/No radio buttons
8. **Notes & chapters** — free-text note field, chapter list (visible for YouTube only)

## Popup UI

Two-tab interface (~500px wide):

| Tab | Content |
|-----|---------|
| **Dodaj** (Add) | Form: title, description, note, type, source, paywall, language, chapter list, Send button |
| **Ustawienia** (Settings) | API key (password field with visibility toggle), server URL |

## API Communication

| Property | Value |
|----------|-------|
| **Default endpoint** | `https://jg40fjwz61.execute-api.us-east-1.amazonaws.com/v1/url_add` |
| **Method** | `POST` |
| **Auth header** | `x-api-key` |
| **Content-Type** | `application/json` |

### Request Payload

```json
{
  "url": "https://example.com/article",
  "title": "Page Title",
  "text": "Full page text (innerText)",
  "html": "Full page HTML (outerHTML)",
  "language": "pl",
  "type": "webpage",
  "source": "own",
  "paywall": false,
  "note": "User note",
  "chapter_list": ""
}
```

The endpoint corresponds to `/url_add` in `backend/server.py` (Docker/K8s) or the `sqs-weblink-put-into` Lambda function (AWS serverless).

### Error Handling

- Validates API key and server URL are not empty before sending
- Shows alert with HTTP status and error message on failure
- Button disabled with "Wysyłam..." (Sending...) text during request
- Popup auto-closes 500ms after successful submission

## Permissions

| Permission | Reason |
|------------|--------|
| `storage` | Persist API key and server URL in `chrome.storage.sync` |
| `activeTab` | Access the currently viewed tab |
| `tabs` | Query tab URL and title |
| `scripting` | Inject content extraction scripts into pages |

CSP: `script-src 'self'; style-src 'self' 'unsafe-inline'; object-src 'self'`

## Storage

Uses `chrome.storage.sync` (encrypted by Chrome, synced across profiles):
- `apiKey` — API authentication key
- `serverUrl` — backend endpoint URL

## Installation

No build step required. Load as unpacked extension:

1. Open `chrome://extensions/`
2. Enable **Developer mode** (top right)
3. Click **Load unpacked**
4. Select the `web_chrome_extension/` folder

Works on **Chrome** (desktop) and **Kiwi Browser** (Android, Chrome-compatible).

## Data Flow

1. `DOMContentLoaded` → load saved settings, query active tab, detect YouTube, extract metadata
2. User fills in form fields (most pre-populated)
3. Click **Wyślij** (Send) → extract page text+HTML via `chrome.scripting.executeScript()`
4. Build JSON payload → POST to server with `x-api-key` header
5. Success → close popup; Error → show alert with details

# Architecture — Browser Extension (web_chrome_extension)

> Generated: 2026-02-13 | Part: web_chrome_extension | Type: Chrome Extension (Manifest v3)

## Architecture Pattern

**Single-file popup** with two-tab interface. No build step, no framework, vanilla JavaScript.

## Technology Stack

| Category | Technology |
|----------|-----------|
| Platform | Chrome Extension Manifest v3 |
| Language | JavaScript (ES6+, vanilla) |
| Styling | Bootstrap CSS (local copy) |
| Storage | chrome.storage.sync |
| APIs | chrome.scripting, chrome.tabs, chrome.storage |

## Application Architecture

### Data Flow

```
1. DOMContentLoaded → load saved settings → query active tab → detect YouTube → extract metadata
2. User fills in form fields (most pre-populated)
3. Click "Wyślij" → chrome.scripting.executeScript() extracts page text+HTML
4. Build JSON payload → POST to server with x-api-key header
5. Success → close popup; Error → show alert
```

### UI Structure

Two-tab interface (~500px wide):

**Tab 1: "Dodaj" (Add)**
- Title (auto-extracted), Description (meta tag), Note (free text)
- Type dropdown (webpage, link, youtube, movie)
- Source dropdown (Own, Maruda, Tomasz Szer, Rafał Skonieczko)
- Paywall flag (Yes/No), Language field
- Chapter list (visible for YouTube only)
- Send button

**Tab 2: "Ustawienia" (Settings)**
- API key (password with visibility toggle)
- Server URL (default: AWS API Gateway endpoint)

### State Management

- **Persistent**: `chrome.storage.sync` — API key, server URL
- **Session**: DOM state — form fields populated from active tab metadata

### Content Extraction

Uses `chrome.scripting.executeScript()` to inject into active tab:
- `document.title` → title
- `<meta name="description">` → description
- `<html lang>` or `navigator.language` → language
- `document.documentElement.innerText` → full page text
- `document.documentElement.outerHTML` → full page HTML

### API Communication

- **Endpoint**: `POST {serverUrl}` (default: AWS API Gateway `/url_add`)
- **Auth**: `x-api-key` header
- **Content-Type**: `application/json`
- **Payload**: url, title, text, html, language, type, source, paywall, note, chapter_list

### Permissions

| Permission | Reason |
|------------|--------|
| storage | Persist API key and server URL |
| activeTab | Access current tab |
| tabs | Query tab URL and title |
| scripting | Inject content extraction scripts |

## Version History

Current: 1.0.22 (2025-08-29). Key milestones:
- 1.0.22: Removed AI summary/correction fields (auto-handled by backend)
- 1.0.18: Tab-based UI, password-type API key
- 1.0.16: Automatic language detection

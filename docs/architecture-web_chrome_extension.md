# Architecture — Browser Extension (web_chrome_extension)

> Generated: 2026-02-13 | Part: web_chrome_extension | Type: Chrome Extension (Manifest v3)
>
> **Uwaga (2026-07-22):** Popup/data-flow/permissions poniżej są prawdopodobnie wciąż aktualne. "Server URL (default: AWS API Gateway endpoint)" odzwierciedla dziś nieaktywny tor AWS (patrz `docs/aws-roadmap.md`) — docelowo powinien wskazywać na NAS, ale nie jest to jeszcze zmienione w kodzie (patrz otwarty wątek dostępu zdalnego w `docs/deployment/`). Zweryfikuj względem [`web_chrome_extension/CLAUDE.md`](../web_chrome_extension/CLAUDE.md) przed poleganiem na tym pliku.

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

- **Persistent**: `chrome.storage.sync` — NAS API key, AWS API key, NAS URL, AWS URL
- **Session**: DOM state — form fields populated from active tab metadata

### Content Extraction

Uses `chrome.scripting.executeScript()` to inject into active tab:
- `document.title` → title
- `<meta name="description">` → description
- `<html lang>` or `navigator.language` → language
- `document.documentElement.innerText` → full page text
- `document.documentElement.outerHTML` → full page HTML

### API Communication

- **Endpoints**: `POST {localServerUrl}` (NAS, preferred) and `POST {serverUrl}` (AWS fallback)
- **Routing**: the extension probes NAS with `OPTIONS /url_add`; if NAS is unavailable before the write it uses AWS.
- **Retry safety**: each submission gets one `external_uuid`. The extension does not retry an uncertain POST against the other backend because NAS and AWS have separate databases and such a retry could create two documents.
- **Auth**: `x-api-key` header
- **Content-Type**: `application/json`
- **Payload**: url, title, text, html, language, type, source, paywall, note, chapter_list

The settings keep the two full `/url_add` URLs and two API keys separately. Existing installations that only have `serverUrl` and `apiKey` stored migrate the old key to both fields; the NAS field gets its default local address. The user can then replace the NAS key independently.

### Permissions

| Permission | Reason |
|------------|--------|
| storage | Persist NAS/AWS API keys and server URLs |
| activeTab | Access current tab |
| tabs | Query tab URL and title |
| scripting | Inject content extraction scripts |

## Version History

Current: 1.0.39 (2026-07-29). Key milestones:
- 1.0.40: Prefer NAS `/url_add` on the local network and fall back to AWS when NAS is unavailable; separate credentials per backend
- 1.0.22: Removed AI summary/correction fields (auto-handled by backend)
- 1.0.18: Tab-based UI, password-type API key
- 1.0.16: Automatic language detection

# Platform Challenges & Workarounds

This document collects real-world challenges encountered while building Project Lenie — a personal AI assistant that downloads, processes, and indexes content from various sources. Each entry documents the problem, root cause, current workaround, and potential long-term fix.

This is also intended as **presentation material** — the challenges below illustrate how modern platforms protect their content and what technical barriers exist for legitimate personal archiving and AI processing.

## Content Acquisition Challenges

### YouTube — IP Blocking & Regional Restrictions

**Problem:** YouTube aggressively blocks automated caption/video downloads. Requests from data center IPs or repeated requests from the same IP get blocked with HTTP 403 or CAPTCHA challenges. The `youtube-transcript-api` and `pytubefix` libraries frequently fail.

**Root cause:** YouTube's anti-bot systems detect non-browser traffic patterns. Residential IPs work longer but eventually get throttled too.

**Current workaround:**
- **Proxy rotation via Webshare** — `WEBSHARE_API_KEY` configures rotating residential proxies for YouTube requests
- **Fallback chain:** `pytubefix` → `yt-dlp` for video download
- **Caption-first strategy:** Always try free captions before paid transcription (AssemblyAI)

**Status:** Working but fragile. Proxy costs ~$5/month. Libraries need frequent updates as YouTube changes its API.

**References:** [ADR-007](adr/adr-007-pytubefix-lambda-exclusion.md) (pytubefix excluded from Lambda due to size), [ADR-011](adr/adr-011-assemblyai-sole-transcription.md) (AssemblyAI as sole transcription provider)

---

### Polish News Sites (wp.pl, Onet, TVN24) — JavaScript-Only Video Players

**Problem:** Video content on major Polish news portals cannot be extracted with standard HTTP requests. Discovered on 2026-04-01 when attempting to transcribe a 10-minute video from `wiadomosci.wp.pl`.

**Root cause:** Video players are fully JavaScript-rendered (no `<video>` tags or direct URLs in HTML). The video stream URLs are loaded dynamically via encrypted/tokenized API calls that require active browser session. Even `yt-dlp` (which supports 1800+ sites) returns `Unsupported URL` for wp.pl.

**What was tried:**
1. `yt-dlp` — no extractor for wp.pl (`ERROR: Unsupported URL`)
2. HTML scraping — found embed UUIDs (`filerepo.grupawp.pl/api/v1/display/embed/{uuid}`) but the API requires session tokens
3. Direct API probing (`video.wp.pl`, `wideo.wp.pl`) — 404 responses

**Current workaround:** Manual extraction via browser DevTools:
1. Open the page in Chrome
2. DevTools → Network tab → filter by `mp4` or `m3u8`
3. Play the video → copy the stream URL
4. Feed the URL to AssemblyAI for transcription

**Potential long-term fix:**
- **Playwright/Selenium automation** — headless browser to extract stream URLs programmatically
- **Browser extension enhancement** — extend the Chrome extension to capture video URLs from the page
- Support `movie` document type in the processing pipeline (currently schema-only, no processing logic)

**Affected sites:** wp.pl, likely also Onet, Interia, Polsat News (similar player technology)

---

### Facebook — Aggressive Anti-Scraping

**Problem:** Facebook content (posts, videos, public pages) is extremely difficult to access programmatically. Even public posts require authentication to view full content.

**Root cause:** Facebook employs multiple layers of protection:
- **Login walls** — most content hidden behind authentication, even "public" posts show limited preview
- **Dynamic rendering** — all content loaded via React/GraphQL, no meaningful HTML in initial response
- **Rate limiting** — aggressive throttling of automated requests
- **Device fingerprinting** — tracks browser characteristics, detects headless browsers
- **Legal enforcement** — actively pursues scrapers via cease-and-desist and lawsuits (Meta v. Bright Data, 2024)

**Current workaround:** None implemented. Facebook content is currently out of scope.

**Potential approaches (not implemented):**
- Official Graph API (limited to pages you admin)
- Manual copy-paste for individual posts
- Browser extension capturing page content while browsing

---

### LinkedIn — Professional Content Protection

**Problem:** LinkedIn content (articles, posts, profiles) cannot be scraped without authentication. Even with authentication, scraping violates ToS and triggers account restrictions.

**Root cause:** LinkedIn's protection includes:
- **Strict authentication requirement** — no anonymous access to any content
- **Session-based rate limiting** — monitors request patterns per logged-in user
- **CAPTCHA challenges** — triggered by unusual browsing patterns
- **Account suspension** — automated detection of scraping behavior, temporary or permanent bans
- **Legal precedent** — hiQ Labs v. LinkedIn (US Supreme Court, 2022) — public data scraping is legal but LinkedIn still blocks it technically
- **Anti-bot JS** — client-side fingerprinting detects automation tools

**Current workaround:**
- **Apify integration** (`APIFY_API_TOKEN`) — third-party service for LinkedIn profile scraping, used in `backend/test_code/linkedin_profile.py`
- Cost: Apify pay-per-result model

**Potential approaches:**
- LinkedIn API (very limited scope, requires app approval)
- Browser extension capturing content during normal browsing

---

### Paywalled Content (General)

**Problem:** Many high-quality sources (news, research papers, reports) are behind paywalls. The system downloads only the free preview, missing the actual content.

**Root cause:** Publishers use client-side or server-side paywall enforcement. Some use "metered" paywalls (N free articles/month), others are hard paywalls.

**Current workaround:**
- **Firecrawl** (`FIRECRAWL_API_KEY`) — third-party scraping service that can bypass some soft paywalls
- For sites the user has subscriptions to — manual copy-paste or browser extension

**Potential approaches:**
- Browser extension capturing full content after login
- Cache content from RSS feeds (often includes full text)

---

### Anti-Bot / Rate Limiting (General)

**Problem:** Many websites detect and block automated content extraction. This manifests as HTTP 403, CAPTCHAs, empty responses, or IP bans.

**Root cause:** Standard HTTP client libraries (`requests`, `urllib`) send identifiable headers and lack JavaScript execution. CDN-level protection (Cloudflare, Akamai) blocks non-browser traffic.

**Current workaround:**
- **User-Agent rotation** — mimic browser headers
- **Webshare proxy** — rotate IP addresses
- **Firecrawl fallback** — cloud-based scraping with browser rendering
- **Beautiful Soup + Markdownify** — primary extraction chain, falls back to Firecrawl on failure

**Extraction priority chain:** Beautiful Soup → Markdownify → Firecrawl (configurable per site via `backend/data/` cleanup rules)

---

## Transcription Challenges

### Cost Management (AssemblyAI)

**Problem:** Audio/video transcription costs $0.12/hour via AssemblyAI. For a personal project, costs can accumulate quickly with many YouTube videos.

**Current approach:**
- **Caption-first strategy** — always try free YouTube captions before paid transcription
- **Budget tracking** — `TRANSCRIPTION_BALANCE_USD` config, `/transcription_usage` endpoint, `transcription_log` DB table
- **Manual approval** — transcription only triggered when `transcript_needed=True` is set on the document

**References:** [ADR-011](adr/adr-011-assemblyai-sole-transcription.md)

---

### Language Detection for Transcription

**Problem:** AssemblyAI needs a language hint for best results. Documents may not have correct language metadata.

**Current approach:**
- `YOUTUBE_DEFAULT_LANGUAGE` config (default: `pl`)
- Per-document `language` field in database
- AWS Comprehend for text language detection (`text_detect_language_aws.py`)

---

## Infrastructure Challenges

### Vault Data Loss After NAS Restart (Resolved 2026-04-01)

**Problem:** HashiCorp Vault on QNAP NAS lost all data after NAS restart. Vault appeared uninitialized after each reboot.

**Root cause:** Docker Compose volume mounts pointed to `/share/vault/` which is a non-persistent path on QNAP. After restart, NAS recreates empty directories at `/share/vault/`.

**Fix applied:**
1. Changed volume paths in `compose.nas.yaml`: `/share/vault/*` → `/share/Container/vault/*` (persistent QNAP path)
2. Enabled **AWS KMS auto-unseal** — Vault automatically unseals using KMS key on konto 639394817995, eliminating manual unseal after restart
3. Re-synced secrets from AWS SSM (us-east-1) to Vault using `env_to_vault.py sync`

**References:** [Vault_Setup.md](CICD/Vault_Setup.md), [NAS_Deployment.md](CICD/NAS_Deployment.md)

---

### Lambda VPC Networking — No Internet Access

**Problem:** Lambda functions inside VPC (for RDS access) cannot reach the internet. Adding a NAT Gateway costs ~$30/month.

**Current workaround:** Split Lambda into two functions:
- `app-server-db` — inside VPC, database access only
- `app-server-internet` — outside VPC, internet access only

**References:** [ADR-006](adr/adr-006-separate-infra-api-gateway.md)

---

## Summary: Protection Mechanisms by Platform

| Platform | Auth Required | JS Rendering | Rate Limiting | Anti-Bot | Legal Risk | yt-dlp Support |
|----------|:---:|:---:|:---:|:---:|:---:|:---:|
| YouTube | No* | No | High | High | Low | Yes |
| wp.pl | No | Yes | Low | Medium | Low | No |
| Facebook | Yes | Yes | High | Very High | High | Partial |
| LinkedIn | Yes | Yes | High | Very High | Medium | No |
| Paywalled sites | Subscription | Varies | Medium | Medium | Low | N/A |
| Standard websites | No | Varies | Low-Medium | Low-Medium | Low | N/A |

\* YouTube doesn't require auth but blocks automated access aggressively


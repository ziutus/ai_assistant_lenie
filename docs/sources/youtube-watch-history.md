# YouTube Watch History — Research Summary

> **Date:** 2026-03-15
> **Status:** Investigated, no integration planned
> **Context:** Evaluated as potential content source for Lenie AI

## Goal

Automatically import YouTube watch history into Lenie to review recently watched videos and selectively add interesting ones for further processing (transcription, summarization, embedding).

## Conclusion

**No feasible automated solution exists.** YouTube watch history will remain a manual source — the user finds interesting videos in YouTube's native history and adds them to Lenie individually (via Chrome extension or CLI).

## Why YouTube Watch History Is Not Accessible

### YouTube Data API v3

- The `activities.list` endpoint (which once provided watch history) was **deprecated and removed** by Google years ago, citing privacy concerns.
- **No replacement endpoint exists** for reading watch history programmatically.
- Available endpoints cover: subscriptions, playlists (including "Liked videos"), channel info — but **not** watch history.

### Google Takeout

- Exports `watch-history.json` with title, URL, channel name, and timestamp per video.
- **Minimum export frequency: every 2 months** — far too infrequent for a "review yesterday's videos" workflow.
- Manual one-time exports are possible but require clicking through the Takeout UI each time.
- No API for triggering exports programmatically.

### Google Workspace CLI (`gws`)

- Does not include a YouTube skill — YouTube is not part of Google Workspace APIs.
- Covers: Gmail, Drive, Calendar, Sheets, Slides, Docs, Admin, Keep, Chat, Meet, Tasks, Contacts.

### Browser Extension Approach

- Could intercept YouTube video views in real-time and send to Lenie.
- **Problem:** The user primarily watches YouTube on mobile (phone) using the native YouTube app, not a browser. Chrome extensions don't run inside the YouTube mobile app.

### Scraping `myactivity.google.com`

- Technically possible but violates Google's Terms of Service.
- Fragile — UI changes break scrapers.

## What IS Available via YouTube Data API

| Endpoint | Data | Useful? |
|----------|------|---------|
| `subscriptions.list` | Subscribed channels | Already covered by `feeds.yaml` (`youtube_channel` type) |
| `playlistItems.list` (playlist=LL) | Liked videos | Possible future source |
| `playlists.list` | User's playlists | Possible future source |
| `search.list` | Search results | Not relevant |

## Current Workflow (Manual)

1. User watches videos on mobile in the native YouTube app
2. When a video is interesting, user finds it in YouTube history
3. User adds it to Lenie via Chrome extension (`web_chrome_extension/`) or discusses it in a Claude Code session
4. Lenie processes: download transcript, generate summary, create embeddings

This manual approach is acceptable given the constraints. The friction is low — only videos worth keeping need to be added, and the Chrome extension already supports YouTube URLs.

## References

- [YouTube Data API v3 — Activities (deprecated)](https://developers.google.com/youtube/v3/docs/activities)
- [Google Takeout](https://takeout.google.com/)
- [Google Workspace CLI](https://github.com/googleworkspace/cli) — no YouTube support
- [Takeout watch history format](https://portmap.dtinit.org/articles/watch-history2.md/)

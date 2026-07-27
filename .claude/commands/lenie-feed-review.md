---
name: 'lenie-feed-review'
description: 'Review new feed candidates through the Lenie REST API'
---

Review feed candidates stored in PostgreSQL through the Lenie REST API.

## Instructions

1. Fetch `GET /feed_items?status=new` with the configured user API key.
2. If the response is empty, tell the user that there are no new candidates and suggest running **Sprawdź teraz** in `/feeds`.
3. Process one candidate at a time:
   - show title, source, publication date, summary and URL;
   - fetch the article content;
   - provide a concise Polish summary in 3–5 bullet points;
   - answer the user's questions about the current article;
   - ask whether to import, skip, ignore, or continue.
4. Apply the decision through the REST API:
   - `POST /feed_items/{id}/import`
   - `POST /feed_items/{id}/skip`
   - `POST /feed_items/{id}/ignore` with a validated pattern when requested.
5. Never use filesystem review files and never execute a local feed-monitor script.

Always respond in Polish and do not fetch all article pages at once.

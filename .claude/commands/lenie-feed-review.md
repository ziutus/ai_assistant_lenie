---
name: 'lenie-feed-review'
description: 'Review new feed candidates through the Lenie REST API'
---

Review feed candidates stored in PostgreSQL through the Lenie REST API.

## Instructions

1. Fetch `GET /feed_items?status=new` with the configured user API key. A candidate can be deferred with `POST /feed_items/{id}/save-for-later`; fetch deferred candidates with `GET /feed_items?status=saved_for_later`.
2. If the response is empty, tell the user that there are no new candidates and suggest running **Sprawdź teraz** in `/feeds`.
3. Process one candidate at a time:
   - show title, source, publication date, summary and URL;
   - fetch the article content;
   - provide a concise Polish summary in 3–5 bullet points;
   - check whether the text is really about a PAID tool or product (pricing page, "free trial", licence, subscription, affiliate/referral links, the recommender is the vendor or sells it) even though the feed presents it as a neutral recommendation or a free resource; say so explicitly in the summary ("opisuje płatne narzędzie: <nazwa>, <cena/model>") and note that the recommender may not have verified the text. Reference example: feed item 12501 (source 1, `Do przeczytania`), whose text turned out to describe a paid tool. Read the user's own comment (`review_note` of `GET /feed_items/{id}`) first: it may already carry such a verdict;
   - answer the user's questions about the current article;
   - ask whether to import, skip, ignore, or continue.
4. Apply the decision through the REST API:
   - `POST /feed_items/{id}/import`
   - `POST /feed_items/{id}/skip`
   - `POST /feed_items/{id}/ignore` with a validated pattern when requested;
   - `POST /feed_items/{id}/restore` to return a deferred candidate to `new`.
5. Never use filesystem review files and never execute a local feed-monitor script.

Always respond in Polish and do not fetch all article pages at once.

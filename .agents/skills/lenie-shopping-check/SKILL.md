---
name: 'lenie-shopping-check'
description: 'Before buying something, check Lenie for a stored discount code/coupon/loyalty note relevant to the shop or product'
---

Before the user buys something, check whether Lenie's library already holds a note about a discount code, coupon, or loyalty deal for that shop — so a saved coupon (e.g. from a flyer, an email, a card insert) actually gets used instead of forgotten.

This is a **read-only lookup** through Lenie's REST `POST /search`. It never creates, edits, or deletes any document — if a genuinely new coupon needs to be recorded, say so and ask the user whether to create that note separately (that's a different task).

## Input

One or both of:
- a shop reference: a name (e.g. "Allegro", a seller name), or a URL — including an Allegro seller/offer URL like `https://allegro.pl/uzytkownik/<seller_name>`, from which the seller name is the shop identifier;
- what the user intends to buy (product/category), e.g. "papier do drukarki".

If only a product is given with no shop, still search — a stored coupon note may name the shop itself and match on the product/category text.

## Runtime and API configuration

This is the shared procedure for Claude Code and Codex. Use `LENIE_API_KEY` from the agent environment for the NAS API (service key; see `[[reference_lenie_api_key]]` in memory). Never print it or store it in this repository. If missing, ask the user to configure it.

Base URL: `http://192.168.200.7:5055`.

The curl examples below are **Bash examples only**. In PowerShell use `$env:LENIE_API_KEY` and `Invoke-RestMethod`:

```powershell
$headers = @{ 'x-api-key' = $env:LENIE_API_KEY }
$body = @{ natural_query = 'kupon rabat kod rabatowy Raptor_Print Allegro' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://192.168.200.7:5055/search' -Headers $headers `
  -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

Lenie's NAS deployment is occasionally paused/offline for maintenance. If the request fails to connect or times out, tell the user plainly that Lenie is unreachable right now and stop — do not guess at an answer, and do not retry more than once.

## Workflow

### Step 1: Build the search query

Compose a Polish `natural_query` combining:
- the shop identifier (name as given, or the seller slug from an Allegro/marketplace URL, e.g. `Raptor_Print`);
- generic discount terms: `kupon`, `rabat`, `kod rabatowy`;
- the product/category, if given.

Example: shop `Raptor_Print` (Allegro), product "papier" → `natural_query: "kupon rabat kod rabatowy Raptor_Print Allegro papier"`.

### Step 2: Query Lenie

```bash
curl -s -H "x-api-key: $LENIE_API_KEY" -H "Content-Type: application/json" \
  -X POST "http://192.168.200.7:5055/search" \
  -d '{"natural_query": "<query built in Step 1>"}'
```

Read `results` from the response. If empty and the query included a product term, retry once with just the shop + discount terms (drop the product) — a coupon note may not mention the specific item.

### Step 3: Report findings

For every result that plausibly names a discount/coupon (not just any document that happens to mention the shop):

- state the shop it applies to, the code/percentage, and any condition mentioned in the text (e.g. "wpisz w uwagach do zamówienia", minimum order, validity date);
- **quote the condition/code text as stored** — never paraphrase a discount code or a percentage, and never infer an expiry date that isn't explicitly in the text;
- give the document link: `http://192.168.200.7:3000/webpage/<id>` (use the result's document id).

If nothing plausible turns up, say so plainly in Polish (e.g. "Nie znalazłem zapisanego kuponu/rabatu dla <sklep>") — do not fabricate a discount and do not assume one doesn't exist just because this specific product wasn't mentioned.

### Step 4: Offer the follow-up, don't do it

If no note was found and the user says they do have an unrecorded coupon, note that this skill is lookup-only and ask whether to create the coupon note now (separate action, not part of this skill).

## Important

- All communication with the user in **Polish**.
- Read-only against Lenie: only `POST /search` is called, nothing is written.
- Never invent or round a discount code, percentage, or expiry date — report exactly what the matched document's text says, or say nothing was found.
- Treat a connection failure to the NAS backend as "Lenie unavailable right now", not as "no coupon exists".

# Lenie NER Service

Internal-only microservice that wraps spaCy's Polish NER model (`pl_core_news_lg`)
behind a minimal HTTP API. Split out from `backend/` so the main backend image
doesn't carry the ~600MB spaCy model, and so the model can be redeployed
independently of the rest of the backend.

Not reachable from outside the `lenie-net` Docker network — no port is
published to the NAS host. Only other containers on `lenie-net` (currently:
`lenie-ai-server`) can reach it, by container name (`lenie-ner-service:8090`).
No authentication — network isolation is the only access control, matching
the internal-only threat model.

See [`../docs/geo-place-ner-plan.md`](../docs/geo-place-ner-plan.md) and
[`../docs/person-ner-plan.md`](../docs/person-ner-plan.md) for the broader
plan this service is the first step of (place/person entity extraction and
tagging — not yet wired into the backend's tagging pipeline).

## API

`GET /healthz` — `{"status": "ok"}`

`POST /ner` — body `{"text": "..."}`, returns:

```json
{
  "entities": [
    {"text": "Donald Tusk", "label": "persName", "start": 0, "end": 11},
    {"text": "Cieśninie Ormuz", "label": "geogName", "start": 20, "end": 35}
  ]
}
```

Labels come directly from `pl_core_news_lg`: `persName`, `geogName`,
`placeName`, `orgName`, `date`, `time`, etc.

## Local development

```bash
uv sync
uv run python -m spacy download pl_core_news_lg
uv run python -m src.main
```

## Testing

```bash
uv run pytest tests/
```

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

See [`../docs/ner-integration-plan.md`](../docs/ner-integration-plan.md) for
how this service is wired into the backend (client: `backend/library/ner_client.py`,
storage: `document_entities` table, UI panel in `web_interface_react`), and
[`../docs/geo-place-ner-plan.md`](../docs/geo-place-ner-plan.md) /
[`../docs/person-ner-plan.md`](../docs/person-ner-plan.md) for the broader
place/person verification plans this service is the first step of.

## API

`GET /healthz` — `{"status": "ok"}`

`POST /ner` — body `{"text": "..."}`, returns:

```json
{
  "entities": [
    {"text": "Donald Tusk", "label": "persName", "lemma": "Donald Tusk", "start": 0, "end": 11,
     "pos": "PROPN", "morph": "Case=Nom|Gender=Masc|Number=Sing"},
    {"text": "Cieśninie Ormuz", "label": "geogName", "lemma": "cieśnina Ormuz", "start": 20, "end": 35,
     "pos": "PROPN", "morph": "Case=Loc|Gender=Neut|Number=Sing"}
  ]
}
```

Labels come directly from `pl_core_news_lg`: `persName`, `geogName`,
`placeName`, `orgName`, `date`, `time`, etc. `lemma` is the base form of the
mention (spaCy lemmatizer) — callers use it to group inflected Polish variants
of the same name ("Tuska" → "Tusk"). `pos` and `morph` describe the root token
of the entity span (`ent.root`); they let callers reject false positives whose
syntactic head is not nominal. They are additive fields, so existing clients
that only consume the original fields remain compatible.

The model is loaded lazily on the first `/ner` call (not at startup), so
`/healthz` responds immediately even before it's loaded — but that first
`/ner` call pays the one-time load cost, which on the NAS (Celeron, cold
disk cache after a container restart) has been observed to take up to
~60-90s. Callers should set a generous timeout on the first request after
a deploy/restart; subsequent calls are sub-second.

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

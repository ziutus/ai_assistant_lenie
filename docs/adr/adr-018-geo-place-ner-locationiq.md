# ADR-018: Geographic Place Tagging — spaCy NER + LocationIQ Verification

**Date:** 2026-07-10
**Status:** Accepted
**Decision Makers:** Ziutus
**Full analysis:** [geo-place-ner-plan.md](../geo-place-ner-plan.md)

### Context

Country tagging (`country_gazetteer.detect_countries()`) works because countries
are a closed, ~197-item list that can be matched by word-stem lookup. Articles
also regularly mention non-country places that carry context (straits, seas,
disputed regions, mountain ranges, strategic cities — e.g. Cieśnina Ormuz,
Morze Czerwone, Górski Karabach) that a gazetteer approach can't cover: there
are tens of thousands of them, so a hand-maintained list would always be
incomplete. This requires genuine Named Entity Recognition instead of list
matching, plus a way to confirm a candidate string is a real geographic
feature before spending LLM tokens judging its relevance.

Two axes needed a decision:
1. Which NER model extracts place candidates from Polish text.
2. How to verify a candidate resolves to a real OSM place (fact-check) before
   the LLM judges whether it's actually discussed in the article.

### Decision

1. **NER model: spaCy `pl_core_news_lg`**, not HerBERT (Allegro, transformer-based).
   spaCy's Polish model natively distinguishes `geogName` (geographic features —
   exactly what's needed) from `placeName` (administrative places), runs on CPU
   in a fraction of a second to ~2s per article, and needed no new hardware on
   the existing NAS (Celeron, no GPU). HerBERT would need a GPU for reasonable
   throughput.
2. **Verification: hosted LocationIQ API** (Nominatim-compatible, 5,000
   free requests/day), not a self-hosted Nominatim/Photon instance. Existence-
   in-OSM is a deterministic yes/no question, cheaper to answer via geocoder
   than via LLM judgment. Self-hosting a full planet Nominatim needs ~800GB
   disk (or ~95GB for Photon, the lighter alternative) — unjustified at the
   article-candidate volumes involved.
3. Pipeline order stays **NER → verify (LocationIQ) → LLM relevance** — the LLM
   only evaluates already-confirmed candidates for whether they're substantively
   discussed, not whether they exist.

### Rationale

- **No new hardware required.** Both choices run on the existing NAS
  (QNAP TS-453Be, Celeron, x86_64, no GPU) — the deciding factor given this is
  a self-hosted personal project, not a funded infra budget.
- **Deterministic checks belong to the cheapest deterministic tool.** Whether a
  string resolves to a real OSM place is a fact, not a judgment call — routing
  it to a geocoder instead of an LLM call saves tokens and is more reliable.
- **spaCy's label scheme matches the problem for free.** `geogName` vs
  `placeName` is exactly the "is this a geographic feature" distinction needed,
  with no extra classification step.
- **LocationIQ over self-hosted Nominatim/Photon, for now.** The free tier
  comfortably covers realistic volume (tens of candidates per article, async
  batch processing); self-hosting is deferred until volume actually justifies
  the disk/ops cost, and Photon (~95GB) is the cheaper self-host path if that
  day comes.

### Consequences

- **Positive:** Implemented without any hardware purchase; ran on the existing NAS.
- **Positive:** `geogName`/`placeName` split removes a classification step that
  a generic `LOC`/`GPE` model would have required.
- **Negative:** Dependent on a third-party hosted API (LocationIQ) and its
  pricing/limits — self-hosting is the documented fallback if that stops being
  viable.
- **Deferred:** HerBERT NER (higher accuracy, needs GPU) remains a possible
  upgrade if spaCy's quality proves insufficient in practice — at that point a
  consumer-class GPU (RTX 3060/4060, 12GB) is sufficient, no data-center hardware.

### Related Artifacts

- [geo-place-ner-plan.md](../geo-place-ner-plan.md) — full model/API comparison, hardware requirement tables, hosted-geocoder pricing survey
- [ner-integration-plan.md](../ner-integration-plan.md) (stage 3) — implementation details: `ner_service/`, `document_entities`/`geocode_cache` tables, `miejsce-*` tags, map markers in `/read/:id`
- `backend/library/locationiq_client.py`, `backend/library/place_verification.py`, `backend/library/place_context_classifier.py` — implementation
- `backend/database/init/21-create-document-entities.sql`, `22-create-geocode-cache.sql` — schema

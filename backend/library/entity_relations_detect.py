"""Document extraction: closed registry candidates, bounded parallel calls, proposals only."""

from collections import Counter

from sqlalchemy import select

from library import app_settings
from library.country_gazetteer import detect_countries
from library.db.models import Document, DocumentEntity, DocumentPerson, Organization, OrganizationAlias, PersonAlias
from library.entity_relation_vocabulary import PIPELINE_TYPES
from library.entity_relations_service import (
    PROJECTIONS, RelationError, document_endpoints, endpoint, relations_for_document, upsert_relation,
)
from library.entity_text import document_ner_text
from library.llm_parallel import map_llm_calls
from library.llm_usage.context import document_usage_context
from library.llm_usage.report import combine_usage_reports
from library.relation_extraction import PROMPT_VERSION, chunk_text, extract_relations, normalized

TASK = "relation_extraction"
SETTING_KEY = "relation_extraction_model"
DEFAULT_MODEL = "openrouter/google/gemma-4-31b-it"


def model_capabilities(model):
    """How to call a model: real system role and JSON-schema answers, where the provider supports them."""
    from library.ai import GOOGLE_MODELS, SHERLOCK_MODELS, SHERLOCK_VISION_MODELS, _registry_provider
    from library.entity_description_batch import supports_structured_output

    system = (model.startswith(("arklabs/", "openrouter/"))
              or model in GOOGLE_MODELS + SHERLOCK_MODELS + SHERLOCK_VISION_MODELS
              or _registry_provider(model) in ("cloudferro", "arklabs", "openrouter", "google-vertexai"))
    return {"system_supported": system, "structured_output": supports_structured_output(model)}


def default_model(session):
    from library.llm_model_registry import is_selectable, selectable_models
    saved = app_settings.get_setting(session, SETTING_KEY)
    if isinstance(saved, str) and is_selectable(saved, TASK):
        return saved
    if is_selectable(DEFAULT_MODEL, TASK):
        return DEFAULT_MODEL
    return next((m["id"] for m in selectable_models(TASK) if m["available"]), None)


def exact_organization(session, name):
    """Use the registry resolver, but never accept its first-match behaviour for namesakes."""
    from library.organization_registry import normalize_alias, resolve_alias
    match = resolve_alias(session, name)
    if match is None:
        return None
    wanted = normalize_alias(name)
    ids = {r.id for r in session.scalars(select(Organization)) if normalize_alias(r.canonical_name) == wanted}
    ids.update(session.scalars(select(OrganizationAlias.organization_id).where(
        OrganizationAlias.normalized_alias == wanted)))
    return match if ids == {match.id} else None


def candidates(session, document_id, text):
    entries = []
    entities = session.scalars(select(DocumentEntity).where(DocumentEntity.document_id == document_id)).all()
    for end in document_endpoints(session, document_id):
        resolved = endpoint(session, end)
        kind, identifier = end["type"], end["id"]
        if kind == "person":
            forms = list(session.scalars(select(PersonAlias.alias).where(PersonAlias.person_id == identifier)))
            forms += list(session.scalars(select(DocumentPerson.raw_mention).where(
                DocumentPerson.person_id == identifier, DocumentPerson.document_id == document_id)))
        else:
            forms = list(session.scalars(select(OrganizationAlias.alias).where(
                OrganizationAlias.organization_id == identifier)))
        names = {normalized(v) for v in [resolved["name"], *forms] if v}
        for entity in entities:
            if entity.entity_type == ("persName" if kind == "person" else "orgName") and normalized(entity.entity_text) in names:
                forms += [entity.entity_text, *(entity.variants or [])]
        entries.append(dict(end, canonical_name=resolved["name"], variants=[resolved["name"], *forms],
                            entity_type="osoba" if kind == "person" else "organizacja"))
    for entity in entities:
        if entity.entity_type == "orgName":
            org = exact_organization(session, entity.entity_text)
            if org and not any(e.get("id") == org.id and e["type"] == "organization" for e in entries):
                entries.append(dict(type="organization", id=org.id, canonical_name=org.canonical_name,
                                    variants=[entity.entity_text, *(entity.variants or [])], entity_type="organizacja"))
    for country in detect_countries(text):
        entries.append(dict(type="country", slug=country.slug, canonical_name=country.name_pl,
                            variants=[country.slug], entity_type="kraj"))
    return entries


def resolve_candidate(session, entries, name, kind):
    matches = {(e["type"], e.get("id", e.get("slug"))) for e in entries if e["type"] == kind
               and normalized(name) in {normalized(v) for v in [e["canonical_name"], *e["variants"]]}}
    if len(matches) == 1:
        _, identifier = matches.pop()
        return {"type": kind, "slug" if kind == "country" else "id": identifier}
    if not matches and kind == "country":
        found = {c.slug for c in detect_countries(name)}
        permitted = {e["slug"] for e in entries if e["type"] == "country"}
        if len(found) == 1 and found <= permitted:
            return {"type": "country", "slug": found.pop()}
    if not matches and kind == "organization":
        org = exact_organization(session, name)
        if org:
            return {"type": kind, "id": org.id}
    return None


def detect_for_document(session, document_id, *, model=None, ask=None):
    doc = session.get(Document, document_id)
    if doc is None:
        raise LookupError("Document not found")
    text = document_ner_text(doc)
    if not text.strip():
        raise RelationError("No text")
    model = model or default_model(session)
    if not model:
        raise RelationError("No available model")
    options = {}
    if ask is None:
        from library.ai import ai_ask
        ask = ai_ask
        options = model_capabilities(model)
    entries = candidates(session, document_id, text)
    # Rows of the country tables carry their own codes; the model only knows the shared vocabulary.
    codes = {target: source for source, target in PROJECTIONS.items()}
    known = [{"subject": r["subject"]["name"], "object": r["object"]["name"],
              "relation": codes.get(r["relation"], r["relation"]),
              "title": r["title"], "status": r["status"]}
             for r in relations_for_document(session, document_id, True) if r["status"] in ("confirmed", "rejected")]
    # Bound even a transcript consisting of a single long sentence.
    chunks = [part[i:i + 6000] for part in chunk_text(text, 6000) for i in range(0, len(part), 6000)]
    summary = dict(document_id=document_id, model=model, prompt_version=PROMPT_VERSION, chunks=min(10, len(chunks)),
                   skipped_chunks=max(0, len(chunks) - 10), created=0, evidence_added=0, skipped_rejected=0,
                   unresolved=[], rejected={}, failed_calls=0, relation_ids=[], usage=None)

    def run(chunk):
        return extract_relations(chunk, entries, model, ask=ask, chunk_chars=6000,
                                 document_id=document_id, known_relations=known, **options)

    with document_usage_context(document_id):
        results = map_llm_calls(run, chunks[:10])
    rejected = Counter()
    summary["usage"] = combine_usage_reports([r["report"] for r in results])
    for result in results:
        rejected.update(result["report"]["rejected"])
        summary["failed_calls"] += result["report"]["failed_calls"]
        for candidate in result["relations"]:
            ends = {side: resolve_candidate(session, entries, candidate[side], PIPELINE_TYPES[candidate[side + "_type"]])
                    for side in ("subject", "object")}
            failed = [side for side, value in ends.items() if value is None]
            if failed:
                summary["unresolved"].append({k: candidate[k] for k in ("subject", "relation", "object", "quote")} |
                                             {"failed_ends": failed})
                continue
            for evidence in candidate["evidence"]:
                try:
                    row, created, added = upsert_relation(
                        session, ends["subject"], candidate["relation"], ends["object"], title=candidate.get("title"),
                        valid_from=candidate.get("valid_from"), valid_to=candidate.get("valid_to"),
                        evidence=dict(document_id=document_id, quote=evidence["quote"], claim=evidence["claim"],
                                      model=model, prompt_version=PROMPT_VERSION))
                except RelationError:
                    rejected["invalid_relation"] += 1
                    continue
                summary["created"] += int(created)
                summary["evidence_added"] += int(added)
                summary["skipped_rejected"] += int(row.status == "rejected")
                if row.id not in summary["relation_ids"]:
                    summary["relation_ids"].append(row.id)
    summary["rejected"] = dict(rejected)
    return summary

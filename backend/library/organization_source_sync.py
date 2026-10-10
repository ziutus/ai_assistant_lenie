"""Keep an organization, its document entities and its information source in step.

An organization resolved from NER can also be a *cited source*
(``information_sources.organization_id``). Its chip text is the organization's
canonical name, and the chip is recognised as a source by matching that text
against the source's name — so correcting a name ("telegrapha" -> "The
Telegraph") has to touch all three places, or the chip stops being a source.
``rename_organization`` does that in one transaction (the caller commits), and
folds the source into an existing one when the corrected name already belongs
to a source (the common case: the proper-name source was created earlier from
an LLM extraction, the lemma-named duplicate later from NER).
"""

from __future__ import annotations

import re

from sqlalchemy import func, select

from library import organization_registry
from library.db.models import (
    DocumentEntity,
    DocumentInformationSource,
    DocumentOrganization,
    InformationSource,
    InformationSourceAlias,
    Organization,
)

SOURCE_TYPE_MAX = 30
DESCRIPTION_MAX = 2000
_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


class SourceConflictError(ValueError):
    """The corrected name belongs to an information source of another organization."""

    def __init__(self, message: str, existing_organization_id: int | None = None):
        super().__init__(message)
        self.existing_organization_id = existing_organization_id


def normalize_domain(value: str | None) -> str | None:
    """Reduce a pasted URL or host to a bare lowercase domain ("https://www.telegraph.co.uk/" -> "telegraph.co.uk")."""
    text = (value or "").strip()
    if not text:
        return None
    text = re.sub(r"^[a-z][a-z0-9+.-]*://", "", text, flags=re.IGNORECASE)
    text = re.split(r"[/?#]", text, maxsplit=1)[0].split("@")[-1].split(":")[0].lower().rstrip(".")
    if text.startswith("www."):
        text = text[4:]
    if not _DOMAIN_RE.match(text):
        raise ValueError("domain must be a host name such as telegraph.co.uk")
    return text


def _clean_text(value, limit: int, field: str) -> str | None:
    text = (value or "").strip() if isinstance(value, str) or value is None else None
    if text is None:
        raise ValueError(f"{field} must be a string")
    if len(text) > limit:
        raise ValueError(f"{field} must be at most {limit} characters")
    return text or None


def _add_alias(session, source: InformationSource, alias: str) -> None:
    key = alias.casefold()
    if key == source.canonical_name.casefold():
        return
    if any(existing.alias.casefold() == key for existing in source.aliases):
        return
    session.add(InformationSourceAlias(source=source, alias=alias))


def _merge_sources(session, source: InformationSource, target: InformationSource, *,
                   adopt_organization: bool = True) -> None:
    """Fold ``source`` into ``target``: move links and aliases, delete ``source``.

    ``adopt_organization``: the target takes over the source's organization binding (a rename
    folding the lemma-named source into the proper one). False when the target already belongs
    to its own organization (an organization merge) — the binding of ``source`` is simply dropped.
    """
    for link in session.scalars(
        select(DocumentInformationSource).where(DocumentInformationSource.source_id == source.id)
    ).all():
        clash = session.scalar(select(DocumentInformationSource.id).where(
            DocumentInformationSource.document_id == link.document_id,
            DocumentInformationSource.source_id == target.id,
            DocumentInformationSource.role == link.role,
        ))
        if clash is not None:
            session.delete(link)
        else:
            link.source_id = target.id

    known = {target.canonical_name.casefold(), *(alias.alias.casefold() for alias in target.aliases)}
    for alias in list(source.aliases):
        if alias.alias.casefold() in known:
            session.delete(alias)
        else:
            # Through the relationship, not the FK column: the delete-orphan
            # cascade on InformationSource.aliases would otherwise drop it.
            alias.source = target
            known.add(alias.alias.casefold())
    if source.canonical_name.casefold() not in known:
        session.add(InformationSourceAlias(source=target, alias=source.canonical_name))

    for attribute in ("source_type", "domain", "description"):
        if not getattr(target, attribute) and getattr(source, attribute):
            setattr(target, attribute, getattr(source, attribute))

    organization_id = source.organization_id
    source.organization_id = None
    session.flush()  # organization_id is unique: free it before the target takes it
    if adopt_organization:
        target.organization_id = organization_id
    session.delete(source)
    session.flush()


def _sync_source_name(session, organization: Organization, old_name: str, new_name: str) -> dict:
    source = session.scalar(
        select(InformationSource).where(InformationSource.organization_id == organization.id)
    )
    duplicate = session.scalar(select(InformationSource).where(
        func.lower(InformationSource.canonical_name) == new_name.casefold(),
        InformationSource.id != (source.id if source is not None else 0),
    ))
    if duplicate is not None and duplicate.organization_id not in (None, organization.id):
        raise SourceConflictError(
            f"Źródło „{duplicate.canonical_name}” jest już powiązane z inną organizacją (id {duplicate.organization_id}).",
            existing_organization_id=duplicate.organization_id,
        )
    if source is None:
        if duplicate is None:
            return {"action": "none"}
        duplicate.organization_id = organization.id
        _add_alias(session, duplicate, old_name)
        session.flush()
        return {"action": "bound", "source_id": duplicate.id}
    if duplicate is None:
        source.canonical_name = new_name  # first: _add_alias skips a name equal to the canonical one
        _add_alias(session, source, old_name)
        session.flush()
        return {"action": "renamed", "source_id": source.id}
    _add_alias(session, duplicate, old_name)
    _merge_sources(session, source, duplicate)
    return {"action": "merged", "source_id": duplicate.id, "merged_source_id": source.id}


def _rename_entities(session, organization: Organization, new_name: str) -> dict:
    renamed = conflicts = 0
    rows = session.scalars(
        select(DocumentEntity)
        .join(DocumentOrganization, DocumentOrganization.document_entity_id == DocumentEntity.id)
        .where(DocumentOrganization.organization_id == organization.id, DocumentEntity.entity_type == "orgName")
    ).all()
    for row in rows:
        if row.entity_text == new_name:
            continue
        clash = session.scalar(select(DocumentEntity.id).where(
            DocumentEntity.document_id == row.document_id,
            DocumentEntity.entity_type == "orgName",
            DocumentEntity.entity_text == new_name,
            DocumentEntity.id != row.id,
        ))
        if clash is not None:
            conflicts += 1
            continue
        variants = dict.fromkeys(row.variants or [])
        variants.setdefault(row.entity_text)
        row.variants = list(variants)
        row.entity_text = new_name
        renamed += 1
    if renamed:
        session.flush()
    return {"entities_renamed": renamed, "entity_conflicts": conflicts}


def rename_organization(session, organization: Organization, new_name: str) -> dict:
    """Rename the organization, its document entities and its information source (merging duplicates).

    Raises ``organization_registry.AliasConflictError`` (another organization owns the
    name), ``SourceConflictError`` or ``ValueError``; the caller rolls back.
    """
    old_name = organization.canonical_name
    organization_registry.rename(session, organization, new_name)
    result = {"old_name": old_name, "canonical_name": organization.canonical_name,
              "entities_renamed": 0, "entity_conflicts": 0, "source": {"action": "none"}}
    if organization.canonical_name == old_name:
        return result
    result.update(_rename_entities(session, organization, organization.canonical_name))
    result["source"] = _sync_source_name(session, organization, old_name, organization.canonical_name)
    return result


def set_description(organization: Organization | None, source: InformationSource | None, text: str | None) -> None:
    """One description for an organization and the information source bound to it."""
    if organization is not None:
        organization.description = text
    if source is not None:
        source.description = text


def update_source_details(session, source: InformationSource, data: dict) -> InformationSource:
    """Apply ``source_type`` / ``domain`` / ``description`` from a PATCH body; ValueError on bad input."""
    if "source_type" in data:
        source.source_type = _clean_text(data["source_type"], SOURCE_TYPE_MAX, "source_type")
    if "domain" in data:
        source.domain = normalize_domain(data["domain"]) if data["domain"] is not None else None
    if "description" in data:
        text = _clean_text(data["description"], DESCRIPTION_MAX, "description")
        organization = session.get(Organization, source.organization_id) if source.organization_id else None
        set_description(organization, source, text)
    return source


def _bound_source(session, organization_id: int) -> InformationSource | None:
    return session.scalar(select(InformationSource).where(InformationSource.organization_id == organization_id))


def merge_organizations(session, source_id: int, target_id: int, *, make_global_alias: bool = True) -> dict:
    """``organization_registry.merge()`` plus what it does not know about: information sources and entity names.

    The registry merge re-points document links and aliases but would leave the source bound to
    the deleted organization orphaned (FK ``SET NULL``) and the entity chips under the old name.
    Here the information sources are folded first (both organizations have one: the lemma-named
    one is merged into the target's; only the merged-away one has one: it becomes the target's,
    renamed), then the registry merge runs, then every document entity of the target carries the
    target's canonical name. The caller commits.
    """
    source_org = session.get(Organization, source_id)
    target_org = session.get(Organization, target_id)
    if source_org is None or target_org is None:
        raise LookupError("organization not found")
    if source_id == target_id:
        raise ValueError("source_organization_id points at the same organization as target")

    source_of_merged = _bound_source(session, source_id)
    source_of_target = _bound_source(session, target_id)
    source_action = "none"
    if source_of_merged is not None and source_of_target is not None:
        _merge_sources(session, source_of_merged, source_of_target, adopt_organization=False)
        source_action = "merged"
    elif source_of_merged is not None:
        old_source_name = source_of_merged.canonical_name
        source_of_merged.organization_id = target_org.id
        session.flush()
        source_action = _sync_source_name(session, target_org, old_source_name, target_org.canonical_name)["action"]

    result = organization_registry.merge(session, source_id, target_id, make_global_alias=make_global_alias)
    result.update(_rename_entities(session, target_org, target_org.canonical_name))
    result["source"] = {"action": source_action}
    return result


def _source_summary(session, source: InformationSource | None) -> dict | None:
    if source is None:
        return None
    count = session.scalar(
        select(func.count(func.distinct(DocumentInformationSource.document_id)))
        .where(DocumentInformationSource.source_id == source.id)
    )
    return {
        "id": source.id, "canonical_name": source.canonical_name, "source_type": source.source_type,
        "domain": source.domain, "description": source.description,
        "aliases": [alias.alias for alias in source.aliases], "document_count": int(count or 0),
    }


def _document_ids(session, organization_id: int) -> set[int]:
    return set(session.scalars(
        select(DocumentOrganization.document_id).where(DocumentOrganization.organization_id == organization_id)
    ).all())


def _organization_summary(session, organization: Organization, document_ids: set[int]) -> dict:
    return {
        "id": organization.id, "canonical_name": organization.canonical_name,
        "organization_type": organization.organization_type, "description": organization.description,
        "aliases": [alias.alias for alias in organization.aliases], "document_count": len(document_ids),
        "information_source": _source_summary(session, _bound_source(session, organization.id)),
    }


def merge_preview(session, source_id: int, target_id: int) -> dict:
    """What ``merge_organizations(source_id -> target_id)`` would do, without changing anything."""
    source_org = session.get(Organization, source_id)
    target_org = session.get(Organization, target_id)
    if source_org is None or target_org is None:
        raise LookupError("organization not found")
    if source_id == target_id:
        raise ValueError("source_organization_id points at the same organization as target")

    source_documents = _document_ids(session, source_id)
    target_documents = _document_ids(session, target_id)
    source_summary = _organization_summary(session, source_org, source_documents)
    target_summary = _organization_summary(session, target_org, target_documents)

    target_names = {target_org.canonical_name.casefold(), *(alias.alias.casefold() for alias in target_org.aliases)}
    entity_texts = session.scalars(
        select(DocumentEntity.entity_text)
        .join(DocumentOrganization, DocumentOrganization.document_entity_id == DocumentEntity.id)
        .where(DocumentOrganization.organization_id == source_id, DocumentEntity.entity_type == "orgName")
    ).all()

    source_data, target_data = source_summary["information_source"], target_summary["information_source"]
    dropped_fields: list[str] = []
    if source_data and target_data:
        source_action = "merge_sources"
        dropped_fields = [
            field for field in ("source_type", "domain", "description")
            if source_data[field] and target_data[field] and source_data[field] != target_data[field]
        ]
    elif source_data:
        source_action = "move_source"
    else:
        source_action = "none"

    return {
        "source": source_summary,
        "target": target_summary,
        "effects": {
            "alias_added": source_org.canonical_name if source_org.canonical_name.casefold() not in target_names else None,
            "aliases_moved": [alias.alias for alias in source_org.aliases if alias.alias.casefold() not in target_names],
            "documents_moved": len(source_documents - target_documents),
            "documents_in_both": len(source_documents & target_documents),
            "entities_renamed": sum(1 for text in entity_texts if text.casefold() != target_org.canonical_name.casefold()),
            "source_action": source_action,
            "source_fields_dropped": dropped_fields,
        },
    }

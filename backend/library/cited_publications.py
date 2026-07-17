"""Deterministic extraction of scholarly publication identifiers and links."""

import re

from sqlalchemy import delete, func, select

from library.db.models import CitedPublication, DocumentCitedPublication

URL_RE = re.compile(r"https?://[^\s<>\]\)]+", re.IGNORECASE)
PMC_RE = re.compile(r"(?:pmc\.ncbi\.nlm\.nih\.gov/articles/|ncbi\.nlm\.nih\.gov/pmc/articles/)(PMC\d+)", re.I)
PMID_RE = re.compile(r"(?:pubmed\.ncbi\.nlm\.nih\.gov/|ncbi\.nlm\.nih\.gov/pubmed/)(\d+)", re.I)
DOI_RE = re.compile(r"(?:doi\.org/|\bdoi\s*:\s*)(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.I)


def extract_cited_publications(text: str) -> list[dict]:
    """Return distinct PMID/PMCID/DOI citations grounded in individual lines."""
    found: dict[tuple[str, str], dict] = {}
    for line in (text or "").splitlines():
        for url_match in URL_RE.finditer(line):
            raw_url = url_match.group(0).rstrip(".,;:")
            pmc = PMC_RE.search(raw_url)
            pmid = PMID_RE.search(raw_url)
            doi = DOI_RE.search(raw_url)
            if pmc:
                value = pmc.group(1).upper()
                key = ("pmcid", value)
                canonical_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{value}/"
            elif pmid:
                value = pmid.group(1)
                key = ("pmid", value)
                canonical_url = f"https://pubmed.ncbi.nlm.nih.gov/{value}/"
            elif doi:
                value = doi.group(1).rstrip(".,;:").lower()
                key = ("doi", value)
                canonical_url = f"https://doi.org/{value}"
            else:
                continue
            found[key] = {
                "identifier_type": key[0], "identifier": value,
                "canonical_url": canonical_url, "raw_citation": line.strip(),
                "evidence_excerpt": line.strip(),
            }
        for doi_match in DOI_RE.finditer(line):
            value = doi_match.group(1).rstrip(".,;:").lower()
            key = ("doi", value)
            found[key] = {
                "identifier_type": "doi", "identifier": value,
                "canonical_url": f"https://doi.org/{value}",
                "raw_citation": line.strip(), "evidence_excerpt": line.strip(),
            }
    return list(found.values())


def _find_publication(session, item: dict) -> CitedPublication | None:
    kind, value = item["identifier_type"], item["identifier"]
    if kind == "pmid":
        return session.scalar(select(CitedPublication).where(CitedPublication.pmid == value))
    if kind == "pmcid":
        return session.scalar(select(CitedPublication).where(func.upper(CitedPublication.pmcid) == value.upper()))
    return session.scalar(select(CitedPublication).where(func.lower(CitedPublication.doi) == value.lower()))


def refresh_document_cited_publications(
    session, document_id: int, chunks, *, replace_document: bool = True,
) -> dict:
    """Refresh citations from chunks, either document-wide or only for those chunks."""
    chunk_ids = [chunk.id for chunk in chunks]
    deletion = delete(DocumentCitedPublication).where(
        DocumentCitedPublication.document_id == document_id
    )
    if not replace_document:
        deletion = deletion.where(DocumentCitedPublication.chunk_id.in_(chunk_ids))
    session.execute(deletion)
    created = []
    seen: set[int] = set()
    for chunk in chunks:
        text = chunk.corrected_text or chunk.original_text or ""
        for item in extract_cited_publications(text):
            publication = _find_publication(session, item)
            if publication is None:
                values = {item["identifier_type"]: item["identifier"]}
                publication = CitedPublication(canonical_url=item["canonical_url"], **values)
                session.add(publication)
                session.flush()
            if publication.id in seen:
                continue
            seen.add(publication.id)
            existing = session.scalar(select(DocumentCitedPublication).where(
                DocumentCitedPublication.document_id == document_id,
                DocumentCitedPublication.publication_id == publication.id,
            ))
            if existing is None:
                session.add(DocumentCitedPublication(
                    document_id=document_id, publication_id=publication.id,
                    chunk_id=chunk.id, raw_citation=item["raw_citation"],
                    evidence_excerpt=item["evidence_excerpt"], extraction_method="url_identifier",
                    review_status="auto_accepted",
                ))
            else:
                existing.chunk_id = chunk.id
                existing.raw_citation = item["raw_citation"]
                existing.evidence_excerpt = item["evidence_excerpt"]
                existing.extraction_method = "url_identifier"
                existing.review_status = "auto_accepted"
            created.append(publication)
    return {"publications": created}

"""SearchService - search and similarity logic extracted from Flask routes.

Orchestrates vector similarity search by composing:
- WebsitesDBPostgreSQL repository (similarity queries)
- library.embedding module (embedding generation)
- library.config_loader (EMBEDDING_MODEL configuration)

No Flask dependencies - works in any context (Flask, MCP server, scripts).
Session is passed in by the caller, not created here.
"""

import logging
import re
import unicodedata

from sqlalchemy.orm import Session

from library.config_loader import load_config
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
import library.embedding as embedding

logger = logging.getLogger(__name__)


class SearchService:
    """Stateless service for search and similarity operations.

    Accepts a SQLAlchemy Session in its constructor.
    Raises RuntimeError for embedding generation failures.
    """

    def __init__(self, session: Session):
        self.session = session
        self.repo = WebsitesDBPostgreSQL(session)

    def _get_model(self) -> str:
        """Return the configured embedding model name."""
        return load_config().require("EMBEDDING_MODEL")

    def get_embedding(self, text: str):
        """Generate embedding for text using configured model."""
        return embedding.get_embedding(model=self._get_model(), text=text)

    def search_similar(
        self,
        text: str,
        limit: int = 3,
        project: str | None = None,
        period_from: int | None = None,
        period_to: int | None = None,
    ) -> list[dict]:
        """Hybrid text/vector search returning unique documents.

        An optional period_from/period_to year window (BCE as negative years)
        keeps only documents with a classified time period overlapping it.
        Raises RuntimeError if embedding generation fails.
        """
        if not text or not text.strip():
            return []

        candidate_limit = max(limit * 5, 20)
        lexical = self.repo.search_text(text, limit=candidate_limit, project=project)

        model = self._get_model()
        result = embedding.get_embedding(model=model, text=text)
        semantic = []
        if result.status == "success" and result.embedding:
            semantic = self.repo.get_similar(
                result.embedding, model, limit=candidate_limit, project=project,
            ) or []
        elif not lexical:
            raise RuntimeError(f"Embedding generation failed: {result.status}")
        else:
            logger.warning("Embedding generation failed; returning lexical results: %s", result.status)

        if period_from is not None or period_to is not None:
            allowed = self._documents_in_period(period_from, period_to)
            lexical = [item for item in lexical if item["website_id"] in allowed]
            semantic = [item for item in semantic if item["website_id"] in allowed]

        return self._merge_results(text, lexical, semantic, limit)

    def _documents_in_period(self, period_from: int | None, period_to: int | None) -> set[int]:
        """Ids of documents with a classified period overlapping [period_from, period_to].

        A missing bound on either side (filter or stored row) is treated as
        open-ended, so a label-only period ("starożytność" with no years)
        never disqualifies its document.
        """
        from sqlalchemy import or_

        from library.db.models import DocumentTimePeriod

        query = self.session.query(DocumentTimePeriod.document_id)
        if period_from is not None:
            query = query.filter(or_(
                DocumentTimePeriod.period_end_year.is_(None),
                DocumentTimePeriod.period_end_year >= period_from,
            ))
        if period_to is not None:
            query = query.filter(or_(
                DocumentTimePeriod.period_start_year.is_(None),
                DocumentTimePeriod.period_start_year <= period_to,
            ))
        return {row[0] for row in query.distinct()}

    # Letters with no Unicode canonical decomposition (NFKD leaves them alone,
    # unlike e.g. "ó" -> "o" + combining acute) but that PostgreSQL's unaccent()
    # folds anyway. Kept in sync with search_text()'s SQL-side folding so a
    # document found as a lexical candidate scores consistently here.
    _EXTRA_FOLD = str.maketrans({"ł": "l", "Ł": "L"})

    # Occurrences of a query token in a document needed for "full" per-token
    # coverage credit (see _token_coverage()).
    _TOKEN_SATURATION = 2

    @staticmethod
    def _normalise(value: str | None) -> str:
        value = (value or "").translate(SearchService._EXTRA_FOLD)
        value = unicodedata.normalize("NFKD", value)
        # Strip combining diacritical marks left over from NFKD decomposition
        # (e.g. "ź" -> "z" + U+0301). Without this, \w+ below still matches
        # each combining mark as "word", so it splits a single accented word
        # into two separate tokens (e.g. "ludźmi" -> "ludz" "mi") instead of
        # folding it to the plain-ASCII "ludzmi" a query would use.
        value = "".join(ch for ch in value if not unicodedata.combining(ch))
        return " ".join(re.findall(r"[\w]+", value.casefold()))

    @classmethod
    def _token_coverage(cls, body: str, tokens: set[str]) -> float:
        """Average per-token credit, saturating at _TOKEN_SATURATION occurrences.

        A lexical candidate already satisfies "every token occurs at least
        once" by construction -- search_text()'s SQL layer ANDs an ILIKE per
        token, so every candidate it returns trivially has 3/3 plain-presence
        coverage. Plain presence therefore gives every lexical candidate the
        same, maximum coverage and cannot distinguish a document that is
        genuinely *about* the query (its key words recur throughout -- a
        trafficking article naturally repeats "handel"/"ludźmi"/"Afryka") from
        one where a token occurs exactly once, incidentally, in an unrelated
        passage (e.g. "Afryka" mentioned once in an article about an unrelated
        Polish crime case, next to an unrelated "handel narkotykami" -- a
        generic crime-reporting phrase -- elsewhere in the same long article).
        Weighting by occurrence count (capped, so one very repetitive word
        can't dominate the average) restores that distinction. A window/
        proximity-based approach was tried first and discarded: a genuinely
        on-topic, well-written article naturally varies phrasing/inflection
        across paragraphs, so its query-token mentions are often *not* any
        closer together than an incidental one-off mention is to an unrelated
        phrase -- proximity penalized true positives about as much as false
        ones. See docs/search-hybrid.md.
        """
        if not tokens:
            return 0.0
        return sum(min(1.0, body.count(t) / cls._TOKEN_SATURATION) for t in tokens) / len(tokens)

    def _merge_results(self, query: str, lexical: list[dict], semantic: list[dict], limit: int) -> list[dict]:
        """Combine signals and keep only the best fragment for each document."""
        query_norm = self._normalise(query)
        tokens = {t for t in query_norm.split() if len(t) >= 3}
        merged: dict[int, dict] = {}

        for item in semantic:
            website_id = item["website_id"]
            candidate = dict(item)
            candidate["semantic_similarity"] = float(item.get("similarity") or 0.0)
            candidate["text_score"] = 0.0
            merged[website_id] = candidate

        for item in lexical:
            website_id = item["website_id"]
            title = self._normalise(item.get("title"))
            # Score against the full document text (text_for_scoring), not the
            # 1000-char display snippet (text) -- a match past the first 1000
            # chars must not be scored as absent. See docs/search-hybrid.md.
            full_text = item.get("text_for_scoring") or item.get("text")
            scoring_text = " ".join(filter(None, [item.get("title"), item.get("tags"), item.get("note"), full_text]))
            body = self._normalise(scoring_text)
            # Occurrence-weighted, not plain-presence, coverage -- see
            # _token_coverage() docstring.
            coverage = self._token_coverage(body, tokens)
            phrase_in_title = bool(query_norm and query_norm in title)
            phrase_in_body = bool(query_norm and query_norm in body)
            title_coverage = sum(token in title for token in tokens) / max(len(tokens), 1)
            # coverage weighted at 0.70 (was 0.45, then 0.60) so a document
            # whose query tokens recur throughout its text -- even with no
            # title or exact-phrase match -- scores competitively (~0.55-0.65
            # for realistic token_coverage values, since that's no longer
            # capped at a trivial 1.0 -- see _token_coverage()) against
            # typical semantic-similarity hits (~0.5-0.55), while a document
            # where each token occurs only once, incidentally, in an unrelated
            # passage stays below that threshold (~0.45-0.48). See
            # docs/search-hybrid.md.
            text_score = min(1.0, 0.70 * coverage + 0.35 * title_coverage
                             + 0.20 * phrase_in_body + 0.35 * phrase_in_title)

            candidate = merged.get(website_id, dict(item))
            candidate["text_score"] = text_score
            candidate.setdefault("semantic_similarity", 0.0)
            # Prefer semantic chunk text/snippet when one exists.
            for key, value in item.items():
                candidate.setdefault(key, value)
            merged[website_id] = candidate

        for candidate in merged.values():
            semantic_score = candidate.get("semantic_similarity", 0.0)
            text_score = candidate.get("text_score", 0.0)
            candidate["similarity"] = round(max(
                text_score, semantic_score, 0.65 * semantic_score + 0.35 * text_score,
            ), 6)
            candidate["search_match"] = "hybrid" if semantic_score and text_score else ("semantic" if semantic_score else "text")
            candidate.pop("tags", None)
            candidate.pop("note", None)
            candidate.pop("text_for_scoring", None)

        return sorted(merged.values(), key=lambda row: row["similarity"], reverse=True)[:limit]

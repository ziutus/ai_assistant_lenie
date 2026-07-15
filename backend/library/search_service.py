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

    def search_similar(self, text: str, limit: int = 3, project: str | None = None) -> list[dict]:
        """Hybrid text/vector search returning unique documents.

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

        return self._merge_results(text, lexical, semantic, limit)

    @staticmethod
    def _normalise(value: str | None) -> str:
        value = unicodedata.normalize("NFKD", value or "")
        return " ".join(re.findall(r"[\w]+", value.casefold()))

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
            body = self._normalise(" ".join(filter(None, [item.get("title"), item.get("tags"), item.get("note"), item.get("text")])))
            coverage = sum(token in body for token in tokens) / max(len(tokens), 1)
            phrase_in_title = bool(query_norm and query_norm in title)
            phrase_in_body = bool(query_norm and query_norm in body)
            title_coverage = sum(token in title for token in tokens) / max(len(tokens), 1)
            text_score = min(1.0, 0.45 * coverage + 0.35 * title_coverage
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

        return sorted(merged.values(), key=lambda row: row["similarity"], reverse=True)[:limit]

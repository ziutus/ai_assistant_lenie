"""SearchService - search and similarity logic extracted from Flask routes.

Orchestrates vector similarity search by composing:
- WebsitesDBPostgreSQL repository (similarity queries)
- library.embedding module (embedding generation)
- library.config_loader (EMBEDDING_MODEL configuration)

No Flask dependencies - works in any context (Flask, MCP server, scripts).
Session is passed in by the caller, not created here.
"""

import logging

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
        """Search for semantically similar documents.

        Raises RuntimeError if embedding generation fails.
        """
        model = self._get_model()
        result = embedding.get_embedding(model=model, text=text)
        if result.status != "success" or len(result.embedding) == 0:
            raise RuntimeError(f"Embedding generation failed: {result.status}")

        return self.repo.get_similar(
            result.embedding,
            model,
            limit=limit,
            project=project,
        )

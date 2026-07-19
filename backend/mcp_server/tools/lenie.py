"""Lenie MCP tools — article retrieval, search, and management tools for the Lenie knowledge base."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import cast, func, or_, select
from sqlalchemy import Text as SaText
from sqlalchemy.exc import OperationalError

from library.db.engine import get_session
from library.db.models import Document
from mcp_server.errors import raise_article_not_found, raise_database_unavailable

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)


def register_lenie_tools(mcp: "FastMCP") -> None:
    """Register all Lenie knowledge-base tools with the MCP server."""

    @mcp.tool()
    def lenie_unreviewed_articles(
        limit: int = 6,
        offset: int = 0,
        source_filter: str | None = None,
        type_filter: str | None = None,
    ) -> dict:
        """Return a list of unreviewed articles from the Lenie knowledge base.

        Articles are unreviewed when reviewed_at IS NULL or obsidian_note_paths is empty ([]).
        Results are ordered newest-first (created_at DESC).

        Args:
            limit: Maximum number of articles to return (default: 6).
            offset: Number of articles to skip for pagination (default: 0).
            source_filter: Optional substring to filter by article URL (case-insensitive).
            type_filter: Optional document type to filter by (e.g. "webpage", "youtube", "link").

        Returns:
            dict with "articles" list and "total_unreviewed" count.
        """
        session = None
        try:
            session = get_session()
            unreviewed_filter = or_(
                Document.reviewed_at.is_(None),
                cast(Document.obsidian_note_paths, SaText) == "[]",
            )

            stmt = select(Document).where(unreviewed_filter)
            count_stmt = select(func.count(Document.id)).where(unreviewed_filter)

            if source_filter:
                url_filter = Document.url.ilike(f"%{source_filter}%")
                stmt = stmt.where(url_filter)
                count_stmt = count_stmt.where(url_filter)

            if type_filter:
                type_f = Document.document_type == type_filter
                stmt = stmt.where(type_f)
                count_stmt = count_stmt.where(type_f)

            total_unreviewed = session.execute(count_stmt).scalar() or 0

            stmt = stmt.order_by(Document.created_at.desc()).limit(limit).offset(offset)
            docs = session.execute(stmt).scalars().all()

            articles = []
            for doc in docs:
                size_kb = len(doc.text.encode()) // 1024 if doc.text else 0
                articles.append({
                    "id": doc.id,
                    "title": doc.title,
                    "source": doc.url,
                    "size_kb": size_kb,
                    "user_note": doc.note,
                    "added_at": doc.created_at.isoformat() if doc.created_at else None,
                    "total_unreviewed": total_unreviewed,
                })

            return {"articles": articles, "total_unreviewed": total_unreviewed}
        except OperationalError:
            raise_database_unavailable()
        finally:
            if session is not None:
                session.close()

    @mcp.tool()
    def lenie_get_article(article_id: int) -> dict:
        """Return the full content and metadata of a specific article from the Lenie knowledge base.

        Args:
            article_id: Integer primary key from documents.id (shown in lenie_unreviewed_articles results).

        Returns:
            dict with full article data: id, title, source, size_kb, content, language,
            user_note, document_type, added_at, reviewed_at, obsidian_note_paths.

        Raises:
            McpError: ARTICLE_NOT_FOUND if the article does not exist in the database.
            McpError: DATABASE_UNAVAILABLE if PostgreSQL is unreachable.
        """
        session = None
        try:
            session = get_session()
            doc = session.execute(
                select(Document).where(Document.id == article_id)
            ).scalars().first()

            if doc is None:
                raise_article_not_found(article_id)

            size_kb = len(doc.text.encode()) // 1024 if doc.text else 0
            return {
                "id": doc.id,
                "title": doc.title,
                "source": doc.url,
                "size_kb": size_kb,
                "content": doc.text,
                "language": doc.language,
                "user_note": doc.note,
                "document_type": doc.document_type,
                "added_at": doc.created_at.isoformat() if doc.created_at else None,
                "reviewed_at": doc.reviewed_at.isoformat() if doc.reviewed_at else None,
                "obsidian_note_paths": doc.obsidian_note_paths or [],
            }
        except OperationalError:
            raise_database_unavailable()
        finally:
            if session is not None:
                session.close()

import datetime
import logging
from typing import Any

from sqlalchemy import Float, and_, delete, func, literal, or_, select
from sqlalchemy.orm import Session

from library.db.models import DocumentAnalysisRun, DocumentChunk, WebDocument, WebsiteEmbedding
from library.models.stalker_document_status import StalkerDocumentStatus
from library.models.stalker_document_status_error import StalkerDocumentStatusError
from library.models.stalker_document_type import StalkerDocumentType

logger = logging.getLogger(__name__)


class WebsitesDBPostgreSQL:
    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # Query methods — ORM via SQLAlchemy session
    # ------------------------------------------------------------------

    def get_list(self, limit: int = 100, offset: int = 0, document_type: str = "ALL", document_state: str = "ALL",
                 search_in_documents=None, count=False, project=None, ai_summary_needed: bool = None,
                 start_id=None, only_missing_obsidian_notes: bool = False,
                 only_has_obsidian_notes: bool = False) -> list[dict[str, Any]]:

        if count:
            stmt = select(func.count(WebDocument.id))
        else:
            stmt = select(
                WebDocument.id, WebDocument.url, WebDocument.title, WebDocument.document_type,
                WebDocument.created_at, WebDocument.document_state, WebDocument.document_state_error,
                WebDocument.note, WebDocument.project, WebDocument.uuid, WebDocument.author,
                WebDocument.obsidian_note_paths,
            )

        # Dynamic filters — column stores enum name strings directly
        if document_type != "ALL":
            stmt = stmt.where(WebDocument.document_type == document_type)

        if document_state != "ALL":
            stmt = stmt.where(WebDocument.document_state == document_state)

        if project:
            stmt = stmt.where(WebDocument.project == project)

        if ai_summary_needed is not None:
            stmt = stmt.where(WebDocument.ai_summary_needed == ai_summary_needed)

        if start_id:
            stmt = stmt.where(WebDocument.id >= int(start_id))

        if search_in_documents:
            escaped = search_in_documents.replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            stmt = stmt.where(or_(
                WebDocument.url.ilike(pattern, escape="\\"),
                WebDocument.text.ilike(pattern, escape="\\"),
                WebDocument.title.ilike(pattern, escape="\\"),
                WebDocument.summary.ilike(pattern, escape="\\"),
                WebDocument.chapter_list.ilike(pattern, escape="\\"),
            ))

        if only_missing_obsidian_notes:
            stmt = stmt.where(select(DocumentChunk.id).where(
                DocumentChunk.document_id == WebDocument.id,
                *self._missing_obsidian_note_chunk_conditions(),
            ).exists())

        if only_has_obsidian_notes:
            stmt = stmt.where(or_(
                func.coalesce(func.jsonb_array_length(WebDocument.obsidian_note_paths), 0) > 0,
                select(DocumentChunk.id).where(
                    DocumentChunk.document_id == WebDocument.id,
                    *self._has_obsidian_note_chunk_conditions(),
                ).exists(),
            ))

        if count:
            return self.session.execute(stmt).scalar()

        stmt = stmt.order_by(WebDocument.created_at.desc())
        stmt = stmt.limit(limit).offset(offset * limit)

        rows = self.session.execute(stmt).all()
        doc_ids = [row.id for row in rows]
        obsidian_notes_by_doc = self._count_obsidian_note_chunks(doc_ids)

        result = []
        for row in rows:
            missing, with_notes = obsidian_notes_by_doc.get(row.id, (0, 0))
            result.append({
                "id": row.id,
                "url": row.url,
                "title": row.title,
                "document_type": row.document_type,
                "created_at": row.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                "document_state": row.document_state,
                "document_state_error": row.document_state_error,
                "note": row.note,
                "project": row.project,
                "uuid": row.uuid,
                "author": row.author,
                "obsidian_note_paths": row.obsidian_note_paths or [],
                "chunks_missing_obsidian_notes": missing,
                "chunks_with_obsidian_notes": with_notes,
            })
        return result

    @staticmethod
    def _missing_obsidian_note_chunk_conditions():
        """TEMAT chunks that still need an Obsidian note: not skipped, no note path
        recorded yet, and not part of a superseded run (an abandoned run replaced
        by a newer one of the same scope — its chunks are not work to do)."""
        return (
            DocumentChunk.type == "TEMAT",
            DocumentChunk.status != "skipped",
            func.coalesce(func.array_length(DocumentChunk.obsidian_note_paths, 1), 0) == 0,
            select(DocumentAnalysisRun.id).where(
                DocumentAnalysisRun.id == DocumentChunk.run_id,
                DocumentAnalysisRun.status != "superseded",
            ).exists(),
        )

    @staticmethod
    def _has_obsidian_note_chunk_conditions():
        """TEMAT chunks that already have at least one Obsidian note recorded."""
        return (
            DocumentChunk.type == "TEMAT",
            func.coalesce(func.array_length(DocumentChunk.obsidian_note_paths, 1), 0) > 0,
        )

    def _count_obsidian_note_chunks(self, doc_ids: list[int]) -> dict[int, tuple[int, int]]:
        """Batch (missing, with_notes) TEMAT chunk counts per document_id."""
        if not doc_ids:
            return {}
        missing_condition = and_(*self._missing_obsidian_note_chunk_conditions())
        with_notes_condition = and_(*self._has_obsidian_note_chunk_conditions())
        stmt = (
            select(
                DocumentChunk.document_id,
                func.count().filter(missing_condition).label("missing"),
                func.count().filter(with_notes_condition).label("with_notes"),
            )
            .where(DocumentChunk.document_id.in_(doc_ids), DocumentChunk.type == "TEMAT")
            .group_by(DocumentChunk.document_id)
        )
        return {doc_id: (missing, with_notes) for doc_id, missing, with_notes in self.session.execute(stmt).all()}

    def get_count(self, document_type: str = "ALL") -> int:
        stmt = select(func.count(WebDocument.id))
        if document_type != "ALL":
            stmt = stmt.where(WebDocument.document_type == document_type)
        return self.session.execute(stmt).scalar()

    def get_count_by_type(self) -> dict[str, int]:
        """Return document counts grouped by type, plus 'ALL' total."""
        stmt = select(WebDocument.document_type, func.count(WebDocument.id)).group_by(WebDocument.document_type)
        rows = self.session.execute(stmt).all()
        counts = {row[0]: row[1] for row in rows}
        counts["ALL"] = sum(counts.values())
        return counts

    def get_ready_for_download(self) -> list[tuple]:
        stmt = select(
            WebDocument.id, WebDocument.url, WebDocument.document_type, WebDocument.uuid,
        ).where(WebDocument.document_state == StalkerDocumentStatus.URL_ADDED.name)

        rows = self.session.execute(stmt).all()
        return [
            (row.id, row.url, row.document_type, row.uuid)
            for row in rows
        ]

    def get_youtube_just_added(self) -> list[tuple]:
        stmt = select(
            WebDocument.id, WebDocument.url, WebDocument.document_type,
            WebDocument.language, WebDocument.chapter_list, WebDocument.ai_summary_needed,
        ).where(
            WebDocument.document_type == StalkerDocumentType.youtube.name,
            or_(
                WebDocument.document_state == StalkerDocumentStatus.URL_ADDED.name,
                WebDocument.document_state == StalkerDocumentStatus.NEED_TRANSCRIPTION.name,
                WebDocument.document_state == StalkerDocumentStatus.TEMPORARY_ERROR.name,
            ),
        )

        rows = self.session.execute(stmt).all()
        return [
            (row.id, row.url, row.document_type,
             row.language, row.chapter_list, row.ai_summary_needed)
            for row in rows
        ]

    def get_transcription_done(self) -> list[int]:
        stmt = select(WebDocument.id).where(
            WebDocument.document_state == StalkerDocumentStatus.TRANSCRIPTION_DONE.name,
        ).order_by(WebDocument.id)

        rows = self.session.execute(stmt).all()
        return [row[0] for row in rows]

    def get_next_to_correct(self, website_id: int, document_type: str = "ALL",
                            document_state: str = "ALL") -> tuple[int, str] | int:
        stmt = select(WebDocument.id, WebDocument.document_type).where(WebDocument.id > website_id)

        if document_type != "ALL":
            stmt = stmt.where(WebDocument.document_type == document_type)

        if document_state != "ALL":
            stmt = stmt.where(WebDocument.document_state == document_state)

        stmt = stmt.order_by(WebDocument.id.asc()).limit(1)

        row = self.session.execute(stmt).first()
        if row is None:
            return -1
        return (row[0], row[1])

    def get_last_unknown_news(self) -> datetime.date | None:
        return self.get_last_by_source('https://unknow.news/')

    def get_last_by_source(self, source: str) -> datetime.date | None:
        """Return the most recent date_from for documents with a given source."""
        stmt = select(func.max(WebDocument.date_from)).where(
            WebDocument.source == source,
        )
        return self.session.execute(stmt).scalar()

    def load_neighbors(self, doc) -> None:
        """Populate doc.next_id, next_type, previous_id, previous_type."""
        WebDocument.populate_neighbors(self.session, doc)

    # ------------------------------------------------------------------
    # Similarity search
    # ------------------------------------------------------------------

    def get_similar(self, embedding, model: str, limit: int = 3, minimal_similarity: float = 0.30, project=None,
                    filters=None) -> list[dict[str, Any]] | None:
        """Vector similarity search.

        ``filters`` (an optional ``library.search.types.SearchFilters``) is
        applied via ``library.search.sql_filters.build_document_filters()``
        — the SAME builder ``search_text()`` uses — before ``LIMIT``, so
        vector and lexical search share identical constraints (stage 6
        acceptance criterion). ``project`` is a separate, older exact-match
        filter kept for existing callers; the two combine with AND if both
        are given.
        """

        if minimal_similarity is None:
            minimal_similarity = 0.30
        if embedding is None:
            return None

        similarity = (
            literal(1) - func.cast(
                WebsiteEmbedding.embedding.cosine_distance(embedding),
                Float,
            )
        ).label("similarity")

        stmt = (
            select(
                WebsiteEmbedding.website_id,
                WebsiteEmbedding.text,
                similarity,
                WebsiteEmbedding.id,
                WebDocument.url,
                WebDocument.language,
                WebsiteEmbedding.text_original,
                func.length(WebDocument.text).label("websites_text_length"),
                func.length(WebsiteEmbedding.text).label("embeddings_text_length"),
                WebDocument.title,
                WebDocument.document_type,
                WebDocument.project,
                WebDocument.date_from,
                WebDocument.created_at,
                WebsiteEmbedding.chunk_id,
                DocumentChunk.obsidian_note_paths,
            )
            .outerjoin(WebDocument, WebsiteEmbedding.website_id == WebDocument.id)
            .outerjoin(DocumentChunk, WebsiteEmbedding.chunk_id == DocumentChunk.id)
            .where(WebsiteEmbedding.model == model)
            .where(
                literal(1) - func.cast(
                    WebsiteEmbedding.embedding.cosine_distance(embedding),
                    Float,
                ) > minimal_similarity
            )
            .order_by(WebsiteEmbedding.embedding.cosine_distance(embedding))
            .limit(limit)
        )

        if project:
            stmt = stmt.where(WebDocument.project == project)

        if filters is not None:
            from library.search.sql_filters import build_document_filters
            stmt = stmt.where(*build_document_filters(filters))

        rows = self.session.execute(stmt).all()
        return [
            {
                "website_id": r.website_id,
                "text": r.text,
                "similarity": float(r.similarity),
                "id": r.id,
                "url": r.url,
                "language": r.language,
                "text_original": r.text_original,
                "websites_text_length": r.websites_text_length,
                "embeddings_text_length": r.embeddings_text_length,
                "title": r.title,
                "document_type": r.document_type,
                "project": r.project,
                "date_from": r.date_from.isoformat() if r.date_from else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "chunk_id": r.chunk_id,
                "obsidian_note_paths": r.obsidian_note_paths or [],
            }
            for r in rows
        ]

    def search_text(self, query: str, limit: int = 20, project=None, filters=None) -> list[dict[str, Any]]:
        """Return documents matching query words in user-visible text fields.

        This deliberately uses portable ILIKE predicates instead of requiring a
        PostgreSQL text-search migration. Ranking/merging with vector results is
        handled by SearchService. Short words (for example Polish prepositions)
        do not restrict token matching.

        Both sides of every ILIKE comparison are wrapped in the `unaccent()`
        extension so Polish diacritics don't have to match literally (a query
        typed as "ludzmi" must still find text containing "ludźmi"). See
        docs/search-hybrid.md for why plain ILIKE is not enough here and why
        this two-layer approach (SQL candidate selection + Python scoring in
        SearchService) exists at all.

        ``filters`` (an optional ``library.search.types.SearchFilters``) is
        applied via ``library.search.sql_filters.build_document_filters()``
        — the SAME builder ``get_similar()`` uses — before ``LIMIT`` (stage 6
        acceptance criterion: lexical and vector search share identical
        constraints).
        """
        query = (query or "").strip()
        if not query:
            return []

        tokens = list(dict.fromkeys(word for word in query.split() if len(word) >= 3))
        searchable = func.unaccent(func.concat_ws(
            " ",
            func.coalesce(WebDocument.title, ""),
            func.coalesce(WebDocument.tags, ""),
            func.coalesce(WebDocument.note, ""),
            func.coalesce(WebDocument.text, ""),
        ))
        title = func.unaccent(func.coalesce(WebDocument.title, ""))
        phrase = func.unaccent(f"%{query}%")
        conditions = [title.ilike(phrase), searchable.ilike(phrase)]
        if tokens:
            conditions.append(and_(*(searchable.ilike(func.unaccent(f"%{token}%")) for token in tokens)))

        stmt = (
            select(WebDocument)
            .where(or_(*conditions))
            .order_by(WebDocument.created_at.desc(), WebDocument.id.desc())
            .limit(limit)
        )
        if project:
            stmt = stmt.where(WebDocument.project == project)

        if filters is not None:
            from library.search.sql_filters import build_document_filters
            stmt = stmt.where(*build_document_filters(filters))

        documents = self.session.scalars(stmt).all()
        return [
            {
                "website_id": doc.id,
                "text": (doc.text or "")[:1000],
                # Full (untruncated) text for SearchService._merge_results() coverage
                # scoring only -- popped before the API response is returned. A
                # matching token past the first 1000 chars (a long article's intro
                # is often boilerplate/AI summary, not the matched sentence) must
                # not be scored as absent. See docs/search-hybrid.md.
                "text_for_scoring": doc.text or "",
                "similarity": 0.0,
                "id": None,
                "url": doc.url,
                "language": doc.language,
                "text_original": (doc.text or "")[:1000],
                "websites_text_length": len(doc.text or ""),
                "embeddings_text_length": 0,
                "title": doc.title,
                "document_type": doc.document_type,
                "project": doc.project,
                "date_from": doc.date_from.isoformat() if doc.date_from else None,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "chunk_id": None,
                "obsidian_note_paths": doc.obsidian_note_paths or [],
                "tags": doc.tags,
                "note": doc.note,
            }
            for doc in documents
        ]

    # ------------------------------------------------------------------
    # Embedding CRUD
    # ------------------------------------------------------------------

    def embedding_add(self, website_id, embedding, language, text, text_original, model, chunk_id=None) -> None:
        emb = WebsiteEmbedding(
            website_id=website_id,
            language=language,
            text=text,
            text_original=text_original,
            embedding=embedding,
            model=model,
            chunk_id=chunk_id,
        )
        self.session.add(emb)

    def embedding_delete(self, website_id: int, model: str) -> None:
        stmt = delete(WebsiteEmbedding).where(
            WebsiteEmbedding.website_id == website_id,
            WebsiteEmbedding.model == model,
        )
        self.session.execute(stmt)

    # ------------------------------------------------------------------
    # Documents needing embedding or markdown
    # ------------------------------------------------------------------

    def get_documents_needing_embedding(self, embedding_model: str) -> list[int]:
        # Only states which explicitly declare content ready for indexing are
        # processed automatically. DOCUMENT_INTO_DATABASE may still be waiting
        # for chunk review; closing that review starts indexing directly.
        stmt = (
            select(WebDocument.id)
            .outerjoin(
                WebsiteEmbedding,
                and_(
                    WebDocument.id == WebsiteEmbedding.website_id,
                    WebsiteEmbedding.model == embedding_model,
                ),
            )
            .where(
                WebsiteEmbedding.website_id.is_(None),
                WebDocument.document_state.in_([
                    StalkerDocumentStatus.READY_FOR_EMBEDDING.name,
                    StalkerDocumentStatus.EMBEDDING_EXIST.name,
                    StalkerDocumentStatus.MD_SIMPLIFIED.name,
                ]),
                or_(
                    func.length(func.coalesce(WebDocument.text_md, "")) > 0,
                    func.length(func.coalesce(WebDocument.text, "")) > 0,
                    and_(
                        WebDocument.document_type == StalkerDocumentType.link.name,
                        func.length(func.coalesce(WebDocument.title, "")) > 0,
                    ),
                ),
            )
            .order_by(WebDocument.id)
        )
        rows = self.session.execute(stmt).all()
        return [row[0] for row in rows]

    def get_documents_md_needed(self, min_id: int = 0) -> list[int]:
        """
        Pobiera listę identyfikatorów dokumentów, które mają null w kolumnie `text_md` i wartość false w kolumnie `paywall`.
        """
        min_id = int(min_id)

        stmt = select(WebDocument.id).where(
            WebDocument.text_md.is_(None),
            or_(WebDocument.paywall == False, WebDocument.paywall.is_(None)),  # noqa: E712
            WebDocument.document_type == StalkerDocumentType.webpage.name,
            WebDocument.id > min_id,
        ).order_by(WebDocument.id)
        rows = self.session.execute(stmt).all()
        return [row[0] for row in rows]

    def get_documents_by_url(self, url: str, min_id: int = 0) -> list[int]:

        """
        Retrieves a list of document IDs where the URL starts with the specified prefix, the document type is 'webpage',
        and the document ID is greater than the provided minimum value (`min_id`).
        """
        min_id = int(min_id)
        escaped_url = url.replace("%", "\\%").replace("_", "\\_")
        pattern = f"{escaped_url}%"

        stmt = select(WebDocument.id).where(
            WebDocument.url.like(pattern, escape="\\"),
            WebDocument.document_type == StalkerDocumentType.webpage.name,
            WebDocument.id > min_id,
            or_(
                and_(
                    WebDocument.document_state == StalkerDocumentStatus.ERROR.name,
                    WebDocument.document_state_error == StalkerDocumentStatusError.REGEX_ERROR.name,
                ),
                WebDocument.document_state == StalkerDocumentStatus.URL_ADDED.name,
            ),
        ).order_by(WebDocument.id)
        rows = self.session.execute(stmt).all()
        return [row[0] for row in rows]

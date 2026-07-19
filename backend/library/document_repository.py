import datetime
import logging
from typing import Any

from sqlalchemy import Float, and_, delete, func, literal, or_, select
from sqlalchemy.orm import Session

from library.db.models import DocumentAnalysisRun, DocumentChunk, Document, DocumentEmbedding
from library.models.stalker_document_status import StalkerDocumentStatus
from library.models.stalker_document_status_error import StalkerDocumentStatusError
from library.models.stalker_document_type import StalkerDocumentType

logger = logging.getLogger(__name__)


class DocumentRepository:
    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # Query methods — ORM via SQLAlchemy session
    # ------------------------------------------------------------------

    def get_list(self, limit: int = 100, offset: int = 0, document_type: str = "ALL", processing_status: str = "ALL",
                 search_in_documents=None, count=False, collection_id: int | None = None,
                 ai_summary_needed: bool = None,
                 start_id=None, only_missing_obsidian_notes: bool = False,
                 only_has_obsidian_notes: bool = False) -> list[dict[str, Any]]:

        if count:
            stmt = select(func.count(Document.id))
        else:
            stmt = select(
                Document.id, Document.url, Document.title, Document.document_type,
                Document.ingested_at, Document.processing_status, Document.processing_error_code,
                Document.note, Document.collection_id, Document.uuid, Document.byline,
                Document.obsidian_note_paths,
            )

        # Dynamic filters — column stores enum name strings directly
        if document_type != "ALL":
            stmt = stmt.where(Document.document_type == document_type)

        if processing_status != "ALL":
            stmt = stmt.where(Document.processing_status == processing_status)

        if collection_id:
            stmt = stmt.where(Document.collection_id == collection_id)

        if ai_summary_needed is not None:
            stmt = stmt.where(Document.ai_summary_needed == ai_summary_needed)

        if start_id:
            stmt = stmt.where(Document.id >= int(start_id))

        if search_in_documents:
            escaped = search_in_documents.replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            stmt = stmt.where(or_(
                Document.url.ilike(pattern, escape="\\"),
                Document.text.ilike(pattern, escape="\\"),
                Document.title.ilike(pattern, escape="\\"),
                Document.summary.ilike(pattern, escape="\\"),
                Document.chapter_list.ilike(pattern, escape="\\"),
            ))

        if only_missing_obsidian_notes:
            stmt = stmt.where(select(DocumentChunk.id).where(
                DocumentChunk.document_id == Document.id,
                *self._missing_obsidian_note_chunk_conditions(),
            ).exists())

        if only_has_obsidian_notes:
            stmt = stmt.where(or_(
                func.coalesce(func.jsonb_array_length(Document.obsidian_note_paths), 0) > 0,
                select(DocumentChunk.id).where(
                    DocumentChunk.document_id == Document.id,
                    *self._has_obsidian_note_chunk_conditions(),
                ).exists(),
            ))

        if count:
            return self.session.execute(stmt).scalar()

        # id tiebreaker keeps pagination stable when timestamps collide (stage 12)
        stmt = stmt.order_by(Document.ingested_at.desc(), Document.id.desc())
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
                "ingested_at": row.ingested_at.strftime('%Y-%m-%d %H:%M:%S'),
                "processing_status": row.processing_status,
                "processing_error_code": row.processing_error_code,
                "note": row.note,
                "collection_id": row.collection_id,
                "uuid": row.uuid,
                "byline": row.byline,
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
        stmt = select(func.count(Document.id))
        if document_type != "ALL":
            stmt = stmt.where(Document.document_type == document_type)
        return self.session.execute(stmt).scalar()

    def get_count_by_type(self) -> dict[str, int]:
        """Return document counts grouped by type, plus 'ALL' total."""
        stmt = select(Document.document_type, func.count(Document.id)).group_by(Document.document_type)
        rows = self.session.execute(stmt).all()
        counts = {row[0]: row[1] for row in rows}
        counts["ALL"] = sum(counts.values())
        return counts

    def get_ready_for_download(self) -> list[tuple]:
        stmt = select(
            Document.id, Document.url, Document.document_type, Document.uuid,
        ).where(Document.processing_status == StalkerDocumentStatus.URL_ADDED.name)

        rows = self.session.execute(stmt).all()
        return [
            (row.id, row.url, row.document_type, row.uuid)
            for row in rows
        ]

    def get_youtube_just_added(self) -> list[tuple]:
        stmt = select(
            Document.id, Document.url, Document.document_type,
            Document.language, Document.chapter_list, Document.ai_summary_needed,
        ).where(
            Document.document_type == StalkerDocumentType.youtube.name,
            or_(
                Document.processing_status == StalkerDocumentStatus.URL_ADDED.name,
                Document.processing_status == StalkerDocumentStatus.NEED_TRANSCRIPTION.name,
                Document.processing_status == StalkerDocumentStatus.TEMPORARY_ERROR.name,
            ),
        )

        rows = self.session.execute(stmt).all()
        return [
            (row.id, row.url, row.document_type,
             row.language, row.chapter_list, row.ai_summary_needed)
            for row in rows
        ]

    def get_transcription_done(self) -> list[int]:
        stmt = select(Document.id).where(
            Document.processing_status == StalkerDocumentStatus.TRANSCRIPTION_DONE.name,
        ).order_by(Document.id)

        rows = self.session.execute(stmt).all()
        return [row[0] for row in rows]

    def get_next_to_correct(self, document_id: int, document_type: str = "ALL",
                            processing_status: str = "ALL") -> tuple[int, str] | int:
        stmt = select(Document.id, Document.document_type).where(Document.id > document_id)

        if document_type != "ALL":
            stmt = stmt.where(Document.document_type == document_type)

        if processing_status != "ALL":
            stmt = stmt.where(Document.processing_status == processing_status)

        stmt = stmt.order_by(Document.id.asc()).limit(1)

        row = self.session.execute(stmt).first()
        if row is None:
            return -1
        return (row[0], row[1])

    def get_last_unknown_news(self) -> datetime.date | None:
        return self.get_last_by_source('https://unknow.news/')

    def get_last_by_source(self, source_name: str) -> datetime.date | None:
        """Return the most recent published_on for documents with a given discovery source."""
        from library.db.models import DiscoverySource
        stmt = select(func.max(Document.published_on)).where(
            Document.discovery_source_id.in_(
                select(DiscoverySource.id).where(DiscoverySource.name == source_name)
            ),
        )
        return self.session.execute(stmt).scalar()

    def load_neighbors(self, doc) -> None:
        """Populate doc.next_id, next_type, previous_id, previous_type."""
        Document.populate_neighbors(self.session, doc)

    # ------------------------------------------------------------------
    # Similarity search
    # ------------------------------------------------------------------

    def get_similar(self, embedding, model: str, limit: int = 3, minimal_similarity: float = 0.30,
                    filters=None) -> list[dict[str, Any]] | None:
        """Vector similarity search.

        ``filters`` (an optional ``library.search.types.SearchFilters``) is
        applied via ``library.search.sql_filters.build_document_filters()``
        — the SAME builder ``search_text()`` uses — before ``LIMIT``, so
        vector and lexical search share identical constraints (stage 6
        acceptance criterion). Collection filtering goes through
        ``filters.collection_name`` (stage 11c removed the legacy ``project``
        kwarg — no HTTP caller ever passed it).
        """

        if minimal_similarity is None:
            minimal_similarity = 0.30
        if embedding is None:
            return None

        similarity = (
            literal(1) - func.cast(
                DocumentEmbedding.embedding.cosine_distance(embedding),
                Float,
            )
        ).label("similarity")

        stmt = (
            select(
                DocumentEmbedding.document_id,
                DocumentEmbedding.text,
                similarity,
                DocumentEmbedding.id,
                Document.url,
                Document.language,
                DocumentEmbedding.text_original,
                func.length(Document.text).label("websites_text_length"),
                func.length(DocumentEmbedding.text).label("embeddings_text_length"),
                Document.title,
                Document.document_type,
                Document.collection_id,
                Document.published_on,
                Document.ingested_at,
                DocumentEmbedding.chunk_id,
                DocumentChunk.obsidian_note_paths,
            )
            .outerjoin(Document, DocumentEmbedding.document_id == Document.id)
            .outerjoin(DocumentChunk, DocumentEmbedding.chunk_id == DocumentChunk.id)
            .where(DocumentEmbedding.model == model)
            .where(
                literal(1) - func.cast(
                    DocumentEmbedding.embedding.cosine_distance(embedding),
                    Float,
                ) > minimal_similarity
            )
            .order_by(DocumentEmbedding.embedding.cosine_distance(embedding))
            .limit(limit)
        )

        if filters is not None:
            from library.search.sql_filters import build_document_filters
            stmt = stmt.where(*build_document_filters(filters))

        rows = self.session.execute(stmt).all()
        return [
            {
                "document_id": r.document_id,
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
                "collection_id": r.collection_id,
                "published_on": r.published_on.isoformat() if r.published_on else None,
                "ingested_at": r.ingested_at.isoformat() if r.ingested_at else None,
                "chunk_id": r.chunk_id,
                "obsidian_note_paths": r.obsidian_note_paths or [],
            }
            for r in rows
        ]

    def search_text(self, query: str, limit: int = 20, filters=None) -> list[dict[str, Any]]:
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
            func.coalesce(Document.title, ""),
            func.coalesce(Document.tags, ""),
            func.coalesce(Document.note, ""),
            func.coalesce(Document.text, ""),
        ))
        title = func.unaccent(func.coalesce(Document.title, ""))
        phrase = func.unaccent(f"%{query}%")
        conditions = [title.ilike(phrase), searchable.ilike(phrase)]
        if tokens:
            conditions.append(and_(*(searchable.ilike(func.unaccent(f"%{token}%")) for token in tokens)))

        stmt = (
            select(Document)
            .where(or_(*conditions))
            .order_by(Document.ingested_at.desc(), Document.id.desc())
            .limit(limit)
        )
        if filters is not None:
            from library.search.sql_filters import build_document_filters
            stmt = stmt.where(*build_document_filters(filters))

        documents = self.session.scalars(stmt).all()
        return [
            {
                "document_id": doc.id,
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
                "collection_id": doc.collection_id,
                "published_on": doc.published_on.isoformat() if doc.published_on else None,
                "ingested_at": doc.ingested_at.isoformat() if doc.ingested_at else None,
                "chunk_id": None,
                "obsidian_note_paths": doc.obsidian_note_paths or [],
                "tags": doc.tags,
                "note": doc.note,
            }
            for doc in documents
        ]

    def list_by_filters(self, filters, limit: int = 20, offset: int = 0, sort=None) -> list[dict[str, Any]]:
        """Filter-only document listing: no text query, no embedding involved.

        Applies the SAME build_document_filters() search_text()/get_similar()
        use, before LIMIT — filter-only listing shares the identical
        constraints too (stage 6 session B of the search-rebuild plan). An
        empty ``filters`` object is legal and lists everything, newest
        first, matching ParsedSearchQuery's own "no criteria means list
        everything" semantics.

        ``sort`` is a ``library.search.types.SearchSort``; RELEVANCE has no
        meaning without a text query, so it falls back to the same
        newest-first ordering as INGESTED_DESC.
        """
        from library.search.sql_filters import build_document_filters
        from library.search.types import SearchSort

        sort_columns = {
            SearchSort.PUBLISHED_DESC: Document.published_on.desc(),
            SearchSort.PUBLISHED_ASC: Document.published_on.asc(),
            SearchSort.INGESTED_DESC: Document.ingested_at.desc(),
            SearchSort.RELEVANCE: Document.ingested_at.desc(),
        }
        order = sort_columns[SearchSort(sort) if sort is not None else SearchSort.RELEVANCE]

        stmt = (
            select(Document)
            .where(*build_document_filters(filters))
            .order_by(order, Document.id.desc())
            .limit(limit)
            .offset(offset)
        )

        documents = self.session.scalars(stmt).all()
        return [
            {
                "document_id": doc.id,
                "title": doc.title,
                "url": doc.url,
                "document_type": doc.document_type,
                "collection_id": doc.collection_id,
                "language": doc.language,
                "published_on": doc.published_on.isoformat() if doc.published_on else None,
                "ingested_at": doc.ingested_at.isoformat() if doc.ingested_at else None,
                "similarity": None,
                "search_match": "filters_only",
            }
            for doc in documents
        ]

    # ------------------------------------------------------------------
    # Embedding CRUD
    # ------------------------------------------------------------------

    def embedding_add(self, document_id, embedding, language, text, text_original, model, chunk_id=None) -> None:
        emb = DocumentEmbedding(
            document_id=document_id,
            language=language,
            text=text,
            text_original=text_original,
            embedding=embedding,
            model=model,
            chunk_id=chunk_id,
        )
        self.session.add(emb)

    def embedding_delete(self, document_id: int, model: str) -> None:
        stmt = delete(DocumentEmbedding).where(
            DocumentEmbedding.document_id == document_id,
            DocumentEmbedding.model == model,
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
            select(Document.id)
            .outerjoin(
                DocumentEmbedding,
                and_(
                    Document.id == DocumentEmbedding.document_id,
                    DocumentEmbedding.model == embedding_model,
                ),
            )
            .where(
                DocumentEmbedding.document_id.is_(None),
                Document.processing_status.in_([
                    StalkerDocumentStatus.READY_FOR_EMBEDDING.name,
                    StalkerDocumentStatus.EMBEDDING_EXIST.name,
                    StalkerDocumentStatus.MD_SIMPLIFIED.name,
                ]),
                or_(
                    func.length(func.coalesce(Document.text_md, "")) > 0,
                    func.length(func.coalesce(Document.text, "")) > 0,
                    and_(
                        Document.document_type == StalkerDocumentType.link.name,
                        func.length(func.coalesce(Document.title, "")) > 0,
                    ),
                ),
            )
            .order_by(Document.id)
        )
        rows = self.session.execute(stmt).all()
        return [row[0] for row in rows]

    def get_documents_md_needed(self, min_id: int = 0) -> list[int]:
        """
        Pobiera listę identyfikatorów dokumentów, które mają null w kolumnie `text_md` i wartość false w kolumnie `paywall`.
        """
        min_id = int(min_id)

        stmt = select(Document.id).where(
            Document.text_md.is_(None),
            or_(Document.paywall == False, Document.paywall.is_(None)),  # noqa: E712
            Document.document_type == StalkerDocumentType.webpage.name,
            Document.id > min_id,
        ).order_by(Document.id)
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

        stmt = select(Document.id).where(
            Document.url.like(pattern, escape="\\"),
            Document.document_type == StalkerDocumentType.webpage.name,
            Document.id > min_id,
            or_(
                and_(
                    Document.processing_status == StalkerDocumentStatus.ERROR.name,
                    Document.processing_error_code == StalkerDocumentStatusError.REGEX_ERROR.name,
                ),
                Document.processing_status == StalkerDocumentStatus.URL_ADDED.name,
            ),
        ).order_by(Document.id)
        rows = self.session.execute(stmt).all()
        return [row[0] for row in rows]

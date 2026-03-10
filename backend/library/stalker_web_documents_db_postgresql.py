import datetime
import logging
from typing import Any

from sqlalchemy import Float, and_, column, delete, func, literal, or_, select, union
from sqlalchemy.orm import Session

from library.db.models import WebDocument, WebsiteEmbedding
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
                 start_id=None) -> list[dict[str, Any]]:

        if count:
            stmt = select(func.count(WebDocument.id))
        else:
            stmt = select(
                WebDocument.id, WebDocument.url, WebDocument.title, WebDocument.document_type,
                WebDocument.created_at, WebDocument.document_state, WebDocument.document_state_error,
                WebDocument.note, WebDocument.project, WebDocument.s3_uuid,
            )

        # Dynamic filters
        if document_type != "ALL":
            stmt = stmt.where(WebDocument.document_type == StalkerDocumentType[document_type])

        if document_state != "ALL":
            stmt = stmt.where(WebDocument.document_state == StalkerDocumentStatus[document_state])

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
                WebDocument.url.ilike(pattern),
                WebDocument.text.ilike(pattern),
                WebDocument.title.ilike(pattern),
                WebDocument.summary.ilike(pattern),
                WebDocument.chapter_list.ilike(pattern),
            ))

        if count:
            return self.session.execute(stmt).scalar()

        stmt = stmt.order_by(WebDocument.created_at.desc())
        stmt = stmt.limit(limit).offset(offset * limit)

        rows = self.session.execute(stmt).all()
        result = []
        for row in rows:
            doc_type = row.document_type
            doc_state = row.document_state
            doc_state_error = row.document_state_error
            result.append({
                "id": row.id,
                "url": row.url,
                "title": row.title,
                "document_type": doc_type.name if hasattr(doc_type, "name") else doc_type,
                "created_at": row.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                "document_state": doc_state.name if hasattr(doc_state, "name") else doc_state,
                "document_state_error": doc_state_error.name if hasattr(doc_state_error, "name") else doc_state_error,
                "note": row.note,
                "project": row.project,
                "s3_uuid": row.s3_uuid,
            })
        return result

    def get_count(self, document_type: str = "ALL") -> int:
        stmt = select(func.count(WebDocument.id))
        if document_type != "ALL":
            stmt = stmt.where(WebDocument.document_type == StalkerDocumentType[document_type])
        return self.session.execute(stmt).scalar()

    def get_count_by_type(self) -> dict[str, int]:
        """Return document counts grouped by type, plus 'ALL' total."""
        stmt = select(WebDocument.document_type, func.count(WebDocument.id)).group_by(WebDocument.document_type)
        rows = self.session.execute(stmt).all()
        counts = {row[0].name if hasattr(row[0], "name") else row[0]: row[1] for row in rows}
        counts["ALL"] = sum(counts.values())
        return counts

    def get_ready_for_download(self) -> list[tuple]:
        stmt = select(
            WebDocument.id, WebDocument.url, WebDocument.document_type, WebDocument.s3_uuid,
        ).where(WebDocument.document_state == StalkerDocumentStatus.URL_ADDED)

        rows = self.session.execute(stmt).all()
        return [
            (row.id, row.url, row.document_type.name if hasattr(row.document_type, "name") else row.document_type, row.s3_uuid)
            for row in rows
        ]

    def get_youtube_just_added(self) -> list[tuple]:
        stmt = select(
            WebDocument.id, WebDocument.url, WebDocument.document_type,
            WebDocument.language, WebDocument.chapter_list, WebDocument.ai_summary_needed,
        ).where(
            WebDocument.document_type == StalkerDocumentType.youtube,
            or_(
                WebDocument.document_state == StalkerDocumentStatus.URL_ADDED,
                WebDocument.document_state == StalkerDocumentStatus.NEED_TRANSCRIPTION,
                WebDocument.document_state == StalkerDocumentStatus.TEMPORARY_ERROR,
            ),
        )

        rows = self.session.execute(stmt).all()
        return [
            (row.id, row.url, row.document_type.name if hasattr(row.document_type, "name") else row.document_type,
             row.language, row.chapter_list, row.ai_summary_needed)
            for row in rows
        ]

    def get_transcription_done(self) -> list[int]:
        stmt = select(WebDocument.id).where(
            WebDocument.document_state == StalkerDocumentStatus.TRANSCRIPTION_DONE,
        ).order_by(WebDocument.id)

        rows = self.session.execute(stmt).all()
        return [row[0] for row in rows]

    def get_next_to_correct(self, website_id: int, document_type: str = "ALL",
                            document_state: str = "ALL") -> tuple[int, str] | int:
        stmt = select(WebDocument.id, WebDocument.document_type).where(WebDocument.id > website_id)

        if document_type != "ALL":
            stmt = stmt.where(WebDocument.document_type == StalkerDocumentType[document_type])

        if document_state != "ALL":
            stmt = stmt.where(WebDocument.document_state == StalkerDocumentStatus[document_state])

        stmt = stmt.order_by(WebDocument.id.asc()).limit(1)

        row = self.session.execute(stmt).first()
        if row is None:
            return -1
        return (row[0], row[1].name if hasattr(row[1], "name") else row[1])

    def get_last_unknown_news(self) -> datetime.date | None:
        stmt = select(func.max(WebDocument.date_from)).where(
            WebDocument.document_type == StalkerDocumentType.link,
            WebDocument.source == 'https://unknow.news/',
        )
        return self.session.execute(stmt).scalar()

    def load_neighbors(self, doc) -> None:
        """Populate doc.next_id, next_type, previous_id, previous_type."""
        WebDocument.populate_neighbors(self.session, doc)

    # ------------------------------------------------------------------
    # Similarity search
    # ------------------------------------------------------------------

    def get_similar(self, embedding, model: str, limit: int = 3, minimal_similarity: float = 0.30, project=None) -> list[dict[
            str, Any]] | None:

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
            )
            .outerjoin(WebDocument, WebsiteEmbedding.website_id == WebDocument.id)
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
                "document_type": r.document_type.name if hasattr(r.document_type, "name") else r.document_type,
                "project": r.project,
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Embedding CRUD
    # ------------------------------------------------------------------

    def embedding_add(self, website_id, embedding, language, text, text_original, model) -> None:
        emb = WebsiteEmbedding(
            website_id=website_id,
            language=language,
            text=text,
            text_original=text_original,
            embedding=embedding,
            model=model,
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
        # Documents in READY_FOR_EMBEDDING state
        stmt1 = select(WebDocument.id).where(
            WebDocument.document_state == StalkerDocumentStatus.READY_FOR_EMBEDDING,
        )
        # Documents in EMBEDDING_EXIST state missing embedding for this model
        stmt2 = (
            select(WebDocument.id)
            .outerjoin(
                WebsiteEmbedding,
                and_(
                    WebDocument.id == WebsiteEmbedding.website_id,
                    WebsiteEmbedding.model == embedding_model,
                ),
            )
            .where(
                WebDocument.document_state == StalkerDocumentStatus.EMBEDDING_EXIST,
                WebsiteEmbedding.website_id.is_(None),
            )
        )
        stmt = union(stmt1, stmt2).order_by(column("id"))
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
            WebDocument.document_type == StalkerDocumentType.webpage,
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

        stmt = select(WebDocument.id).where(
            WebDocument.url.like(f"{escaped_url}%"),
            WebDocument.document_type == StalkerDocumentType.webpage,
            WebDocument.id > min_id,
            or_(
                and_(
                    WebDocument.document_state == StalkerDocumentStatus.ERROR,
                    WebDocument.document_state_error == StalkerDocumentStatusError.REGEX_ERROR,
                ),
                WebDocument.document_state == StalkerDocumentStatus.URL_ADDED,
            ),
        ).order_by(WebDocument.id)
        rows = self.session.execute(stmt).all()
        return [row[0] for row in rows]

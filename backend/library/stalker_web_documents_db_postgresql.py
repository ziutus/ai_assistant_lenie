import datetime
import logging
import os
from typing import Any

import psycopg2
from sqlalchemy import and_, column, delete, func, or_, select, union
from sqlalchemy.orm import Session

from library.db.models import WebDocument, WebsiteEmbedding
from library.models.stalker_document_status import StalkerDocumentStatus
from library.models.stalker_document_type import StalkerDocumentType

logger = logging.getLogger(__name__)


class WebsitesDBPostgreSQL:
    def __init__(self, session: Session = None):
        self.session = session
        if session is None:
            # Legacy psycopg2 connection for backward compatibility
            connect_kwargs = {
                "host": os.getenv("POSTGRESQL_HOST"),
                "database": os.getenv("POSTGRESQL_DATABASE"),
                "user": os.getenv("POSTGRESQL_USER"),
                "password": os.getenv("POSTGRESQL_PASSWORD"),
                "port": os.getenv("POSTGRESQL_PORT"),
            }
            sslmode = os.getenv("POSTGRESQL_SSLMODE")
            if sslmode:
                connect_kwargs["sslmode"] = sslmode
            self.conn = psycopg2.connect(**connect_kwargs)
            self.embedding = os.getenv("EMBEDDING_MODEL")

    def is_connection_open(self) -> bool:
        return self.conn.closed == 0

    def close(self):
        self.conn.close()

    # ------------------------------------------------------------------
    # Query methods — ORM when session is provided, legacy psycopg2 otherwise
    # ------------------------------------------------------------------

    def get_list(self, limit: int = 100, offset: int = 0, document_type: str = "ALL", document_state: str = "ALL",
                 search_in_documents=None, count=False, project=None, ai_summary_needed: bool = None,
                 ai_correction_needed: bool = None, start_id=None) -> list[dict[str, Any]]:

        if self.session is None:
            return self._get_list_legacy(
                limit=limit, offset=offset, document_type=document_type, document_state=document_state,
                search_in_documents=search_in_documents, count=count, project=project,
                ai_summary_needed=ai_summary_needed, ai_correction_needed=ai_correction_needed, start_id=start_id,
            )

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

        # ai_correction_needed — silently ignored (column does not exist in DB/model)

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

    def _get_list_legacy(self, limit: int = 100, offset: int = 0, document_type: str = "ALL",
                         document_state: str = "ALL", search_in_documents=None, count=False, project=None,
                         ai_summary_needed: bool = None, ai_correction_needed: bool = None, start_id=None):
        offset = offset * limit

        if count:
            base_query = "SELECT count(id) FROM public.web_documents"
        else:
            base_query = "SELECT id, url, title, document_type, created_at, document_state, document_state_error, note, project, s3_uuid FROM public.web_documents"

        order_by = "ORDER BY created_at DESC"
        where_clauses = []
        params = []

        if document_type != "ALL":
            where_clauses.append("document_type = %s")
            params.append(document_type)

        if document_state != "ALL":
            where_clauses.append("document_state = %s")
            params.append(document_state)

        if project:
            where_clauses.append("project = %s")
            params.append(project)

        if ai_correction_needed is not None:
            where_clauses.append("ai_correction_needed = %s")
            params.append(ai_correction_needed)

        if ai_summary_needed is not None:
            where_clauses.append("ai_summary_needed = %s")
            params.append(ai_summary_needed)

        if start_id:
            start_id = int(start_id)
            where_clauses.append("id >= %s")
            params.append(start_id)

        if search_in_documents:
            search_fields = ["url", "text", "title", "summary", "chapter_list"]
            search_clauses = [f"{field} LIKE %s" for field in search_fields]
            escaped = search_in_documents.replace("%", "\\%").replace("_", "\\_")
            search_pattern = f"%{escaped}%"
            params.extend([search_pattern] * len(search_fields))
            where_clauses.append(f"({' OR '.join(search_clauses)})")

        if where_clauses:
            where_query = " WHERE " + " AND ".join(where_clauses)
        else:
            where_query = ""

        if count:
            query = f"{base_query}{where_query}"
        else:
            query = f"{base_query}{where_query} {order_by} LIMIT %s OFFSET %s"
            params.extend([int(limit), int(offset)])

        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute(query, params if params else None)

                if count:
                    return cur.fetchone()[0]
                else:
                    result = []
                    for line in cur.fetchall():
                        dt = line[4]
                        result.append({
                            "id": line[0],
                            "url": line[1],
                            "title": line[2],
                            "document_type": line[3],
                            "created_at": dt.strftime('%Y-%m-%d %H:%M:%S'),
                            "document_state": line[5],
                            "document_state_error": line[6],
                            "note": line[7],
                            "project": line[8],
                            "s3_uuid": line[9],
                        })
                    return result

    def get_count(self, document_type: str = "ALL") -> int:
        if self.session is None:
            if document_type != "ALL":
                with self.conn:
                    with self.conn.cursor() as cur:
                        cur.execute("SELECT count(id) FROM public.web_documents WHERE document_type = %s",
                                    (document_type,))
                        return cur.fetchone()[0]
            with self.conn:
                with self.conn.cursor() as cur:
                    cur.execute("SELECT count(id) FROM public.web_documents")
                    return cur.fetchone()[0]

        stmt = select(func.count(WebDocument.id))
        if document_type != "ALL":
            stmt = stmt.where(WebDocument.document_type == StalkerDocumentType[document_type])
        return self.session.execute(stmt).scalar()

    def get_count_by_type(self) -> dict[str, int]:
        """Return document counts grouped by type, plus 'ALL' total."""
        if self.session is None:
            with self.conn:
                with self.conn.cursor() as cur:
                    cur.execute(
                        "SELECT document_type, count(id) FROM public.web_documents GROUP BY document_type"
                    )
                    rows = cur.fetchall()
                    counts = {row[0]: row[1] for row in rows}
                    counts["ALL"] = sum(counts.values())
                    return counts

        stmt = select(WebDocument.document_type, func.count(WebDocument.id)).group_by(WebDocument.document_type)
        rows = self.session.execute(stmt).all()
        counts = {row[0].name if hasattr(row[0], "name") else row[0]: row[1] for row in rows}
        counts["ALL"] = sum(counts.values())
        return counts

    def get_ready_for_download(self) -> list[tuple]:
        if self.session is None:
            cursor = self.conn.cursor()
            cursor.execute(
                f"SELECT id, url, document_type, s3_uuid FROM public.web_documents WHERE document_state = '{StalkerDocumentStatus.URL_ADDED.name}'"
            )
            return cursor.fetchall()

        stmt = select(
            WebDocument.id, WebDocument.url, WebDocument.document_type, WebDocument.s3_uuid,
        ).where(WebDocument.document_state == StalkerDocumentStatus.URL_ADDED)

        rows = self.session.execute(stmt).all()
        return [
            (row.id, row.url, row.document_type.name if hasattr(row.document_type, "name") else row.document_type, row.s3_uuid)
            for row in rows
        ]

    def get_youtube_just_added(self) -> list[tuple]:
        if self.session is None:
            cursor = self.conn.cursor()
            cursor.execute(
                f"SELECT id, url, document_type, language, chapter_list, ai_summary_needed FROM public.web_documents WHERE document_type='youtube' and (document_state = '{StalkerDocumentStatus.URL_ADDED.name}' or document_state = '{StalkerDocumentStatus.NEED_TRANSCRIPTION.name}' )"
            )
            return cursor.fetchall()

        stmt = select(
            WebDocument.id, WebDocument.url, WebDocument.document_type,
            WebDocument.language, WebDocument.chapter_list, WebDocument.ai_summary_needed,
        ).where(
            WebDocument.document_type == StalkerDocumentType.youtube,
            or_(
                WebDocument.document_state == StalkerDocumentStatus.URL_ADDED,
                WebDocument.document_state == StalkerDocumentStatus.NEED_TRANSCRIPTION,
            ),
        )

        rows = self.session.execute(stmt).all()
        return [
            (row.id, row.url, row.document_type.name if hasattr(row.document_type, "name") else row.document_type,
             row.language, row.chapter_list, row.ai_summary_needed)
            for row in rows
        ]

    def get_transcription_done(self) -> list[int]:
        if self.session is None:
            query = f"""
                SELECT id
                FROM public.web_documents
                WHERE public.web_documents.document_state = '{StalkerDocumentStatus.TRANSCRIPTION_DONE.name}'
                ORDER BY id
                """
            cursor = self.conn.cursor()
            cursor.execute(query)
            return [r[0] for r in cursor.fetchall()]

        stmt = select(WebDocument.id).where(
            WebDocument.document_state == StalkerDocumentStatus.TRANSCRIPTION_DONE,
        ).order_by(WebDocument.id)

        rows = self.session.execute(stmt).all()
        return [row[0] for row in rows]

    def get_next_to_correct(self, website_id: int, document_type: str = "ALL",
                            document_state: str = "ALL") -> tuple[int, str] | int:
        if self.session is None:
            base_query = "SELECT id, document_type FROM public.web_documents"
            where_clauses = ["id > %s"]
            params = [website_id]
            if document_type != "ALL":
                where_clauses.append("document_type = %s")
                params.append(document_type)
            if document_state != "ALL":
                where_clauses.append("document_state = %s")
                params.append(document_state)
            where_query = " WHERE " + " AND ".join(where_clauses)
            with self.conn:
                with self.conn.cursor() as cur:
                    cur.execute(f"{base_query}{where_query} ORDER BY id LIMIT 1", params)
                    result = cur.fetchone()
                    if result is None:
                        return -1
                    return result

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
        if self.session is None:
            query = f"""
                SELECT MAX(date_from) AS latest_entry
                FROM web_documents
                WHERE document_type = '{StalkerDocumentType.link.name}' AND source = 'https://unknow.news/'
            """
            with self.conn:
                with self.conn.cursor() as cur:
                    cur.execute(query)
                    return cur.fetchone()[0]

        stmt = select(func.max(WebDocument.date_from)).where(
            WebDocument.document_type == StalkerDocumentType.link,
            WebDocument.source == 'https://unknow.news/',
        )
        return self.session.execute(stmt).scalar()

    def load_neighbors(self, doc) -> None:
        """Populate doc.next_id, next_type, previous_id, previous_type."""
        if self.session is None:
            raise RuntimeError("load_neighbors() requires an ORM session")
        WebDocument.populate_neighbors(self.session, doc)

    # ------------------------------------------------------------------
    # Legacy psycopg2-only methods — NOT in scope for Story 27.2
    # These will be migrated in their respective stories (Epics 28-29).
    # ------------------------------------------------------------------

    def get_similar(self, embedding, model: str, limit: int = 3, minimal_similarity: float = 0.30, project=None) -> list[dict[
            str, Any]] | None:

        if minimal_similarity is None:
            minimal_similarity = 0.30
        if embedding is None:
            return None

        if project:
            where_project = " AND public.web_documents.project = '" + project + "' "
        else:
            where_project = ""

        query = f"""
            SELECT public.websites_embeddings.website_id,
            public.websites_embeddings.text,
            1 - (public.websites_embeddings.embedding <=> '{embedding}') AS cosine_similarity,
            public.websites_embeddings.id,
            public.web_documents.url,
            public.web_documents.language,
            public.websites_embeddings.text_original,
            LENGTH(public.web_documents.text) AS websites_text_length,
            LENGTH(public.websites_embeddings.text) AS embeddings_text_length,
            public.web_documents.title,
            public.web_documents.document_type,
            public.web_documents.project
            FROM public.websites_embeddings
            left join public.web_documents on public.websites_embeddings.website_id = public.web_documents.id
            WHERE public.websites_embeddings.model = '{model}' {where_project}
            AND (1 - (public.websites_embeddings.embedding <=> '{embedding}')) > {minimal_similarity}
            ORDER BY cosine_similarity desc
            LIMIT {limit}
            """

        cursor = self.conn.cursor()
        cursor.execute(query)

        result = []
        for r in cursor.fetchall():
            result.append({
                "website_id": r[0],
                "text": r[1],
                "similarity": r[2],
                "id": r[3],
                "url": r[4],
                "language": r[5],
                "text_original": r[6],
                "websites_text_length": r[7],
                "embeddings_text_length": r[8],
                "title": r[9],
                "document_type": r[10],
                "project": r[11],
            })

        return result

    def embedding_add(self, website_id, embedding, language, text, text_original, model) -> None:
        if self.session:
            emb = WebsiteEmbedding(
                website_id=website_id,
                language=language,
                text=text,
                text_original=text_original,
                embedding=embedding,
                model=model,
            )
            self.session.add(emb)
        else:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO public.websites_embeddings (website_id, language, text, embedding, model, text_original) "
                "VALUES (%s,%s, %s, %s, %s,%s)",
                (website_id, language, text, embedding, model, text_original)
            )
            self.conn.commit()

    def embedding_delete(self, website_id: int, model: str) -> None:
        if self.session:
            stmt = delete(WebsiteEmbedding).where(
                WebsiteEmbedding.website_id == website_id,
                WebsiteEmbedding.model == model,
            )
            self.session.execute(stmt)
        else:
            cursor = self.conn.cursor()
            cursor.execute(
                "DELETE FROM public.websites_embeddings WHERE website_id = %s and model = %s",
                (website_id, model),
            )
            self.conn.commit()

    def get_documents_needing_embedding(self, embedding_model: str) -> list[int]:
        if self.session:
            # ORM branch: compare enum members directly — SAEnum mapping handles str conversion.
            # Legacy branch below uses .name strings because raw SQL requires literal values.
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
        else:
            query = f"""
                SELECT id FROM web_documents WHERE document_state = '{StalkerDocumentStatus.READY_FOR_EMBEDDING.name}'
                UNION
                SELECT wd.id FROM web_documents wd
                    LEFT JOIN websites_embeddings we ON wd.id = we.website_id AND we.model = '{embedding_model}'
                    WHERE we.website_id IS NULL AND wd.document_state = '{StalkerDocumentStatus.EMBEDDING_EXIST.name}'
                ORDER BY id
            """
            cursor = self.conn.cursor()
            cursor.execute(query)

            result = []
            for r in cursor.fetchall():
                result.append(r[0])

            return result

    def get_documents_md_needed(self, min: str = 0) -> list[int]:
        """
        Pobiera listę identyfikatorów dokumentów, które mają null w kolumnie `text_md` i wartość false w kolumnie `paywall`.
        """
        min = int(min)

        query = f"""
            SELECT id
            FROM web_documents as wd
            WHERE wd.text_md IS NULL AND (wd.paywall = false OR paywall IS NULL)  AND document_type='webpage'  AND wd.id > {min}
            ORDER by wd.id
        """

        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute(query)
                result = cur.fetchall()
                # Zwróć listę id
                return [row[0] for row in result]

    def get_documents_by_url(self, url: str, min: str = 0) -> list[int]:

        """
        Retrieves a list of document IDs where the URL starts with the specified prefix, the document type is 'webpage',
        and the document ID is greater than the provided minimum value (`min`).
        """
        min = int(min)

        query = f"""
            SELECT id
            FROM web_documents as wd
            WHERE url like '{url}%'  AND document_type='webpage'  AND wd.id > {min} and ((document_state='ERROR' and document_state_error='REGEX_ERROR') OR document_state='URL_ADDED')
            ORDER by wd.id
        """

        logger.debug("query: %s", query)

        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute(query)
                result = cur.fetchall()
                # Zwróć listę id
                return [row[0] for row in result]

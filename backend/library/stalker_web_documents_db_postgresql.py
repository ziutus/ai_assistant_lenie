import logging
import os
from typing import Any

import psycopg2

from library.models.stalker_document_status import StalkerDocumentStatus
from library.models.stalker_document_type import StalkerDocumentType


class WebsitesDBPostgreSQL:
    def __init__(self):
        if os.getenv("DEBUG", "").lower() == "true":
            logging.info(
                "Connecting to PostgreSQL host=%s db=%s user=%s port=%s password_set=%s",
                os.getenv("POSTGRESQL_HOST"),
                os.getenv("POSTGRESQL_DATABASE"),
                os.getenv("POSTGRESQL_USER"),
                os.getenv("POSTGRESQL_PORT"),
                bool(os.getenv("POSTGRESQL_PASSWORD")),
            )

        self.conn = psycopg2.connect(
            host=os.getenv("POSTGRESQL_HOST"),
            database=os.getenv("POSTGRESQL_DATABASE"),
            user=os.getenv("POSTGRESQL_USER"),
            password=os.getenv("POSTGRESQL_PASSWORD"),
            port=os.getenv("POSTGRESQL_PORT")
        )

        self.embedding = os.getenv("EMBEDDING_MODEL")

    def is_connection_open(self) -> bool:
        return self.conn.closed == 0

    def get_next_to_correct(self, website_id, document_type="ALL", document_state="ALL") -> [int, str]:
        # "SELECT id, document_type FROM public.web_documents WHERE id > %s and document_state = '{StalkerDocumentStatus.NEED_MANUAL_REVIEW.name}' ORDER BY id LIMIT 1"

        base_query = "SELECT id, document_type FROM public.web_documents"

        where_clauses = []

        if document_type != "ALL":
            where_clauses.append(f"document_type = '{document_type}'")

        if document_state != "ALL":
            where_clauses.append(f"document_state = '{document_state}'")

        # Łączenie warunków zapytania
        if where_clauses:
            where_query = " WHERE  id > %s AND " + " AND ".join(where_clauses)
        else:
            where_query = " WHERE  id > %s "

        # Końcowe zapytanie
        query = f"{base_query} {where_query} ORDER BY id LIMIT 1"

        print(query)

        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute(f"{base_query} {where_query} ORDER BY id LIMIT 1", (website_id,))
                result = cur.fetchone()
                if result is None:
                    return -1
                return result

    def close(self):
        self.conn.close()

    def get_list(self, limit: int = 100, offset: int = 0, document_type: str = "ALL", document_state: str = "ALL",
                 search_in_documents = None, count = False, project = None, ai_summary_needed: bool = None,# noqa
                 ai_correction_needed: bool = None, start_id = None) -> \
            list[
                dict[str, str, str, str, str, str, str, str, str]]:
        offset = offset * limit

        print(f"count: {count}")

        if count:
            base_query = "SELECT count(id) FROM public.web_documents"
        else:
            base_query = "SELECT id, url, title, document_type, created_at, document_state, document_state_error, note, project, s3_uuid FROM public.web_documents"


        order_by = "ORDER BY created_at DESC"
        limit_offset = f"LIMIT {int(limit)} OFFSET {int(offset)}"

        where_clauses = []

        if document_type != "ALL":
            where_clauses.append(f"document_type = '{document_type}'")

        if document_state != "ALL":
            where_clauses.append(f"document_state = '{document_state}'")

        if project:
            where_clauses.append(f"document_state = '{project}'")

        if ai_correction_needed:
            where_clauses.append(f"ai_correction_needed = '{ai_correction_needed}'")

        if ai_summary_needed:
            where_clauses.append(f"ai_summary_needed = '{ai_summary_needed}'")

        if start_id:
            start_id = int(start_id)
            where_clauses.append(f"id >= {start_id} ")


        if search_in_documents:
            search_clauses = [f"text LIKE '%{search_in_documents}%'",
                              f"title LIKE '%{search_in_documents}%'",
                              f"summary LIKE '%{search_in_documents}%'",
                              f"chapter_list LIKE '%{search_in_documents}%'",
                              f"summary_english LIKE '%{search_in_documents}%'",
                              f"text_english LIKE '%{search_in_documents}%'"]
            where_clauses.append(f"({' OR '.join(search_clauses)})")

        # Łączenie warunków zapytania
        if where_clauses:
            where_query = " WHERE " + " AND ".join(where_clauses)
        else:
            where_query = ""

        # Końcowe zapytanie
        if count:
            query = f"{base_query}{where_query}"
        else:
            query = f"{base_query}{where_query} {order_by} {limit_offset}"

        print(query)

        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute(query)

                if count:
                    result = cur.fetchone()[0]
                    return result
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

    def get_count(self) -> tuple[Any, ...] | None:
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute("SELECT count(id) FROM public.web_documents")
                return cur.fetchone()[0]

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

    def get_ready_for_download(self) -> list[int | str]:
        cursor = self.conn.cursor()
        cursor.execute(
            f"SELECT id, url, document_type, s3_uuid FROM public.web_documents WHERE document_state = '{StalkerDocumentStatus.URL_ADDED.name}'")
        website_data = cursor.fetchall()
        return website_data

    def get_ready_for_embedding(self) -> list[int | str]:
        query = f"""
            SELECT id
            FROM public.web_documents
            WHERE public.web_documents.document_state = '{StalkerDocumentStatus.READY_FOR_EMBEDDING.name}'
            ORDER BY id
           """
        cursor = self.conn.cursor()
        cursor.execute(query)

        result = []
        for r in cursor.fetchall():
            result.append(r[0])

        return result

    def get_transcription_done(self) -> list[int | str]:
        query = f"""
            SELECT id
            FROM public.web_documents
            WHERE public.web_documents.document_state = '{StalkerDocumentStatus.TRANSCRIPTION_DONE.name}'
            ORDER BY id
            """
        cursor = self.conn.cursor()
        cursor.execute(query)

        result = []
        for r in cursor.fetchall():
            result.append(r[0])

        return result

    def get_ready_for_translation(self) -> list[int | str]:
        query = f"""
            SELECT id
            FROM public.web_documents
            WHERE public.web_documents.document_state = '{StalkerDocumentStatus.READY_FOR_TRANSLATION.name}'
            ORDER BY id
            """
        cursor = self.conn.cursor()
        cursor.execute(query)

        result = []
        for r in cursor.fetchall():
            result.append(r[0])

        return result

    def get_youtube_just_added(self):
        cursor = self.conn.cursor()
        cursor.execute(
            f"SELECT id, url, document_type, language, chapter_list, ai_summary_needed FROM public.web_documents WHERE document_type='youtube' and (document_state = '{StalkerDocumentStatus.URL_ADDED.name}' or document_state = '{StalkerDocumentStatus.NEED_TRANSCRIPTION.name}' )")
        website_data = cursor.fetchall()

        return website_data

    def embedding_add(self, website_id, embedding, langauge, text, text_original, model) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO public.websites_embeddings (website_id, langauge, text, embedding, model, text_original) "
            "VALUES (%s,%s, %s, %s, %s,%s)",
            (website_id, langauge, text, embedding, model, text_original)
        )
        self.conn.commit()

    def get_last_unknown_news(self) -> str:
        query = f"""
            SELECT MAX(date_from) AS latest_entry
            FROM web_documents
            WHERE document_type = '{StalkerDocumentType.link.name}' AND source = 'https://unknow.news/'
        """
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute(query)
                return cur.fetchone()[0]

    def get_embedding_missing(self, embedding_model: str) -> list[int | str]:
        cursor = self.conn.cursor()

        query = f"""
            SELECT wd.id
            FROM web_documents wd
                     LEFT JOIN websites_embeddings we
                               ON wd.id = we.website_id AND we.model = '{embedding_model}'
            WHERE we.website_id IS NULL and wd.document_state = 'EMBEDDING_EXIST';
        """

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

        # query = f"""
        #     SELECT id
        #     FROM web_documents as wd
        #     WHERE url like '{url}%'  AND document_type='webpage'  AND wd.id > {min} and document_state='NEED_MANUAL_REVIEW'
        #     ORDER by wd.id
        # """

        query = f"""
            SELECT id
            FROM web_documents as wd
            WHERE url like '{url}%'  AND document_type='webpage'  AND wd.id > {min} and ((document_state='ERROR' and document_state_error='REGEX_ERROR') OR document_state='URL_ADDED') 
            ORDER by wd.id
        """

        print(query)

        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute(query)
                result = cur.fetchall()
                # Zwróć listę id
                return [row[0] for row in result]

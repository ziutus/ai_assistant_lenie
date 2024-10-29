import os
from typing import Any

import psycopg2
from psycopg2 import sql
from pprint import pprint

from library.stalker_web_document import StalkerWebDocument, StalkerDocumentStatus, StalkerDocumentType


class WebsitesDBPostgreSQL:
    def __init__(self):
        # if os.getenv("DEBUG"):
        #     print("Connecting to PostgreSQL database...")
        #     print("POSTGRESQL_HOST: " + os.getenv("POSTGRESQL_HOST"))
        #     print("POSTGRESQL_DATABASE: " + os.getenv("POSTGRESQL_DATABASE"))
        #     print("POSTGRESQL_USER: " + os.getenv("POSTGRESQL_USER"))
        #     print("POSTGRESQL_PASSWORD: " + os.getenv("POSTGRESQL_PASSWORD"))
        #     print("POSTGRESQL_PORT: " + os.getenv("POSTGRESQL_PORT"))

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

    def get_next_to_correct(self, website_id, document_type = "ALL", document_state = "ALL") -> [int, str]:
        # "SELECT id, document_type FROM public.web_documents WHERE id > %s and document_state = '{StalkerDocumentStatus.NEED_MANUAL_REVIEW.name}' ORDER BY id LIMIT 1"

        base_query = "SELECT id, document_type FROM public.web_documents"
        order_by = "ORDER BY id"

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

    def get_list(self, limit: int = 100, offset: int = 0, document_type: str = "ALL", document_state: str = "ALL") -> list[
        dict[str, str, str, str, str]]:
        offset = offset * limit

        base_query = "SELECT id, url, title, document_type, created_at, document_state, document_state_error, note FROM public.web_documents"
        order_by = "ORDER BY created_at DESC"
        limit_offset = f"LIMIT {int(limit)} OFFSET {int(offset)}"

        where_clauses = []

        if document_type != "ALL":
            where_clauses.append(f"document_type = '{document_type}'")

        if document_state != "ALL":
            where_clauses.append(f"document_state = '{document_state}'")

        # Łączenie warunków zapytania
        if where_clauses:
            where_query = " WHERE " + " AND ".join(where_clauses)
        else:
            where_query = ""

        # Końcowe zapytanie
        query = f"{base_query}{where_query} {order_by} {limit_offset}"

        print(query)

        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute(query)
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
                        "note": line[7]
                    })

                return result

    def get_count(self) -> tuple[Any, ...] | None:
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute("SELECT count(id) FROM public.web_documents")
                return cur.fetchone()[0]

    def get_similar(self, embedding, model: str, limit: int = 3, minimal_similarity: float = 0.30) -> list[dict[
        str, Any]] | None:
        if minimal_similarity is None:
            minimal_similarity = 0.30
        if embedding is None:
            return None

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
              public.web_documents.document_type
             FROM public.websites_embeddings
             left join public.web_documents on public.websites_embeddings.website_id = public.web_documents.id  
             WHERE public.websites_embeddings.model = '{model}' 
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
import os

import psycopg2
from psycopg2 import sql

from library.embedding import get_embedding
from library.stalker_web_document import StalkerWebDocument
from library.models.stalker_document_type import StalkerDocumentType
from library.models.stalker_document_status import StalkerDocumentStatus
from library.models.webpage_parse_result import WebPageParseResult


class StalkerWebDocumentDB(StalkerWebDocument):
    db_conn = None

    def __init__(self, url: str = None, document_id: int = None, reach: bool = False,
                 webpage_parse_result: WebPageParseResult | None = None):
        super().__init__(url, webpage_parse_result)
        if not self.db_conn:
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
            self.db_conn = psycopg2.connect(**connect_kwargs)

        self.next_id = None
        self.next_type = None
        self.previous_id = None
        self.previous_type = None

        with self.db_conn:
            with self.db_conn.cursor() as cur:
                select_cols = ("id, summary, url, language, tags, text, paywall, title, created_at, "
                              "document_type, source, date_from, original_id, "
                              "document_length, chapter_list, document_state, document_state_error, "
                              "text_raw, transcript_job_id, ai_summary_needed, author, note, s3_uuid, "
                              "project, text_md")
                if url:
                    cur.execute(f"SELECT {select_cols} FROM public.web_documents WHERE url = %s", (url,))
                elif id:
                    cur.execute(f"SELECT {select_cols} FROM public.web_documents WHERE id = %s", (document_id,))
                else:
                    raise Exception("One of url or id must be provided")

                website_data = cur.fetchone()
                if website_data:
                    self.id = website_data[0]
                    self.summary = website_data[1]
                    self.url = website_data[2]
                    self.language = website_data[3]
                    self.tags = website_data[4]
                    self.text = website_data[5]
                    self.paywall = website_data[6]
                    self.title = website_data[7]
                    self.created_at = website_data[8]
                    self.set_document_type(website_data[9])
                    self.source = website_data[10]
                    self.date_from = website_data[11]
                    self.original_id = website_data[12]
                    self.document_length = website_data[13]
                    self.chapter_list = website_data[14]
                    self.set_document_state(website_data[15])
                    self.set_document_state_error(website_data[16])
                    self.text_raw = website_data[17]
                    self.transcript_job_id = website_data[18]
                    self.ai_summary_needed = website_data[19]
                    self.author = website_data[20]
                    self.note = website_data[21]
                    self.s3_uuid = website_data[22]
                    self.project = website_data[23]
                    self.text_md = website_data[24] if website_data[24] is not None else ""

                    if self.ai_summary_needed is None:
                        self.ai_summary_needed = False

                    if reach:
                        cur.execute("SELECT id, document_type FROM public.web_documents WHERE id > %s ORDER BY id LIMIT 1", (self.id,))
                        result = cur.fetchone()
                        if result is not None:
                            self.next_id = result[0]
                            self.next_type = result[1]

                        cur.execute("SELECT id, document_type FROM public.web_documents WHERE id < %s ORDER BY id DESC LIMIT 1",
                                    (self.id,))
                        result = cur.fetchone()
                        if result is not None:
                            self.previous_id = result[0]
                            self.previous_type = result[1]

        if webpage_parse_result:
            self.text_raw = webpage_parse_result.text_raw
            self.text = webpage_parse_result.text
            self.language = webpage_parse_result.language
            self.title = webpage_parse_result.title
            self.summary = webpage_parse_result.summary

    def dict(self):
        result = {
            "id": self.id,
            "next_id": self.next_id,
            "next_type": self.next_type,
            "previous_id": self.previous_id,
            "previous_type": self.previous_type,
            "summary": self.summary,
            "url": self.url,
            "language": self.language,
            "tags": self.tags,
            "text": self.text,
            "paywall": self.paywall,
            "title": self.title,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "document_type": self.document_type.name,
            "source": self.source,
            "date_from": self.date_from,
            "original_id": self.original_id,
            "document_length": self.document_length,
            "chapter_list": self.chapter_list,
            "document_state": self.document_state.name,
            "document_state_error": self.document_state_error.name,
            "text_raw": self.text_raw,
            "transcript_job_id": self.transcript_job_id,
            "ai_summary_needed": self.ai_summary_needed,
            "author": self.author,
            "note": self.note,
            "s3_uuid": self.s3_uuid,
            "project": self.project,
            "text_md": self.text_md
        }
        return result

    def save(self) -> int | None:
        with self.db_conn:
            with self.db_conn.cursor() as cur:
                if self.id is None:
                    query = sql.SQL(
                        "INSERT INTO {} (title, summary, url, language, "
                        "tags, document_type, text, source, paywall, date_from, original_id,"
                        "document_length, document_state, document_state_error, text_raw, transcript_job_id, "
                        "ai_summary_needed, author, note, s3_uuid, project, text_md) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id"
                    ).format(sql.Identifier('web_documents'))

                    cur.execute(
                        query,
                        (self.title, self.summary, self.url, self.language,
                         self.tags, self.document_type.name, self.text,
                         self.source, self.paywall, self.date_from, self.original_id,
                         self.document_length,
                         self.document_state.name, self.document_state_error.name, self.text_raw,
                         self.transcript_job_id, self.ai_summary_needed, self.author, self.note, self.s3_uuid,
                         self.project, self.text_md)
                    )
                    self.id = cur.fetchone()[0]

                    return self.id

                else:
                    columns = [
                        ("summary", self.summary),
                        ("url", self.url),
                        ("title", self.title),
                        ("language", self.language),
                        ("tags", self.tags),
                        ("text", self.text),
                        ("document_type", self.document_type.name),
                        ("paywall", self.paywall),
                        ("source", self.source),
                        ("date_from", self.date_from),
                        ("original_id", self.original_id),
                        ("document_length", self.document_length),
                        ("document_state", self.document_state.name),
                        ("document_state_error", self.document_state_error.name),
                        ("text_raw", self.text_raw),
                        ("transcript_job_id", self.transcript_job_id),
                        ("ai_summary_needed", self.ai_summary_needed),
                        ("author", self.author),
                        ("note", self.note),
                        ("s3_uuid", self.s3_uuid),
                        ("project", self.project),
                        ("text_md", self.text_md),
                    ]
                    set_clause = ", ".join(
                        f"{column} = %s" for column, value in columns if value is not None
                    )
                    values = [value for column, value in columns if value is not None]

                    if values:
                        query = sql.SQL("UPDATE public.web_documents SET {set_clause} WHERE id = %s").format(
                            set_clause=sql.SQL(set_clause)
                        )

                    try:
                        cur.execute(query, values + [self.id])
                    except Exception as e:
                        print("Error processing sql query...")
                        print(str(e))

    def __clean_values(self):
        self.id = None
        self.next_id = None
        self.next_type = None
        self.previous_id = None
        self.previous_type = None
        self.summary = None
        self.url = None
        self.language = None
        self.tags = None
        self.text = None
        self.paywall = None
        self.title = None
        self.created_at = None
        self.document_type = None
        self.source = None
        self.date_from = None
        self.original_id = None
        self.document_length = None
        self.chapter_list = None
        self.document_state = None
        self.document_state_error = None
        self.text_raw = None
        self.transcript_job_id = None
        self.ai_summary_needed = False
        self.author = None
        self.note = None
        self.s3_uuid = None
        self.project = None
        self.text_md = None

    def delete(self) -> bool:
        with self.db_conn:
            with self.db_conn.cursor() as cur:
                cur.execute("DELETE FROM public.web_documents WHERE id = %s", (self.id,))

                self.__clean_values()
                return True

    def embedding_add(self, model: str) -> None:
        if self.document_type == StalkerDocumentType.link:
            text = self.title or ""
            if self.summary:
                text = text + " " + self.summary if text else self.summary
            text = text.strip()
            if not text:
                print(f"WARNING: document {self.id} has no title or summary, skipping embedding")
                return

            self.embedding_delete(model)
            result = get_embedding(model, text)
            self.embedding_add_simple(model, result.embedding, text)
            self.document_state = StalkerDocumentStatus.EMBEDDING_EXIST
        else:
            raise NotImplementedError(f"embedding_add not yet implemented for document type: {self.document_type}")

    def embedding_delete(self, model) -> None:
        cursor = self.db_conn.cursor()
        cursor.execute(
            "DELETE FROM public.websites_embeddings WHERE website_id = %s and model = %s", (self.id, model)
        )
        self.db_conn.commit()

    def embedding_add_simple(self, model, embedding, text) -> None:
        cursor = self.db_conn.cursor()
        cursor.execute(
            "INSERT INTO public.websites_embeddings (website_id, langauge, text, embedding, model) "
            "VALUES (%s,%s, %s, %s, %s)",
            (self.id, self.language, text, embedding, model)
        )

        self.db_conn.commit()

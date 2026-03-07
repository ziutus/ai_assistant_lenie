import json

from library.models.stalker_document_status import StalkerDocumentStatus
from library.models.stalker_document_status_error import StalkerDocumentStatusError
from library.models.stalker_document_type import StalkerDocumentType


class StalkerWebDocument:
    def __init__(self,
                 url: str | None = None,
                 wb_id: int | None = None,
                 summary: str | None = None,
                 language: str | None = None,
                 tags: str | None = None,
                 text: str | None = None,
                 paywall: bool | None = None,
                 title: str | None = None,
                 created_at=None,
                 updated_at=None,
                 document_type: StalkerDocumentType = None,
                 source: str | None = "own",
                 date_from: str | None = None, original_id: str | None = None,
                 document_length: int | None = None,
                 chapter_list: str | None = None,
                 document_state: StalkerDocumentStatus = StalkerDocumentStatus.URL_ADDED,
                 document_state_error: StalkerDocumentStatusError = StalkerDocumentStatusError.NONE,
                 text_raw: str | None = None,
                 transcript_job_id: str | None = None,
                 ai_summary_needed: bool | None = None,
                 author: str | None = None,
                 note: str | None = None,
                 s3_uuid: str | None = None,
                 project: str | None = None,
                 text_md: str | None = None,
                 transcript_needed: bool = False
                 ):

        self.id: int | None = wb_id
        self.url: str | None = url
        self.language: str | None = language
        self.tags: str | None = tags
        self.title: str | None = title
        self.summary: str | None = summary
        self.text: str | None = text
        self.source: str | None = source
        self.created_at = created_at
        self.updated_at = updated_at
        self.document_type: StalkerDocumentType = document_type

        self.paywall: bool = paywall
        self.status_code: int | None = None
        self.date_from: str | None = date_from
        self.original_id: str | None = original_id
        self.document_length: int | None = document_length
        self.chapter_list: str | None = chapter_list
        self.document_state = document_state
        self.document_state_error = document_state_error
        self.text_raw: str | None = text_raw
        self.transcript_job_id: str | None = transcript_job_id
        self.ai_summary_needed: bool | None = ai_summary_needed
        self.author: str | None = author
        self.note: str | None = note
        self.s3_uuid: str | None = s3_uuid
        self.project: str | None = project
        self.text_md: str | None = text_md
        self.transcript_needed: bool = transcript_needed

    def __str__(self):
        data = {
            "id": self.id,
            "url": self.url,
            "created_at": self.created_at,
            "summary": self.summary,
            "language": self.language,
            "tags": self.tags,
            "text": self.text,
            "paywall": self.paywall,
            "title": self.title,
            "document_type": self.document_type.name,
            "date_from": self.date_from,
            "original_id": self.original_id,
            "document_length": self.document_length,
            "document_state": self.document_state.name,
            "document_state_error": self.document_state_error.name,
            "text_raw": self.text_raw,
            "transcript_job_id": self.transcript_job_id,
            "ai_summary_needed": self.ai_summary_needed,
            "author": self.author,
            "note": self.note,
            "s3_uuid": self.s3_uuid,
            "s3_project": self.project,
            "text_md": self.text_md,
            "transcript_needed": self.transcript_needed,
        }
        result = json.dumps(data, indent=4)

        return result

    def set_document_type(self, document_type: str) -> None:
        if document_type == "movie":
            self.document_type = StalkerDocumentType.movie
        elif document_type == "youtube":
            self.document_type = StalkerDocumentType.youtube
        elif document_type == "link":
            self.document_type = StalkerDocumentType.link
        elif document_type in ["webpage", "website"]:
            self.document_type = StalkerDocumentType.webpage
        elif document_type in ["sms", "text_message"]:
            self.document_type = StalkerDocumentType.text_message
        elif document_type in ["text"]:
            self.document_type = StalkerDocumentType.text
        else:
            raise ValueError(f"document_type must be either 'movie', 'webpage', 'text_message', 'text' or 'link' not >{document_type}<")

    def set_document_state(self, document_state: str) -> None:
        if document_state in ["ERROR_DOWNLOAD", "ERROR"]:
            self.document_state = StalkerDocumentStatus.ERROR
        elif document_state == "URL_ADDED":
            self.document_state = StalkerDocumentStatus.URL_ADDED
        elif document_state == "NEED_TRANSCRIPTION":
            self.document_state = StalkerDocumentStatus.NEED_TRANSCRIPTION
        elif document_state == "TRANSCRIPTION_DONE":
            self.document_state = StalkerDocumentStatus.TRANSCRIPTION_DONE
        elif document_state == "TRANSCRIPTION_IN_PROGRESS":
            self.document_state = StalkerDocumentStatus.TRANSCRIPTION_IN_PROGRESS
        elif document_state == "NEED_MANUAL_REVIEW":
            self.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW
        elif document_state == "READY_FOR_TRANSLATION":
            self.document_state = StalkerDocumentStatus.READY_FOR_TRANSLATION
        elif document_state == "READY_FOR_EMBEDDING":
            self.document_state = StalkerDocumentStatus.READY_FOR_EMBEDDING
        elif document_state == "EMBEDDING_EXIST":
            self.document_state = StalkerDocumentStatus.EMBEDDING_EXIST
        elif document_state == "DOCUMENT_INTO_DATABASE":
            self.document_state = StalkerDocumentStatus.DOCUMENT_INTO_DATABASE
        elif document_state == "NEED_CLEAN_TEXT":
            self.document_state = StalkerDocumentStatus.NEED_CLEAN_TEXT
        elif document_state == "NEED_CLEAN_MD":
            self.document_state = StalkerDocumentStatus.NEED_CLEAN_MD
        elif document_state == "TEXT_TO_MD_DONE":
            self.document_state = StalkerDocumentStatus.NEED_CLEAN_MD
        elif document_state == "MD_SIMPLIFIED":
            self.document_state = StalkerDocumentStatus.MD_SIMPLIFIED
        else:
            raise ValueError("document_state must be one of the valid StalkerDocumentStatus values")

    def set_document_state_error(self, document_state_error: str) -> None:

        if document_state_error is None or document_state_error == "NONE":
            self.document_state_error = StalkerDocumentStatusError.NONE
        elif document_state_error == "ERROR_DOWNLOAD":
            self.document_state_error = StalkerDocumentStatusError.ERROR_DOWNLOAD
        elif document_state_error == "LINK_SUMMARY_MISSING":
            self.document_state_error = StalkerDocumentStatusError.LINK_SUMMARY_MISSING
        elif document_state_error == "TITLE_MISSING":
            self.document_state_error = StalkerDocumentStatusError.TITLE_MISSING
        elif document_state_error == "TEXT_MISSING":
            self.document_state_error = StalkerDocumentStatusError.TEXT_MISSING
        elif document_state_error == "TEXT_TRANSLATION_ERROR":
            self.document_state_error = StalkerDocumentStatusError.TEXT_TRANSLATION_ERROR
        elif document_state_error == "TITLE_TRANSLATION_ERROR":
            self.document_state_error = StalkerDocumentStatusError.TITLE_TRANSLATION_ERROR
        elif document_state_error == "SUMMARY_TRANSLATION_ERROR":
            self.document_state_error = StalkerDocumentStatusError.SUMMARY_TRANSLATION_ERROR
        elif document_state_error == "NO_URL_ERROR":
            self.document_state_error = StalkerDocumentStatusError.NO_URL_ERROR
        elif document_state_error == "EMBEDDING_ERROR":
            self.document_state_error = StalkerDocumentStatusError.EMBEDDING_ERROR
        elif document_state_error == "MISSING_TRANSLATION":
            self.document_state_error = StalkerDocumentStatusError.MISSING_TRANSLATION
        elif document_state_error == "TRANSLATION_ERROR":
            self.document_state_error = StalkerDocumentStatusError.TRANSLATION_ERROR
        elif document_state_error == "REGEX_ERROR":
            self.document_state_error = StalkerDocumentStatusError.REGEX_ERROR
        elif document_state_error == "TEXT_TO_MD_ERROR":
            self.document_state_error = StalkerDocumentStatusError.TEXT_TO_MD_ERROR

        else:
            raise ValueError(
                f"document_state_error must be one of the valid StalkerDocumentStatusError values, not >{document_state_error}<")

    def analyze(self) -> None:
        if self.document_state == StalkerDocumentStatus.EMBEDDING_EXIST:
            return None

        if not self.text_raw:
            print("This is adding new entry, so raw text is equal to text")
            self.text_raw = self.text

        # if self.title and not self.language:
        #     print("Checking language for title", end="")
        #     self.language = text_language_detect(text=self.title)
        #     print("[DONE]")
        #
        # if self.summary and not self.language:
        #     print("Checking language for summary", end="")
        #     self.language = text_language_detect(text=self.summary)
        #     print("[DONE]")
        #
        # if self.text and not self.language:
        #     print("Checking language for text", end="")
        #     self.language = text_language_detect(text=self.text)
        #     print("[DONE]")
        #
        if self.document_type == StalkerDocumentType.link:
            self.text = None

    def validate(self) -> None:
        self.document_state_error = StalkerDocumentStatusError.NONE

        if self.document_state == StalkerDocumentStatus.EMBEDDING_EXIST:
            return None

        if not self.title or len(self.title) < 3:
            self.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW
            self.document_state_error = StalkerDocumentStatusError.TITLE_MISSING

        if self.document_type == StalkerDocumentType.link:
            if not self.summary or len(self.summary) < 3:
                self.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW
                self.document_state_error = StalkerDocumentStatusError.LINK_SUMMARY_MISSING

        if self.document_type == StalkerDocumentType.webpage:
            if not self.text or len(self.text) < 3:
                self.document_state = StalkerDocumentStatus.NEED_MANUAL_REVIEW
                self.document_state_error = StalkerDocumentStatusError.TEXT_MISSING


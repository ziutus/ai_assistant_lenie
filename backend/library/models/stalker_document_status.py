from enum import Enum


# Source of truth for valid document processing states. DB lookup table `document_status_types`
# is seeded from these values and enforces them via FK constraint on `web_documents.document_state`.
# Kept alongside FK for: early validation in setter methods, input aliases ("ERROR_DOWNLOAD"→"ERROR"),
# IDE autocomplete. See ADR-010 for rationale.
class StalkerDocumentStatus(Enum):
    ERROR = 1
    URL_ADDED = 2
    NEED_TRANSCRIPTION = 3
    TRANSCRIPTION_IN_PROGRESS = 4
    TRANSCRIPTION_DONE = 5
    TRANSCRIPTION_DONE_AND_SPLIT_BY_CHAPTERS = 6
    NEED_MANUAL_REVIEW = 7  # regexp + LLM extraction failed to produce clean article text — needs manual review
    READY_FOR_TRANSLATION = 8  # deprecated — kept for DB compatibility
    READY_FOR_EMBEDDING = 9
    EMBEDDING_EXIST = 10
    DOCUMENT_INTO_DATABASE = 11
    NEED_CLEAN_TEXT = 12
    NEED_CLEAN_MD = 13
    TEXT_TO_MD_DONE = 14
    MD_SIMPLIFIED = 15
    TEMPORARY_ERROR = 16


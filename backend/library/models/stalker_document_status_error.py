from enum import Enum


# Source of truth for valid document error states. DB lookup table `document_status_error_types`
# is seeded from these values and enforces them via FK constraint on `web_documents.document_state_error`.
# Kept alongside FK for: early validation in setter methods, IDE autocomplete. See ADR-010.
class StalkerDocumentStatusError(Enum):
    NONE = 1
    ERROR_DOWNLOAD = 2
    LINK_SUMMARY_MISSING = 3
    TITLE_MISSING = 4
    TITLE_TRANSLATION_ERROR = 5
    TEXT_MISSING = 6
    TEXT_TRANSLATION_ERROR = 7
    SUMMARY_TRANSLATION_ERROR = 8
    NO_URL_ERROR = 9
    EMBEDDING_ERROR = 10
    MISSING_TRANSLATION = 11
    TRANSLATION_ERROR = 12
    REGEX_ERROR = 13
    TEXT_TO_MD_ERROR = 14
    NO_CAPTIONS_AVAILABLE = 15
    CAPTIONS_LANGUAGE_MISMATCH = 16
    CAPTIONS_FETCH_ERROR = 17
    TRANSCRIPTION_ERROR = 18
    TRANSCRIPTION_INSUFFICIENT_FUNDS = 19


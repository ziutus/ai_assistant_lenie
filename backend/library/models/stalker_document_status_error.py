# This errors status are also defined in Postgresql table: document_status_error_types
from enum import Enum

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


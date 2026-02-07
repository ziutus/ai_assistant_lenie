from enum import Enum

# Those errors status are also defined in Postgresql table: document_status_types

class StalkerDocumentStatus(Enum):
    ERROR = 1
    URL_ADDED = 2
    NEED_TRANSCRIPTION = 3
    TRANSCRIPTION_IN_PROGRESS = 4
    TRANSCRIPTION_DONE = 5
    TRANSCRIPTION_DONE_AND_SPLIT_BY_CHAPTERS = 6
    NEED_MANUAL_REVIEW = 7
    READY_FOR_TRANSLATION = 8
    READY_FOR_EMBEDDING = 9
    EMBEDDING_EXIST = 10
    DOCUMENT_INTO_DATABASE = 11
    NEED_CLEAN_TEXT = 12
    NEED_CLEAN_MD = 13
    TEXT_TO_MD_DONE = 14
    MD_SIMPLIFIED = 15


from enum import Enum

# Those document types are also defined in Postgresql table: document_types
class StalkerDocumentType(Enum):
    movie = 1
    youtube = 2
    link = 3
    webpage = 4
    text_message = 5
    text = 6


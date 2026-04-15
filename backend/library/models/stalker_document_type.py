from enum import Enum


# Source of truth for valid document types. DB lookup table `document_types` is seeded from
# these values and enforces them via FK constraint on `web_documents.document_type`.
# Kept alongside FK for: early validation in setter methods, input aliases ("website"→"webpage",
# "sms"→"text_message"), IDE autocomplete. See ADR-010 for rationale.
class StalkerDocumentType(Enum):
    movie = 1
    youtube = 2
    link = 3
    webpage = 4
    text_message = 5
    text = 6
    email = 7
    social_media_post = 8


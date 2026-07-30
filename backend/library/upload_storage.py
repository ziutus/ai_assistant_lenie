"""Durable staging area for files uploaded through the Lenie UI.

Objects are intentionally kept separate from document source/artifact keys:
``uploads/<year>/<month>/<uuid>-<filename>``.  Importers can consume a key
from this area without needing the file to exist on their local filesystem.
"""

from __future__ import annotations

import mimetypes
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from werkzeug.utils import secure_filename

from library.storage import ObjectStorage

UPLOAD_PREFIX = "uploads"
ALLOWED_EXTENSIONS = frozenset({".pdf", ".epub", ".mobi"})


@dataclass(frozen=True)
class UploadedFile:
    key: str
    filename: str
    size: int
    extension: str


def validate_upload_filename(filename: str) -> tuple[str, str]:
    """Return a safe display filename and extension, or reject unsupported files."""
    safe_name = secure_filename(filename or "")
    if not safe_name:
        raise ValueError("filename is required")
    extension = Path(safe_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        formats = ", ".join(sorted(ext.removeprefix(".").upper() for ext in ALLOWED_EXTENSIONS))
        raise ValueError(f"unsupported file type; allowed: {formats}")
    return safe_name, extension


def store_uploaded_file(storage: ObjectStorage, filename: str, data: bytes) -> UploadedFile:
    safe_name, extension = validate_upload_filename(filename)
    if not data:
        raise ValueError("file is empty")
    now = datetime.now(UTC)
    key = f"{UPLOAD_PREFIX}/{now:%Y}/{now:%m}/{uuid.uuid4().hex}-{safe_name}"
    content_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    storage.put_bytes(key, data, content_type=content_type)
    return UploadedFile(key=key, filename=safe_name, size=len(data), extension=extension)


def get_uploaded_file(storage: ObjectStorage, key: str) -> bytes:
    """Read an upload key while preventing import scripts from reading arbitrary objects."""
    normalized = key.replace("\\", "/").lstrip("/")
    if not normalized.startswith(f"{UPLOAD_PREFIX}/"):
        raise ValueError(f"upload storage key must start with {UPLOAD_PREFIX!r}")
    if Path(normalized).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError("upload storage key has an unsupported file type")
    return storage.get_bytes(normalized)

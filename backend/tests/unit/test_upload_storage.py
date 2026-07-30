from unittest.mock import MagicMock

import pytest

from library.storage import StoredObject
from library.upload_storage import get_uploaded_file, list_uploaded_files, store_uploaded_file, validate_upload_filename


def test_store_uploaded_file_uses_dedicated_prefix_and_safe_filename():
    storage = MagicMock()

    result = store_uploaded_file(storage, "M\u00f3j katalog.pdf", b"%PDF-test")

    assert result.key.startswith("uploads/")
    assert result.key.endswith("-Moj_katalog.pdf")
    assert result.extension == ".pdf"
    storage.put_bytes.assert_called_once()


@pytest.mark.parametrize("filename", ["book.txt", "", "book.pdf.exe"])
def test_validate_upload_filename_rejects_unsupported_type(filename):
    with pytest.raises(ValueError):
        validate_upload_filename(filename)


def test_get_uploaded_file_only_reads_upload_area():
    storage = MagicMock()
    storage.get_bytes.return_value = b"pdf"

    assert get_uploaded_file(storage, "uploads/2026/07/book.pdf") == b"pdf"
    storage.get_bytes.assert_called_once_with("uploads/2026/07/book.pdf")
    with pytest.raises(ValueError):
        get_uploaded_file(storage, "documents/1/source.pdf")


def test_list_uploaded_files_returns_only_supported_uploads_in_reverse_key_order():
    storage = MagicMock()
    storage.iter_objects.return_value = [
        StoredObject("uploads/2026/07/a-old.pdf", 10),
        StoredObject("uploads/2026/07/z-new.epub", 20),
        StoredObject("uploads/2026/07/readme.txt", 2),
    ]

    result = list_uploaded_files(storage)

    assert [(item.key, item.filename, item.size) for item in result] == [
        ("uploads/2026/07/z-new.epub", "new.epub", 20),
        ("uploads/2026/07/a-old.pdf", "old.pdf", 10),
    ]
    storage.iter_objects.assert_called_once_with("uploads/")

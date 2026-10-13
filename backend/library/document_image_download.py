"""Download a web article's external images into object storage (MinIO on the NAS).

A document_images row of a webpage starts life as a bare external URL
(library/article_cleaner.py). The original CDN can drop or block the file at any
time, so the user can copy it into our own storage: the row then keeps both its
original ``url`` (identity, re-clean matching) and the new ``storage_key``
(what the editor/reader serve, via a presigned link).
"""

import ipaddress
import logging
import mimetypes
import socket
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import requests
from sqlalchemy import select

from library.db.models import DocumentImage

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 15 * 1024 * 1024
REQUEST_TIMEOUT = (5, 20)  # connect, read
MAX_REDIRECTS = 3
MAX_IMAGES_PER_CALL = 60
FETCH_WORKERS = 4
USER_AGENT = "Mozilla/5.0 (compatible; LenieImageFetcher/1.0)"

_EXT_BY_TYPE = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/avif": "avif",
    "image/svg+xml": "svg",
    "image/bmp": "bmp",
}


class ImageDownloadError(Exception):
    """A single image could not be fetched; the message is shown to the user."""


def _assert_public_http_url(url: str) -> None:
    """Refuse non-http(s) schemes and hosts resolving to internal addresses (SSRF guard)."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ImageDownloadError("Adres obrazka nie jest adresem http(s).")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ImageDownloadError("Nie udało się rozwiązać nazwy hosta.") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (address.is_private or address.is_loopback or address.is_link_local
                or address.is_reserved or address.is_multicast or address.is_unspecified):
            raise ImageDownloadError("Adres obrazka wskazuje na sieć wewnętrzną.")


def fetch_image(url: str) -> tuple[bytes, str]:
    """Fetch one image, returning (bytes, content_type). Raises ImageDownloadError."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        _assert_public_http_url(current)
        try:
            response = requests.get(
                current, headers={"User-Agent": USER_AGENT, "Accept": "image/*,*/*;q=0.5"},
                timeout=REQUEST_TIMEOUT, stream=True, allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise ImageDownloadError(f"Błąd połączenia: {type(exc).__name__}") from exc
        with response:
            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get("Location")
                if not location:
                    raise ImageDownloadError("Przekierowanie bez adresu docelowego.")
                current = urljoin(current, location)
                continue
            if response.status_code != 200:
                raise ImageDownloadError(f"Serwer odpowiedział kodem {response.status_code}.")
            content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if not content_type.startswith("image/"):
                guessed = mimetypes.guess_type(urlparse(current).path)[0] or ""
                if not guessed.startswith("image/"):
                    raise ImageDownloadError("Adres nie zwraca obrazka.")
                content_type = guessed
            declared = response.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > MAX_IMAGE_BYTES:
                raise ImageDownloadError("Obrazek jest większy niż 15 MB.")
            data = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                data.extend(chunk)
                if len(data) > MAX_IMAGE_BYTES:
                    raise ImageDownloadError("Obrazek jest większy niż 15 MB.")
            if not data:
                raise ImageDownloadError("Pusta odpowiedź.")
            return bytes(data), content_type
    raise ImageDownloadError("Zbyt wiele przekierowań.")


def storage_key_for(document_id: int, image_id: int, content_type: str) -> str:
    ext = _EXT_BY_TYPE.get(content_type) or mimetypes.guess_extension(content_type) or ".img"
    return f"documents/{document_id}/web_images/{image_id}.{ext.lstrip('.')}"


def download_document_images(
    session, storage, document_id: int, image_ids: list[int] | None = None, fetcher=fetch_image,
) -> list[dict]:
    """Copy url-sourced document_images of document_id into storage.

    image_ids=None means every image of the document that has no stored copy
    yet. Network fetches run in a small thread pool; storage writes and row
    updates stay sequential on the caller's session. Commits once at the end;
    one image failing never aborts the rest.

    Returns one dict per requested image: {id, status, message?} with status
    "stored" | "already_stored" | "error".
    """
    query = select(DocumentImage).where(
        DocumentImage.document_id == document_id, DocumentImage.url.is_not(None),
    ).order_by(DocumentImage.id)
    if image_ids is not None:
        query = query.where(DocumentImage.id.in_(image_ids))
    rows = list(session.execute(query).scalars())
    if len(rows) > MAX_IMAGES_PER_CALL:
        rows = rows[:MAX_IMAGES_PER_CALL]

    results: list[dict] = []
    to_fetch = []
    for row in rows:
        if row.storage_key:
            results.append({"id": row.id, "status": "already_stored"})
        else:
            to_fetch.append(row)

    def _fetch(row):
        try:
            return row, fetcher(row.url), None
        except ImageDownloadError as exc:
            return row, None, str(exc)
        except Exception:  # noqa: BLE001 — never let one image break the batch
            logger.warning("Unexpected error fetching image %s", row.id, exc_info=True)
            return row, None, "Nieoczekiwany błąd pobierania."

    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        fetched = list(pool.map(_fetch, to_fetch))

    for row, payload, error in fetched:
        if error:
            results.append({"id": row.id, "status": "error", "message": error})
            continue
        data, content_type = payload
        key = storage_key_for(document_id, row.id, content_type)
        try:
            storage.put_bytes(key, data, content_type)
        except Exception:  # noqa: BLE001
            logger.warning("Could not store image %s", row.id, exc_info=True)
            results.append({"id": row.id, "status": "error", "message": "Nie udało się zapisać w storage."})
            continue
        row.storage_key = key
        results.append({"id": row.id, "status": "stored"})

    session.commit()
    return results

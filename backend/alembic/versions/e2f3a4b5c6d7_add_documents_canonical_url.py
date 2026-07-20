"""Add canonical URL identity to documents.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
"""
from collections import defaultdict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from alembic import op
import sqlalchemy as sa

revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None

_EXACT = {"_ga", "_gl", "dclid", "fbclid", "gclid", "gbraid", "igshid", "msclkid", "twclid", "wbraid"}
_PREFIXES = ("utm_", "mc_", "ss_", "vero_")


def _canonicalize(url: str) -> str:
    value = (url or "").strip()
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value.split("#", 1)[0]
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower().rstrip(".")
    try:
        hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError:
        pass
    host = f"[{hostname}]" if ":" in hostname else hostname
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port is not None and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    if parsed.username:
        credentials = parsed.username + (f":{parsed.password}" if parsed.password else "")
        host = f"{credentials}@{host}"
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    items = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if k.lower() not in _EXACT and not k.lower().startswith(_PREFIXES)]
    if hostname in {"youtu.be", "www.youtu.be"}:
        video_id = path.strip("/").split("/", 1)[0]
        if video_id:
            host, path, items = "www.youtube.com", "/watch", [("v", video_id)]
    elif hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"} and path == "/watch":
        ids = [v for k, v in items if k == "v"]
        if ids:
            host, items = "www.youtube.com", [("v", ids[0])]
    return urlunsplit((scheme, host, path, urlencode(sorted(items), doseq=True), ""))


def upgrade():
    op.add_column("documents", sa.Column("canonical_url", sa.Text(), nullable=True))
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, url FROM documents ORDER BY id")).fetchall()
    collisions = defaultdict(list)
    for document_id, url in rows:
        canonical = _canonicalize(url)
        connection.execute(
            sa.text("UPDATE documents SET canonical_url = :canonical WHERE id = :id"),
            {"canonical": canonical, "id": document_id},
        )
        collisions[canonical].append(document_id)
    for canonical, ids in collisions.items():
        if len(ids) > 1:
            print(f"CANONICAL URL COLLISION: {canonical} -> document IDs {ids}")
    op.alter_column("documents", "canonical_url", nullable=False)
    op.create_index("idx_documents_canonical_url", "documents", ["canonical_url"])


def downgrade():
    op.drop_index("idx_documents_canonical_url", table_name="documents")
    op.drop_column("documents", "canonical_url")

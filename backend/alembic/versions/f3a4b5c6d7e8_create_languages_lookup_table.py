"""Create languages lookup table, normalize documents.language.

documents.language accumulated 15 distinct raw values across 9210 rows on
NAS (2026-07-20): case/region variants of the same language
(pl/pl-PL/pl-pl, en/en-US/en-us), 829 empty-string rows and 28 NULL rows.
This migration folds every value to a bare lowercase code (the part before
a '-', if any) and treats an empty string the same as NULL — a document
either has a known language or it doesn't. Folding is lossy by design:
'pl-PL' and 'pl' become indistinguishable ('pl'), which is the point.

documents.language stays a free TEXT column, NOT an FK to languages.id:
language detection (library/text_detect_language.py) and every import path
that writes it (email_import.py, dynamodb_sync.py, imports/*) keep working
unchanged, and a language nobody has catalogued yet still writes fine.
`languages` is a curated "known good" reference list backing the /search
languages filter picker (GET /languages), not a hard constraint — the
backend's SearchFilters.languages validation (library/search/types.py)
stays a permissive 2-3 letter regex, unchanged by this migration.

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
"""
from alembic import op
import sqlalchemy as sa

revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None

# Names for languages actually observed in production on 2026-07-20. A code
# that shows up later without an entry here just falls back to itself as
# the display name (see the INSERT below) rather than blocking the
# migration — there is no need to pre-populate hypothetical languages.
_KNOWN_NAMES_PL = {
    "pl": "polski", "en": "angielski", "de": "niemiecki", "es": "hiszpański",
    "it": "włoski", "nl": "niderlandzki", "sk": "słowacki", "lt": "litewski",
    "gd": "szkocki gaelicki",
}


def _normalize_language(value: str | None) -> str | None:
    value = (value or "").strip().lower()
    return value.split("-", 1)[0] or None


def upgrade():
    op.execute("""
        CREATE TABLE languages (
            id SERIAL PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            name_pl TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, language FROM documents ORDER BY id")).fetchall()
    seen_codes = set()
    for document_id, raw in rows:
        code = _normalize_language(raw)
        if code != raw:
            connection.execute(
                sa.text("UPDATE documents SET language = :code WHERE id = :id"),
                {"code": code, "id": document_id},
            )
        if code:
            seen_codes.add(code)

    for code in sorted(seen_codes):
        connection.execute(
            sa.text("INSERT INTO languages (code, name_pl) VALUES (:code, :name)"),
            {"code": code, "name": _KNOWN_NAMES_PL.get(code, code)},
        )


def downgrade():
    op.execute("DROP TABLE languages")

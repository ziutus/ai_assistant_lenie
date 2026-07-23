"""create organizations, organization_aliases, document_organizations

Global organization registry (docs/organization-ner-alias-plan.md):
a one-off manual merge of two orgName spellings (e.g. "Interia"/"Interii")
must apply globally — in the current document, in already-saved documents,
and on future NER runs. Schema + safe seed only; existing document_entities
are backfilled separately via backend/imports/backfill_organizations.py
(--dry-run by default).

Also adds information_sources.organization_id (nullable, unique) so a
source that IS an organization mentioned via NER resolves through the same
registry instead of maintaining an independent alias set (see the "Ustalenia
z review" section of the plan doc). Bloomberg/KCNA are seeded here as
organizations, replacing the hardcoded KNOWN_ORGANIZATION_SOURCES name
mapping in library/information_provenance.py.

Revision ID: e23a1b2c3d4e
Revises: e22d8e0f6b1c
"""
from alembic import op
import sqlalchemy as sa

revision = "e23a1b2c3d4e"
down_revision = "e22d8e0f6b1c"
branch_labels = None
depends_on = None

# (canonical_name, organization_type, [(alias, alias_kind), ...])
_SEED_ORGANIZATIONS = [
    ("Interia", "media", [
        ("Interia", "manual"),
        ("Interii", "inflection"),
        ("Interią", "inflection"),
        ("Interię", "inflection"),
    ]),
    ("Bloomberg", "agency", [("Bloomberg", "manual")]),
    ("KCNA", "agency", [("KCNA", "manual")]),
]


def _normalize(value: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFC", value).strip().casefold()


def upgrade():
    op.execute("""
        CREATE TABLE organizations (
            id SERIAL PRIMARY KEY,
            uuid VARCHAR(100) NOT NULL DEFAULT gen_random_uuid() UNIQUE,
            canonical_name TEXT NOT NULL,
            organization_type VARCHAR(30),
            description TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE organization_aliases (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            alias TEXT NOT NULL,
            normalized_alias TEXT NOT NULL,
            alias_kind VARCHAR(20) NOT NULL DEFAULT 'ner_observed',
            created_by VARCHAR(20) NOT NULL DEFAULT 'ner',
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (normalized_alias)
        )
    """)
    op.execute("""
        CREATE TABLE document_organizations (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            document_entity_id INTEGER REFERENCES document_entities(id) ON DELETE SET NULL,
            confidence VARCHAR(20) NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (document_id, organization_id)
        )
    """)
    op.execute("CREATE INDEX idx_document_organizations_document ON document_organizations (document_id)")
    op.execute("CREATE INDEX idx_document_organizations_organization ON document_organizations (organization_id)")

    op.execute(
        "ALTER TABLE information_sources ADD COLUMN organization_id INTEGER UNIQUE "
        "REFERENCES organizations(id) ON DELETE SET NULL"
    )

    connection = op.get_bind()
    for canonical_name, organization_type, aliases in _SEED_ORGANIZATIONS:
        org_id = connection.execute(
            sa.text(
                "INSERT INTO organizations (canonical_name, organization_type) "
                "VALUES (:name, :type) RETURNING id"
            ),
            {"name": canonical_name, "type": organization_type},
        ).scalar_one()
        for alias, alias_kind in aliases:
            connection.execute(
                sa.text(
                    "INSERT INTO organization_aliases "
                    "(organization_id, alias, normalized_alias, alias_kind, created_by) "
                    "VALUES (:org_id, :alias, :normalized, :kind, 'migration')"
                ),
                {"org_id": org_id, "alias": alias, "normalized": _normalize(alias), "kind": alias_kind},
            )


def downgrade():
    op.execute("ALTER TABLE information_sources DROP COLUMN organization_id")
    op.execute("DROP TABLE IF EXISTS document_organizations")
    op.execute("DROP TABLE IF EXISTS organization_aliases")
    op.execute("DROP TABLE IF EXISTS organizations")

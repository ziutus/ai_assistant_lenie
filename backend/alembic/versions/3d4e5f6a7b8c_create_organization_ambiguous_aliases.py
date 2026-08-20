"""Create context-dependent organization abbreviation candidates.

``organization_aliases`` remains globally unique and is only for aliases
that can always resolve to one organization. This table stores alternatives
for abbreviations such as SAF, which require document context or a human/LLM
decision.

Revision ID: 3d4e5f6a7b8c
Revises: f35c4d5e6a7b
"""

from alembic import op
import sqlalchemy as sa


revision = "3d4e5f6a7b8c"
down_revision = "f35c4d5e6a7b"
branch_labels = None
depends_on = None


def _normalize(value: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFC", value).strip().casefold()


def _find_or_create_organization(connection, *, name: str, organization_type: str, description: str) -> int:
    existing = connection.execute(
        sa.text("SELECT id FROM organizations WHERE canonical_name = :name ORDER BY id LIMIT 1"),
        {"name": name},
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    return connection.execute(
        sa.text(
            "INSERT INTO organizations (canonical_name, organization_type, description) "
            "VALUES (:name, :type, :description) RETURNING id"
        ),
        {"name": name, "type": organization_type, "description": description},
    ).scalar_one()


def upgrade() -> None:
    op.create_table(
        "organization_ambiguous_aliases",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.Text, nullable=False),
        sa.Column("normalized_alias", sa.Text, nullable=False),
        sa.Column("context_hint", sa.Text),
        sa.Column("language", sa.String(10)),
        sa.Column("status", sa.String(20), nullable=False, server_default="approved"),
        sa.Column("created_by", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "normalized_alias"),
    )
    op.create_index(
        "idx_organization_ambiguous_aliases_normalized",
        "organization_ambiguous_aliases",
        ["normalized_alias"],
    )

    connection = op.get_bind()
    sudan_id = _find_or_create_organization(
        connection,
        name="Siły Zbrojne Sudanu",
        organization_type="military",
        description="Państwowe siły zbrojne Sudanu (Sudanese Armed Forces).",
    )
    credit_id = _find_or_create_organization(
        connection,
        name="SAF",
        organization_type="company",
        description="SAF to organizacja zajmująca się zarządzaniem ryzykiem kredytowym i ubezpieczeniami kredytów kupieckich.",
    )
    for organization_id, context_hint in (
        (sudan_id, "Sudan; wojsko, wojna domowa, Chartum, RSF; pełna forma: Siły Zbrojne Sudanu."),
        (credit_id, "Zarządzanie ryzykiem kredytowym i ubezpieczenia kredytów kupieckich."),
    ):
        connection.execute(
            sa.text(
                "INSERT INTO organization_ambiguous_aliases "
                "(organization_id, alias, normalized_alias, context_hint, language, status, created_by) "
                "VALUES (:organization_id, :alias, :normalized_alias, :context_hint, 'pl', 'approved', 'migration') "
                "ON CONFLICT (organization_id, normalized_alias) DO NOTHING"
            ),
            {
                "organization_id": organization_id,
                "alias": "SAF",
                "normalized_alias": _normalize("SAF"),
                "context_hint": context_hint,
            },
        )


def downgrade() -> None:
    op.drop_index("idx_organization_ambiguous_aliases_normalized", table_name="organization_ambiguous_aliases")
    op.drop_table("organization_ambiguous_aliases")

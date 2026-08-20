"""Seed the two verified meanings of the ambiguous RSF abbreviation.

Revision ID: 4e5f6a7b8c9d
Revises: 3d4e5f6a7b8c
"""

from alembic import op
import sqlalchemy as sa


revision = "4e5f6a7b8c9d"
down_revision = "3d4e5f6a7b8c"
branch_labels = None
depends_on = None


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
    connection = op.get_bind()
    sudan_id = _find_or_create_organization(
        connection,
        name="Siły Szybkiego Wsparcia",
        organization_type="military",
        description="Sudańskie paramilitarne Siły Szybkiego Wsparcia (Rapid Support Forces).",
    )
    reporters_id = _find_or_create_organization(
        connection,
        name="Reporterzy bez Granic",
        organization_type="ngo",
        description="Międzynarodowa organizacja pozarządowa chroniąca wolność prasy i prawa dziennikarzy.",
    )
    for organization_id, context_hint in (
        (sudan_id, "Sudan; wojna domowa, Darfur, Chartum; pełna forma: Siły Szybkiego Wsparcia."),
        (reporters_id, "Wolność prasy, dziennikarze, media; Reporterzy bez Granic."),
    ):
        connection.execute(
            sa.text(
                "INSERT INTO organization_ambiguous_aliases "
                "(organization_id, alias, normalized_alias, context_hint, language, status, created_by) "
                "VALUES (:organization_id, 'RSF', 'rsf', :context_hint, 'pl', 'approved', 'migration') "
                "ON CONFLICT (organization_id, normalized_alias) DO NOTHING"
            ),
            {"organization_id": organization_id, "context_hint": context_hint},
        )


def downgrade() -> None:
    op.execute("DELETE FROM organization_ambiguous_aliases WHERE normalized_alias = 'rsf'")

"""seed africa corps ambiguous aliases

"Africa Corps" is the modern Russian paramilitary formation's own English
name, but it is also a plausible English rendering of the WWII German
"Afrika Korps" — a genuine full-name collision, not just a spelling variant
(see docs/organization-ner-alias-plan.md). Registers 'africa corps' as an
ambiguous alias of both organizations so entity_service's context-LLM step
(select_ambiguous_alias_candidate_with_llm) can pick the right one from
document context instead of always falling through to the deterministic
canonical_name match (which would silently prefer the Russian formation).

Revision ID: fa12f5be1ae2
Revises: 05f58c775df5
Create Date: 2026-08-22 08:22:52.521813

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fa12f5be1ae2'
down_revision: Union[str, Sequence[str], None] = '05f58c775df5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
    """Upgrade schema."""
    connection = op.get_bind()
    russia_id = _find_or_create_organization(
        connection,
        name="Africa Corps",
        organization_type="formacja paramilitarna",
        description=(
            "Rosyjska formacja paramilitarna podległa rosyjskiemu MON, faktyczny następca "
            "Grupy Wagnera działający w Afryce od 2023 roku."
        ),
    )
    wwii_id = _find_or_create_organization(
        connection,
        name="Afrika Korps",
        organization_type="jednostka wojskowa (hist.)",
        description=(
            "Niemiecki korpus ekspedycyjny w Afryce Północnej podczas II wojny światowej "
            "(marzec 1941 – maj 1943), dowodzony początkowo przez feldmarszałka Erwina Rommla."
        ),
    )
    for organization_id, context_hint in (
        (russia_id, "Rosja, MON, Grupa Wagnera, 2023+, Sahel, Mali, Burkina Faso, CAR, Niger."),
        (wwii_id, "II wojna światowa, Rommel, Tobruk, El Alamein, 1941-1943, Afrika Korps."),
    ):
        connection.execute(
            sa.text(
                "INSERT INTO organization_ambiguous_aliases "
                "(organization_id, alias, normalized_alias, context_hint, language, status, created_by) "
                "VALUES (:organization_id, 'Africa Corps', 'africa corps', :context_hint, 'pl', 'approved', 'migration') "
                "ON CONFLICT (organization_id, normalized_alias) DO NOTHING"
            ),
            {"organization_id": organization_id, "context_hint": context_hint},
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM organization_ambiguous_aliases WHERE normalized_alias = 'africa corps'")

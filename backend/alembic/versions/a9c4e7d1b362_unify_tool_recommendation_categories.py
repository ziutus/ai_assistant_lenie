"""Fold duplicate spellings of radar categories (security/Security, decision-models/DecisionModels, ...)."""

from alembic import op

revision = "a9c4e7d1b362"
down_revision = "d4a7c1e9b6f2"
branch_labels = None
depends_on = None

# Old spelling -> canonical spelling; the same folding the writers apply (library/tool_categories.py).
RENAMES = {
    "security": "Security",
    "decision-models": "DecisionModels",
    "cloud": "Cloud",
    "database": "Database",
    "scraping": "Scraping",
    "workflow": "Workflow",
    "frontend-tooling": "FrontendTooling",
    "python-tooling": "PythonTooling",
    "infrastructure-as-code": "InfrastructureAsCode",
    "infrastructure": "InfraManagement",
    "notes": "Notatki i produktywność",
}


def upgrade() -> None:
    for old, new in RENAMES.items():
        op.execute(f"UPDATE tool_recommendations SET category = '{new}' WHERE category = '{old}'")


def downgrade() -> None:
    # The original spellings are not recoverable once merged; nothing to restore.
    pass

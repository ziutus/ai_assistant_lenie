"""Add contact interests and education."""
from alembic import op

revision = "63f91b7e2a84"
down_revision = "92de6b7a108c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE contact_interests (
            id          SERIAL PRIMARY KEY,
            name        VARCHAR(100) UNIQUE NOT NULL,
            description TEXT,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE contact_interest_memberships (
            contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            interest_id   INTEGER NOT NULL REFERENCES contact_interests(id) ON DELETE RESTRICT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (contact_id, interest_id)
        )
        """
    )
    op.execute("CREATE INDEX idx_contact_interest_memberships_interest_id ON contact_interest_memberships (interest_id)")

    op.execute("""
        CREATE TABLE contact_education (
            id SERIAL PRIMARY KEY,
            contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            institution VARCHAR(255) NOT NULL,
            field_of_study VARCHAR(255),
            degree VARCHAR(20),
            start_date DATE,
            end_date DATE,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_contact_education_degree CHECK
                (degree IN ('bachelor', 'engineer', 'master', 'doctor', 'other')),
            CONSTRAINT ck_contact_education_dates CHECK (end_date >= start_date)
        )
    """)
    op.execute("CREATE INDEX idx_contact_education_contact ON contact_education (contact_id)")


def downgrade() -> None:
    op.execute("DROP TABLE contact_education")
    op.execute("DROP TABLE IF EXISTS contact_interest_memberships")
    op.execute("DROP TABLE IF EXISTS contact_interests")

"""Multiple phone numbers and email addresses, retaining primary legacy fields."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d8f2c4a6b901"
down_revision = "a4acf996046e"
branch_labels = None
depends_on = None


def upgrade():
    for field, legacy in (("phone_numbers", "phone_number"), ("email_addresses", "email")):
        op.add_column("contacts", sa.Column(field, postgresql.JSONB(), nullable=False,
                                           server_default=sa.text("'[]'::jsonb")))
        op.execute(sa.text(f"""
            UPDATE contacts
            SET {field} = jsonb_build_array(jsonb_build_object('value', {legacy}, 'label', NULL))
            WHERE {legacy} IS NOT NULL AND btrim({legacy}) <> ''
        """))


def downgrade():
    # Primary values remain in the legacy columns; export additional values before downgrade.
    op.drop_column("contacts", "email_addresses")
    op.drop_column("contacts", "phone_numbers")

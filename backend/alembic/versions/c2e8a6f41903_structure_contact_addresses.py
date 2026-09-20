"""Split shared contact addresses into structured components."""
from alembic import op
import sqlalchemy as sa

from library.address_formatting import imported_address_fields

revision = "c2e8a6f41903"
down_revision = "9bc5a781e204"
branch_labels = None
depends_on = None

_COLUMNS = {"street": 200, "building_number": 20, "apartment_number": 20,
            "postal_code": 10, "city": 200, "country": 100}


def upgrade():
    for name, length in _COLUMNS.items():
        op.add_column("addresses", sa.Column(name, sa.String(length), nullable=True))
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, raw_address FROM addresses")).mappings().all()
    for row in rows:
        # This helper calls parse_address_text_heuristic; unsafe/partial parses
        # retain ALL original text in city, or abort rather than truncate it.
        fields = imported_address_fields(row["raw_address"])
        connection.execute(sa.text("""
            UPDATE addresses SET street=:street, building_number=:building_number,
                apartment_number=:apartment_number, postal_code=:postal_code,
                city=:city, country=:country WHERE id=:id
        """), {**fields, "id": row["id"]})
    op.alter_column("addresses", "city", nullable=False)
    op.drop_column("addresses", "raw_address")


def downgrade():
    op.add_column("addresses", sa.Column("raw_address", sa.Text(), nullable=True))
    # Frozen format_address equivalent, following neighboring migrations' SQL
    # convention and avoiding any dependency on the current ORM model.
    op.execute(sa.text("""
        UPDATE addresses SET raw_address = concat_ws(', ',
            nullif(concat_ws(' ', nullif(btrim(street), ''), nullif(btrim(building_number), ''))
                || CASE WHEN nullif(btrim(apartment_number), '') IS NOT NULL
                        THEN '/' || btrim(apartment_number) ELSE '' END, ''),
            nullif(concat_ws(' ', nullif(btrim(postal_code), ''), nullif(btrim(city), '')), ''),
            CASE WHEN btrim(country) <> 'Polska' THEN nullif(btrim(country), '') END)
    """))
    op.alter_column("addresses", "raw_address", nullable=False)
    for name in reversed(_COLUMNS):
        op.drop_column("addresses", name)

"""geo_events become the registry of world events (ADR-034)

Revision ID: c7e2b5a9d814
Revises: b9d3f1a7c526
Create Date: 2026-11-01 00:00:00.000000

An event may now have no country and no date ("CrowdStrike outage", "Bitcoin halving", "WHO declares a
pandemic"), several names (aliases), a kind, a date range and organizations/persons as participants.

* ``geo_events``: ``event_date`` nullable (``date_precision='unknown'`` then), ``end_date_precision``,
  ``is_ongoing``, ``kind`` (FK ``geo_event_kinds``), ``version``; ``dedup_key`` becomes UNIQUE (the former
  "look up, then insert" raced).
* ``geo_event_aliases``: every name an event is known by, with ``name_key`` (NFC, spaces, casefold) and
  ``search_key`` (accents and punctuation folded, trigram index).
* ``geo_event_organizations`` / ``geo_event_persons``: participants with real foreign keys; roles are a
  dictionary (``geo_event_roles``) instead of a CHECK, so ``host`` or ``winner`` need no migration.
* ``geo_event_mention_links``: the reader's decision "in document D the event name N means event E"
  (a named-event mention in ``document_entities`` is rebuilt on every NER refresh, so the decision cannot
  live on that row).
* ``geo_event_sources.document_event_id``: where a source came from, ``ON DELETE SET NULL`` because the
  timeline extraction deletes and recreates its rows.
* ``country_relation_evidence``: ``event_id`` becomes ``RESTRICT`` (deleting an event must not silently
  remove the grounds of a confirmed assessment) and ``evidence_kind`` (``direct`` needs both countries in the
  event, ``context`` is background only).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c7e2b5a9d814"
down_revision: Union[str, None] = "b9d3f1a7c526"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KINDS = [
    ("election", "Wybory"),
    ("summit", "Szczyt / spotkanie"),
    ("diplomatic", "Dyplomacja"),
    ("agreement", "Umowa / traktat"),
    ("sanctions", "Sankcje"),
    ("conflict", "Konflikt zbrojny"),
    ("exercise", "Ćwiczenia wojskowe"),
    ("protest", "Protesty / niepokoje"),
    ("disaster", "Katastrofa / klęska żywiołowa"),
    ("health", "Zdrowie / pandemia"),
    ("outage", "Awaria / incydent techniczny"),
    ("cyber", "Cyberatak / luka w zabezpieczeniach"),
    ("product_launch", "Premiera produktu"),
    ("corporate", "Wydarzenie korporacyjne"),
    ("market", "Rynki / finanse"),
    ("other", "Inne"),
]
_ROLES = [
    ("actor", "sprawca"),
    ("target", "cel"),
    ("affected", "dotknięty"),
    ("location", "miejsce"),
    ("host", "gospodarz"),
    ("organizer", "organizator"),
    ("winner", "zwycięzca"),
    ("subject", "podmiot"),
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    kinds = op.create_table(
        "geo_event_kinds",
        sa.Column("code", sa.String(length=30), primary_key=True),
        sa.Column("label", sa.String(length=80), nullable=False),
    )
    op.bulk_insert(kinds, [{"code": code, "label": label} for code, label in _KINDS])
    roles = op.create_table(
        "geo_event_roles",
        sa.Column("code", sa.String(length=20), primary_key=True),
        sa.Column("label", sa.String(length=40), nullable=False),
    )
    op.bulk_insert(roles, [{"code": code, "label": label} for code, label in _ROLES])

    # --- geo_events -------------------------------------------------------------------------------------
    op.alter_column("geo_events", "event_date", existing_type=sa.Date(), nullable=True)
    op.drop_constraint("ck_geo_events_precision", "geo_events", type_="check")
    op.create_check_constraint(
        "ck_geo_events_precision", "geo_events", "date_precision IN ('day', 'month', 'year', 'unknown')"
    )
    op.create_check_constraint(
        "ck_geo_events_unknown_date", "geo_events", "(event_date IS NULL) = (date_precision = 'unknown')"
    )
    op.add_column("geo_events", sa.Column("end_date_precision", sa.String(length=10), nullable=True))
    op.create_check_constraint(
        "ck_geo_events_end_precision",
        "geo_events",
        "end_date_precision IS NULL OR end_date_precision IN ('day', 'month', 'year')",
    )
    op.add_column("geo_events", sa.Column("is_ongoing", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_check_constraint(
        "ck_geo_events_ongoing", "geo_events", "NOT (is_ongoing AND event_date_end IS NOT NULL)"
    )
    op.add_column(
        "geo_events",
        sa.Column(
            "kind",
            sa.String(length=30),
            sa.ForeignKey("geo_event_kinds.code", ondelete="RESTRICT"),
            nullable=False,
            server_default="other",
        ),
    )
    op.add_column("geo_events", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.create_index("idx_geo_events_kind_date", "geo_events", ["kind", "event_date"])

    # dedup_key: UNIQUE. Defensive: should an earlier race have produced equal keys, only the oldest keeps it.
    op.execute(
        """
        UPDATE geo_events SET dedup_key = NULL WHERE id IN (
            SELECT id FROM (
                SELECT id, row_number() OVER (PARTITION BY dedup_key ORDER BY id) AS rn
                FROM geo_events WHERE dedup_key IS NOT NULL
            ) ranked WHERE rn > 1
        )
        """
    )
    op.drop_index("idx_geo_events_dedup_key", table_name="geo_events")
    op.create_index(
        "uq_geo_events_dedup_key", "geo_events", ["dedup_key"], unique=True, postgresql_where=sa.text("dedup_key IS NOT NULL")
    )

    # --- participants: roles become a dictionary -----------------------------------------------------------
    op.drop_constraint("ck_geo_event_participants_role", "geo_event_participants", type_="check")
    op.create_foreign_key(
        "fk_geo_event_participants_role", "geo_event_participants", "geo_event_roles", ["role"], ["code"],
        ondelete="RESTRICT",
    )
    op.create_table(
        "geo_event_organizations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("geo_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("role", sa.String(length=20), sa.ForeignKey("geo_event_roles.code", ondelete="RESTRICT"), nullable=False),
        sa.UniqueConstraint("event_id", "organization_id", "role", name="uq_geo_event_organizations"),
    )
    op.create_index("idx_geo_event_organizations_org", "geo_event_organizations", ["organization_id", "event_id"])
    op.create_table(
        "geo_event_persons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("geo_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("persons.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("role", sa.String(length=20), sa.ForeignKey("geo_event_roles.code", ondelete="RESTRICT"), nullable=False),
        sa.UniqueConstraint("event_id", "person_id", "role", name="uq_geo_event_persons"),
    )
    op.create_index("idx_geo_event_persons_person", "geo_event_persons", ["person_id", "event_id"])

    # --- aliases --------------------------------------------------------------------------------------------
    op.create_table(
        "geo_event_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("geo_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("name_key", sa.Text(), nullable=False),
        sa.Column("search_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("event_id", "name_key", name="uq_geo_event_aliases"),
        sa.CheckConstraint("name_key <> ''", name="ck_geo_event_aliases_key"),
    )
    op.create_index("idx_geo_event_aliases_name_key", "geo_event_aliases", ["name_key"])
    op.execute("CREATE INDEX idx_geo_event_aliases_search ON geo_event_aliases USING gin (search_key gin_trgm_ops)")
    # Every existing event is known by its title.
    op.execute(
        """
        INSERT INTO geo_event_aliases (event_id, alias, name_key, search_key)
        SELECT id, title, lower(regexp_replace(btrim(title), '\\s+', ' ', 'g')),
               btrim(regexp_replace(lower(unaccent(title)), '[^a-z0-9]+', ' ', 'g'))
        FROM geo_events
        ON CONFLICT DO NOTHING
        """
    )

    # --- mention links --------------------------------------------------------------------------------------
    op.create_table(
        "geo_event_mention_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name_key", sa.Text(), nullable=False),
        sa.Column("surface", sa.Text(), nullable=False),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("geo_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="confirmed"),
        sa.Column("decided_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "name_key", "event_id", name="uq_geo_event_mention_links"),
        sa.CheckConstraint("status IN ('confirmed', 'rejected')", name="ck_geo_event_mention_links_status"),
    )
    op.create_index("idx_geo_event_mention_links_event", "geo_event_mention_links", ["event_id", "status"])
    op.create_index("idx_geo_event_mention_links_name", "geo_event_mention_links", ["name_key"])

    # --- sources and evidence -------------------------------------------------------------------------------
    op.add_column(
        "geo_event_sources",
        sa.Column("document_event_id", sa.Integer(), sa.ForeignKey("document_events.id", ondelete="SET NULL"), nullable=True),
    )
    op.drop_constraint("country_relation_evidence_event_id_fkey", "country_relation_evidence", type_="foreignkey")
    op.create_foreign_key(
        "country_relation_evidence_event_id_fkey", "country_relation_evidence", "geo_events", ["event_id"], ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "country_relation_evidence",
        sa.Column("evidence_kind", sa.String(length=10), nullable=False, server_default="direct"),
    )
    op.create_check_constraint(
        "ck_country_relation_evidence_kind", "country_relation_evidence", "evidence_kind IN ('direct', 'context')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_country_relation_evidence_kind", "country_relation_evidence", type_="check")
    op.drop_column("country_relation_evidence", "evidence_kind")
    op.drop_constraint("country_relation_evidence_event_id_fkey", "country_relation_evidence", type_="foreignkey")
    op.create_foreign_key(
        "country_relation_evidence_event_id_fkey", "country_relation_evidence", "geo_events", ["event_id"], ["id"],
        ondelete="CASCADE",
    )
    op.drop_column("geo_event_sources", "document_event_id")
    op.drop_table("geo_event_mention_links")
    op.drop_table("geo_event_aliases")
    op.drop_table("geo_event_persons")
    op.drop_table("geo_event_organizations")
    op.drop_constraint("fk_geo_event_participants_role", "geo_event_participants", type_="foreignkey")
    op.create_check_constraint(
        "ck_geo_event_participants_role", "geo_event_participants", "role IN ('actor', 'target', 'affected', 'location')"
    )
    op.drop_index("uq_geo_events_dedup_key", table_name="geo_events")
    op.create_index("idx_geo_events_dedup_key", "geo_events", ["dedup_key"])
    op.drop_index("idx_geo_events_kind_date", table_name="geo_events")
    op.drop_column("geo_events", "version")
    op.drop_column("geo_events", "kind")
    op.drop_constraint("ck_geo_events_ongoing", "geo_events", type_="check")
    op.drop_column("geo_events", "is_ongoing")
    op.drop_constraint("ck_geo_events_end_precision", "geo_events", type_="check")
    op.drop_column("geo_events", "end_date_precision")
    op.drop_constraint("ck_geo_events_unknown_date", "geo_events", type_="check")
    op.drop_constraint("ck_geo_events_precision", "geo_events", type_="check")
    op.create_check_constraint("ck_geo_events_precision", "geo_events", "date_precision IN ('day', 'month', 'year')")
    op.alter_column("geo_events", "event_date", existing_type=sa.Date(), nullable=False)
    op.drop_table("geo_event_roles")
    op.drop_table("geo_event_kinds")

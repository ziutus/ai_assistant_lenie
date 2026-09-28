"""Create contact fact sources, assertions and resolution slots.

Revision ID: 1915e3243ed6
Revises: 83b1c79306a4
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "1915e3243ed6"
down_revision = "83b1c79306a4"
branch_labels = None
depends_on = None


def _timestamps(updated=False):
    columns = [sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now())]
    if updated:
        columns.append(sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
    return columns


def upgrade() -> None:
    sources = op.create_table(
        "contact_fact_sources",
        sa.Column("key", sa.String(30), primary_key=True),
        sa.Column("label", sa.String(100)),
        sa.Column("default_priority", sa.SmallInteger(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("default_priority BETWEEN 0 AND 100", name="ck_contact_fact_source_priority"),
    )
    attributes = op.create_table(
        "contact_fact_attributes",
        sa.Column("key", sa.String(50), primary_key=True),
        sa.Column("cardinality", sa.String(10), nullable=False),
        sa.Column("min_auto_priority", sa.SmallInteger(), nullable=False, server_default="0"),
        *_timestamps(),
        sa.CheckConstraint("cardinality IN ('single', 'many')", name="ck_contact_fact_attribute_cardinality"),
    )
    policies = op.create_table(
        "contact_fact_source_policies",
        sa.Column("source_key", sa.String(30), sa.ForeignKey("contact_fact_sources.key"), primary_key=True),
        sa.Column("attribute_key", sa.String(50), sa.ForeignKey("contact_fact_attributes.key"), primary_key=True),
        sa.Column("priority", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("priority BETWEEN 0 AND 100", name="ck_contact_fact_policy_priority"),
    )
    op.create_table(
        "contact_fact_slots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attribute_key", sa.String(50), sa.ForeignKey("contact_fact_attributes.key"), nullable=False),
        sa.Column("item_key", sa.String(100), nullable=False),
        sa.Column("resolution_mode", sa.String(20), nullable=False, server_default="auto"),
        sa.Column("selected_assertion_id", sa.Integer()),
        sa.Column("decision_by", sa.String(100)),
        sa.Column("decision_note", sa.Text()),
        sa.Column("resolved_at", sa.DateTime()),
        *_timestamps(True),
        sa.UniqueConstraint("contact_id", "attribute_key", "item_key", name="uq_contact_fact_slots_item"),
        sa.CheckConstraint("resolution_mode IN ('auto', 'pinned', 'suppressed')", name="ck_contact_fact_slot_mode"),
    )
    op.create_index("idx_contact_fact_slots_contact_attribute", "contact_fact_slots", ["contact_id", "attribute_key"])
    op.create_table(
        "contact_fact_assertions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slot_id", sa.Integer(), sa.ForeignKey("contact_fact_slots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_key", sa.String(30), sa.ForeignKey("contact_fact_sources.key"), nullable=False),
        sa.Column("source_record_key", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("asserted_by", sa.String(100)),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("confidence", sa.Numeric(4, 3)),
        sa.Column("status", sa.String(20), nullable=False, server_default="candidate"),
        sa.Column("evidence_note", sa.Text()),
        sa.Column("reviewed_by", sa.String(100)),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("review_note", sa.Text()),
        sa.Column("observed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("dedup_key", sa.String(64), nullable=False, unique=True),
        *_timestamps(True),
        sa.UniqueConstraint("slot_id", "id", name="uq_contact_fact_assertions_slot_id"),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_contact_fact_assertion_confidence"),
        sa.CheckConstraint("status IN ('candidate', 'confirmed', 'rejected', 'superseded')", name="ck_contact_fact_assertion_status"),
    )
    op.create_index("idx_contact_fact_assertions_slot_status_source", "contact_fact_assertions", ["slot_id", "status", "source_key"])
    op.create_foreign_key(
        "fk_contact_fact_slots_selected_assertion", "contact_fact_slots", "contact_fact_assertions",
        ["id", "selected_assertion_id"], ["slot_id", "id"], use_alter=True,
    )
    op.add_column("contact_education", sa.Column("fact_slot_id", sa.Integer()))
    op.create_foreign_key("fk_contact_education_fact_slot", "contact_education", "contact_fact_slots", ["fact_slot_id"], ["id"], ondelete="SET NULL")
    op.create_unique_constraint("uq_contact_education_fact_slot", "contact_education", ["fact_slot_id"])
    op.bulk_insert(sources, [dict(key=key, default_priority=priority) for key, priority in (
        ("facebook", 20), ("linkedin", 40), ("user_manual", 100), ("ceidg", 60), ("other", 10), ("legacy_unknown", 5),
    )])
    op.bulk_insert(attributes, [dict(key=key, cardinality=cardinality, min_auto_priority=priority)
                               for key, cardinality, priority in (
        ("birthday", "single", 50), ("education", "many", 30), ("current_city", "single", 30),
        ("hometown", "single", 30), ("gender", "single", 30),
    )])
    op.bulk_insert(policies, [dict(source_key=source, attribute_key=attribute, priority=priority)
                             for source, attribute, priority in (
        ("linkedin", "education", 80), ("facebook", "education", 30), ("facebook", "birthday", 10),
        ("linkedin", "birthday", 20), ("ceidg", "current_city", 70),
    )])


def downgrade() -> None:
    op.drop_constraint("uq_contact_education_fact_slot", "contact_education", type_="unique")
    op.drop_constraint("fk_contact_education_fact_slot", "contact_education", type_="foreignkey")
    op.drop_column("contact_education", "fact_slot_id")
    op.drop_constraint("fk_contact_fact_slots_selected_assertion", "contact_fact_slots", type_="foreignkey")
    for table in ("contact_fact_assertions", "contact_fact_slots", "contact_fact_source_policies",
                  "contact_fact_attributes", "contact_fact_sources"):
        op.drop_table(table)

"""Global entity relations with evidence and the preferred extraction model.

Revision ID: e4b8c2a79061
Revises: d91f7a6b203e
"""
from alembic import op
import sqlalchemy as sa

revision = "e4b8c2a79061"
down_revision = "d91f7a6b203e"
branch_labels = None
depends_on = None

ADDED = (("openrouter/google/gemma-4-31b-it", "Gemma 4 31B (OpenRouter)"),)


def upgrade():
    op.create_table(
        "entity_relations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subject_person_id", sa.Integer(), sa.ForeignKey("persons.id", ondelete="CASCADE")),
        sa.Column("subject_organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE")),
        sa.Column("object_person_id", sa.Integer(), sa.ForeignKey("persons.id", ondelete="CASCADE")),
        sa.Column("object_organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE")),
        sa.Column("object_country_slug", sa.String(80)),
        sa.Column("relation", sa.String(40), nullable=False),
        sa.Column("title", sa.String(200)),
        sa.Column("valid_from", sa.Date()), sa.Column("valid_to", sa.Date()),
        sa.Column("status", sa.String(20), nullable=False, server_default="proposed"),
        sa.Column("detection_method", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime()),
        sa.Column("decided_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("projected_table", sa.String(40)), sa.Column("projected_row_id", sa.Integer()),
        sa.CheckConstraint("(CASE WHEN subject_person_id IS NULL THEN 0 ELSE 1 END + "
                           "CASE WHEN subject_organization_id IS NULL THEN 0 ELSE 1 END) = 1",
                           name="ck_entity_relations_subject"),
        sa.CheckConstraint("(CASE WHEN object_person_id IS NULL THEN 0 ELSE 1 END + "
                           "CASE WHEN object_organization_id IS NULL THEN 0 ELSE 1 END + "
                           "CASE WHEN object_country_slug IS NULL THEN 0 ELSE 1 END) = 1",
                           name="ck_entity_relations_object"),
        sa.CheckConstraint("valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
                           name="ck_entity_relations_dates"),
        sa.CheckConstraint("status IN ('proposed', 'confirmed', 'rejected')", name="ck_entity_relations_status"),
        sa.CheckConstraint("detection_method IN ('llm', 'wikidata', 'manual')", name="ck_entity_relations_method"),
    )
    for column in ("subject_person_id", "subject_organization_id", "object_person_id", "object_organization_id",
                   "object_country_slug", "status", "decided_by_user_id"):
        op.create_index(f"ix_entity_relations_{column}", "entity_relations", [column])
    op.create_table(
        "entity_relation_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("relation_id", sa.Integer(), sa.ForeignKey("entity_relations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("quote", sa.Text()), sa.Column("claim", sa.String(30)), sa.Column("source_url", sa.Text()),
        sa.Column("model", sa.String(120)), sa.Column("prompt_version", sa.String(40)),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("relation_id", "content_hash", name="uq_entity_relation_evidence_hash"),
    )
    for column in ("relation_id", "document_id"):
        op.create_index(f"ix_entity_relation_evidence_{column}", "entity_relation_evidence", [column])
    for model_id, label in ADDED:
        op.execute(sa.text("INSERT INTO llm_models (model_id, label, provider, external, verified, status) "
                           "VALUES (:model_id, :label, 'openrouter', true, false, 'active') "
                           "ON CONFLICT (model_id) DO NOTHING").bindparams(model_id=model_id, label=label))


def downgrade():
    # The model may have been edited or used since upgrade; preserve it.
    op.drop_table("entity_relation_evidence")
    op.drop_table("entity_relations")

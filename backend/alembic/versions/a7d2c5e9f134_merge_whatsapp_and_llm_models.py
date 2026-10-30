"""Merge the WhatsApp live-sync branch (e4a7c1d9b358) with the Vertex price / llm_models branch (f2c8a4d6b190).

Both branches grew from d3b8f1a6c924 in parallel (WhatsApp deployed first, the LLM allowlist after). This
revision joins them so the history has a single head again; it changes no schema.
"""

revision = "a7d2c5e9f134"
down_revision = ("e4a7c1d9b358", "f2c8a4d6b190")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

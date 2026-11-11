"""Persist optional summaries and a shared daily request limit."""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in (
        sa.Column("input_fingerprint", sa.String(64), nullable=True),
        sa.Column("evaluated_level", sa.SmallInteger(), nullable=True),
        sa.Column("evaluated_attempt", sa.Integer(), nullable=True),
        sa.Column("narrative_status", sa.String(24), nullable=False, server_default="disabled"),
        sa.Column("narrative_text", sa.Text(), nullable=True),
        sa.Column("narrative_model", sa.String(100), nullable=True),
        sa.Column("narrative_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("narrative_created_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("analyses", column, schema="clinical")
    op.create_table(
        "narrative_usage",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("requests", sa.Integer(), nullable=False),
        schema="clinical",
    )


def downgrade() -> None:
    op.drop_table("narrative_usage", schema="clinical")
    for name in ("narrative_created_at", "narrative_started_at", "narrative_model", "narrative_text", "narrative_status", "evaluated_attempt", "evaluated_level", "input_fingerprint"):
        op.drop_column("analyses", name, schema="clinical")

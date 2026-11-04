"""Límites compartidos entre instancias; no contienen IP ni correo en claro."""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "rate_limit_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("clock_timestamp()")),
        schema="identity",
    )
    op.create_index("ix_rate_limit_key_time", "rate_limit_events", ["key_hash", "occurred_at"], schema="identity")
    op.create_index("ix_rate_limit_time", "rate_limit_events", ["occurred_at"], schema="identity")

def downgrade() -> None:
    op.drop_table("rate_limit_events", schema="identity")

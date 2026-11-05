"""Add the self-reported phobia grade per patient (BPMN step "Ajustar grado de fobia", contract v1.1.0)."""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patients", sa.Column("phobia_grade", sa.SmallInteger(), nullable=True), schema="clinical")
    op.add_column("patients", sa.Column("phobia_grade_updated_at", sa.DateTime(timezone=True), nullable=True), schema="clinical")
    op.create_check_constraint(
        op.f("ck_patients_phobia_grade"),
        "patients",
        "phobia_grade IS NULL OR phobia_grade BETWEEN 1 AND 5",
        schema="clinical",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_patients_phobia_grade"), "patients", schema="clinical", type_="check")
    op.drop_column("patients", "phobia_grade_updated_at", schema="clinical")
    op.drop_column("patients", "phobia_grade", schema="clinical")

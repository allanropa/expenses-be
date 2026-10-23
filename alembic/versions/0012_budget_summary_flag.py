"""Add a per-budget summary visibility flag."""

from alembic import op
import sqlalchemy as sa


revision = "0012_budget_summary_flag"
down_revision = "0011_budget_targets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("budgets", sa.Column("show_in_summary", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.alter_column("budgets", "show_in_summary", server_default=None)


def downgrade() -> None:
    op.drop_column("budgets", "show_in_summary")

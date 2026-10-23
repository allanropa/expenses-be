"""Allow budgets to target multiple accounts or cards."""

from alembic import op
import sqlalchemy as sa


revision = "0011_budget_targets"
down_revision = "0010_multiple_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("budgets", sa.Column("account_ids", sa.JSON(), nullable=True))
    op.add_column("budgets", sa.Column("card_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("budgets", "card_ids")
    op.drop_column("budgets", "account_ids")

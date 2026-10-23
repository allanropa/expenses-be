"""Store multiple categories on transactions and category budgets."""

from alembic import op
import sqlalchemy as sa


revision = "0010_multiple_categories"
down_revision = "0009_duplicate_names"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("financial_transactions", sa.Column("category_ids", sa.JSON(), nullable=True))
    op.add_column("budgets", sa.Column("category_ids", sa.JSON(), nullable=True))
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        bind.execute(sa.text("UPDATE financial_transactions SET category_ids = json_array(category_id)"))
        bind.execute(sa.text("UPDATE budgets SET category_ids = json_array(category_id) WHERE category_id IS NOT NULL"))
    else:
        bind.execute(sa.text("UPDATE financial_transactions SET category_ids = json_build_array(category_id)"))
        bind.execute(sa.text("UPDATE budgets SET category_ids = json_build_array(category_id) WHERE category_id IS NOT NULL"))


def downgrade() -> None:
    op.drop_column("budgets", "category_ids")
    op.drop_column("financial_transactions", "category_ids")

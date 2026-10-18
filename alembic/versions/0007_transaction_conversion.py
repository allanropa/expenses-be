"""Add conversion tracking to financial transactions."""

from alembic import op
import sqlalchemy as sa

revision = "0007_transaction_conversion"
down_revision = "0006_card_rate_precision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("financial_transactions", sa.Column("original_amount", sa.Numeric(20, 4), nullable=True))
    op.add_column("financial_transactions", sa.Column("original_currency", sa.String(3), nullable=True))


def downgrade() -> None:
    op.drop_column("financial_transactions", "original_currency")
    op.drop_column("financial_transactions", "original_amount")

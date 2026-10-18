"""Increase credit-card monthly interest precision."""

from alembic import op
import sqlalchemy as sa

revision = "0006_card_rate_precision"
down_revision = "0005_loans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("interest_rate_configurations", "monthly_rate", existing_type=sa.Numeric(12, 8), type_=sa.Numeric(20, 12), existing_nullable=False)
    op.alter_column("credit_purchases", "monthly_interest_rate", existing_type=sa.Numeric(12, 8), type_=sa.Numeric(20, 12), existing_nullable=False)


def downgrade() -> None:
    op.alter_column("credit_purchases", "monthly_interest_rate", existing_type=sa.Numeric(20, 12), type_=sa.Numeric(12, 8), existing_nullable=False)
    op.alter_column("interest_rate_configurations", "monthly_rate", existing_type=sa.Numeric(20, 12), type_=sa.Numeric(12, 8), existing_nullable=False)

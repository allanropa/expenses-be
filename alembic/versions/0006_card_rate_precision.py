"""Increase credit-card monthly interest precision."""

from alembic import op
import sqlalchemy as sa

revision = "0006_card_rate_precision"
down_revision = "0005_loans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("interest_rate_configurations", recreate="always") as batch:
        batch.alter_column("monthly_rate", existing_type=sa.Numeric(12, 8), type_=sa.Numeric(20, 12), existing_nullable=False)
    with op.batch_alter_table("credit_purchases", recreate="always") as batch:
        batch.alter_column("monthly_interest_rate", existing_type=sa.Numeric(12, 8), type_=sa.Numeric(20, 12), existing_nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("credit_purchases", recreate="always") as batch:
        batch.alter_column("monthly_interest_rate", existing_type=sa.Numeric(20, 12), type_=sa.Numeric(12, 8), existing_nullable=False)
    with op.batch_alter_table("interest_rate_configurations", recreate="always") as batch:
        batch.alter_column("monthly_rate", existing_type=sa.Numeric(20, 12), type_=sa.Numeric(12, 8), existing_nullable=False)

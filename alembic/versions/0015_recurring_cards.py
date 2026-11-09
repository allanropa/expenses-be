"""Allow recurring expenses on credit cards."""

from alembic import op
import sqlalchemy as sa

revision = "0015_recurring_cards"
down_revision = "0014_payment_components"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recurring_payments", sa.Column("card_id", sa.Integer(), nullable=True))
    op.add_column("recurring_payments", sa.Column("currency", sa.String(3), nullable=True))
    op.create_foreign_key("fk_recurring_card", "recurring_payments", "credit_cards", ["card_id"], ["id"], ondelete="RESTRICT")


def downgrade() -> None:
    op.drop_constraint("fk_recurring_card", "recurring_payments", type_="foreignkey")
    op.drop_column("recurring_payments", "currency")
    op.drop_column("recurring_payments", "card_id")

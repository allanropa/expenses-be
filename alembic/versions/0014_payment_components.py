"""Associate payment costs with card and loan payments."""

from alembic import op
import sqlalchemy as sa


revision = "0014_payment_components"
down_revision = "0013_recurring_payments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("card_charges", sa.Column("operation_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_card_charges_operation_id", "card_charges", "financial_operations", ["operation_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_card_charges_operation_id", "card_charges", ["operation_id"])
    op.add_column("card_charges", sa.Column("payment_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_card_charges_payment_id", "card_charges", "card_payments", ["payment_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_card_charges_payment_id", "card_charges", ["payment_id"])
    op.add_column("card_payments", sa.Column("total_paid", sa.Numeric(20, 4), nullable=True))
    op.execute("UPDATE card_payments SET total_paid = obligation_amount")
    op.alter_column("card_payments", "total_paid", nullable=False)
    op.add_column("loan_payments", sa.Column("total_paid", sa.Numeric(20, 4), nullable=True))
    op.execute("UPDATE loan_payments SET total_paid = total_amount")
    op.alter_column("loan_payments", "total_paid", nullable=False)
    op.add_column("financial_transactions", sa.Column("is_payment_component", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("financial_transactions", sa.Column("payment_component_type", sa.String(length=16), nullable=True))
    op.add_column("financial_transactions", sa.Column("payment_component_id", sa.Integer(), nullable=True))
    op.create_index("ix_financial_transactions_is_payment_component", "financial_transactions", ["is_payment_component"])
    op.alter_column("financial_transactions", "is_payment_component", server_default=None)


def downgrade() -> None:
    op.drop_column("loan_payments", "total_paid")
    op.drop_column("card_payments", "total_paid")
    op.drop_index("ix_card_charges_payment_id", table_name="card_charges")
    op.drop_constraint("fk_card_charges_payment_id", "card_charges", type_="foreignkey")
    op.drop_column("card_charges", "payment_id")
    op.drop_index("ix_card_charges_operation_id", table_name="card_charges")
    op.drop_constraint("fk_card_charges_operation_id", "card_charges", type_="foreignkey")
    op.drop_column("card_charges", "operation_id")
    op.drop_index("ix_financial_transactions_is_payment_component", table_name="financial_transactions")
    op.drop_column("financial_transactions", "payment_component_id")
    op.drop_column("financial_transactions", "payment_component_type")
    op.drop_column("financial_transactions", "is_payment_component")

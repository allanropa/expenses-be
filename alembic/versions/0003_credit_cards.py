"""Create credit cards, purchases, installments and payments."""

from alembic import op
import sqlalchemy as sa

revision = "0003_credit_cards"
down_revision = "0002_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "credit_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("issuing_bank", sa.String(length=120), nullable=True),
        sa.Column("statement_closing_day", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "name"),
    )
    op.create_index("ix_credit_cards_user_id", "credit_cards", ["user_id"])

    op.create_table(
        "card_currencies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("credit_limit", sa.Numeric(20, 4), nullable=True),
        sa.ForeignKeyConstraint(["card_id"], ["credit_cards.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("card_id", "currency"),
    )
    op.create_index("ix_card_currencies_card_id", "card_currencies", ["card_id"])

    op.create_table(
        "interest_rate_configurations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("monthly_rate", sa.Numeric(12, 8), nullable=False),
        sa.Column("rate_type", sa.String(length=16), nullable=False),
        sa.Column("periodicity", sa.String(length=16), nullable=False),
        sa.Column("calculation_method", sa.String(length=16), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["card_id"], ["credit_cards.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_interest_rate_configurations_card_id", "interest_rate_configurations", ["card_id"])

    op.create_table(
        "credit_purchases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("operation_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("installments_count", sa.Integer(), nullable=False),
        sa.Column("monthly_interest_rate", sa.Numeric(12, 8), nullable=False),
        sa.Column("financing_method", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["operation_id"], ["financial_operations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["card_id"], ["credit_cards.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("operation_id"),
    )
    op.create_index("ix_credit_purchases_user_id", "credit_purchases", ["user_id"])
    op.create_index("ix_credit_purchases_card_id", "credit_purchases", ["card_id"])
    op.create_index("ix_credit_purchases_purchase_date", "credit_purchases", ["purchase_date"])

    op.create_table(
        "installments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("purchase_id", sa.Integer(), nullable=False),
        sa.Column("installment_number", sa.Integer(), nullable=False),
        sa.Column("statement_closing_date", sa.Date(), nullable=False),
        sa.Column("principal_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("estimated_interest", sa.Numeric(20, 4), nullable=False),
        sa.Column("estimated_total", sa.Numeric(20, 4), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["purchase_id"], ["credit_purchases.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_installments_purchase_id", "installments", ["purchase_id"])
    op.create_index("ix_installments_statement_closing_date", "installments", ["statement_closing_date"])

    op.create_table(
        "card_charges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("purchase_id", sa.Integer(), nullable=True),
        sa.Column("charge_type", sa.String(length=24), nullable=False),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("charge_date", sa.Date(), nullable=False),
        sa.Column("is_estimated", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["card_id"], ["credit_cards.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["purchase_id"], ["credit_purchases.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_card_charges_user_id", "card_charges", ["user_id"])
    op.create_index("ix_card_charges_card_id", "card_charges", ["card_id"])
    op.create_index("ix_card_charges_charge_date", "card_charges", ["charge_date"])

    op.create_table(
        "card_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("operation_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("source_account_id", sa.Integer(), nullable=True),
        sa.Column("obligation_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("obligation_currency", sa.String(length=3), nullable=False),
        sa.Column("source_amount", sa.Numeric(20, 4), nullable=True),
        sa.Column("source_currency", sa.String(length=3), nullable=True),
        sa.Column("exchange_rate", sa.Numeric(20, 10), nullable=True),
        sa.Column("fee_amount", sa.Numeric(20, 4), nullable=True),
        sa.Column("fee_currency", sa.String(length=3), nullable=True),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["operation_id"], ["financial_operations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["card_id"], ["credit_cards.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("operation_id"),
    )
    op.create_index("ix_card_payments_user_id", "card_payments", ["user_id"])
    op.create_index("ix_card_payments_card_id", "card_payments", ["card_id"])
    op.create_index("ix_card_payments_payment_date", "card_payments", ["payment_date"])

    op.create_table(
        "card_payment_allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payment_id", sa.Integer(), nullable=False),
        sa.Column("charge_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["card_payments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["charge_id"], ["card_charges.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_card_payment_allocations_payment_id", "card_payment_allocations", ["payment_id"])
    op.create_index("ix_card_payment_allocations_charge_id", "card_payment_allocations", ["charge_id"])

    op.create_table(
        "card_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("operation_id", sa.Integer(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.ForeignKeyConstraint(["operation_id"], ["financial_operations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["card_id"], ["credit_cards.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_card_movements_operation_id", "card_movements", ["operation_id"])
    op.create_index("ix_card_movements_card_id", "card_movements", ["card_id"])

    with op.batch_alter_table("financial_transactions", recreate="always") as batch:
        batch.alter_column("account_id", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("card_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("credit_purchase_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("payment_method", sa.String(length=8), nullable=False, server_default="debit"))
        batch.create_foreign_key("fk_financial_transactions_card_id", "credit_cards", ["card_id"], ["id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_financial_transactions_purchase_id", "credit_purchases", ["credit_purchase_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_financial_transactions_card_id", "financial_transactions", ["card_id"])
    op.create_index("ix_financial_transactions_credit_purchase_id", "financial_transactions", ["credit_purchase_id"])


def downgrade() -> None:
    op.drop_index("ix_financial_transactions_credit_purchase_id", table_name="financial_transactions")
    op.drop_index("ix_financial_transactions_card_id", table_name="financial_transactions")
    with op.batch_alter_table("financial_transactions", recreate="always") as batch:
        batch.drop_constraint("fk_financial_transactions_purchase_id", type_="foreignkey")
        batch.drop_constraint("fk_financial_transactions_card_id", type_="foreignkey")
        batch.drop_column("payment_method")
        batch.drop_column("credit_purchase_id")
        batch.drop_column("card_id")
        batch.alter_column("account_id", existing_type=sa.Integer(), nullable=False)
    for index_name, table_name in [
        ("ix_card_movements_card_id", "card_movements"),
        ("ix_card_movements_operation_id", "card_movements"),
        ("ix_card_payment_allocations_charge_id", "card_payment_allocations"),
        ("ix_card_payment_allocations_payment_id", "card_payment_allocations"),
        ("ix_card_payments_payment_date", "card_payments"),
        ("ix_card_payments_card_id", "card_payments"),
        ("ix_card_payments_user_id", "card_payments"),
        ("ix_card_charges_charge_date", "card_charges"),
        ("ix_card_charges_card_id", "card_charges"),
        ("ix_card_charges_user_id", "card_charges"),
        ("ix_installments_statement_closing_date", "installments"),
        ("ix_installments_purchase_id", "installments"),
        ("ix_credit_purchases_purchase_date", "credit_purchases"),
        ("ix_credit_purchases_card_id", "credit_purchases"),
        ("ix_credit_purchases_user_id", "credit_purchases"),
        ("ix_interest_rate_configurations_card_id", "interest_rate_configurations"),
        ("ix_card_currencies_card_id", "card_currencies"),
        ("ix_credit_cards_user_id", "credit_cards"),
    ]:
        op.drop_index(index_name, table_name=table_name)
    for table_name in [
        "card_movements",
        "card_payment_allocations",
        "card_payments",
        "card_charges",
        "installments",
        "credit_purchases",
        "interest_rate_configurations",
        "card_currencies",
        "credit_cards",
    ]:
        op.drop_table(table_name)

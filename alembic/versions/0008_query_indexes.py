"""Add indexes for authenticated list and dashboard queries."""

from alembic import op


revision = "0008_query_indexes"
down_revision = "0007_transaction_conversion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_financial_transactions_user_status_date",
        "financial_transactions",
        ["user_id", "status", "transaction_date"],
    )
    op.create_index(
        "ix_financial_transactions_user_account_date",
        "financial_transactions",
        ["user_id", "account_id", "transaction_date"],
    )
    op.create_index(
        "ix_financial_transactions_user_category_date",
        "financial_transactions",
        ["user_id", "category_id", "transaction_date"],
    )
    op.create_index(
        "ix_financial_transactions_user_card_date",
        "financial_transactions",
        ["user_id", "card_id", "transaction_date"],
    )
    op.create_index("ix_account_movements_account_id_id", "account_movements", ["account_id", "id"])
    op.create_index("ix_card_movements_card_currency", "card_movements", ["card_id", "currency"])
    op.create_index("ix_credit_purchases_card_status_date", "credit_purchases", ["card_id", "status", "purchase_date"])
    op.create_index("ix_card_payments_card_date", "card_payments", ["card_id", "payment_date"])
    op.create_index("ix_budgets_user_archived_dates", "budgets", ["user_id", "is_archived", "start_date", "end_date"])
    op.create_index("ix_alerts_user_created", "alerts", ["user_id", "created_at"])
    op.create_index("ix_loan_movements_loan_id_id", "loan_movements", ["loan_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_loan_movements_loan_id_id", table_name="loan_movements")
    op.drop_index("ix_alerts_user_created", table_name="alerts")
    op.drop_index("ix_budgets_user_archived_dates", table_name="budgets")
    op.drop_index("ix_card_payments_card_date", table_name="card_payments")
    op.drop_index("ix_credit_purchases_card_status_date", table_name="credit_purchases")
    op.drop_index("ix_card_movements_card_currency", table_name="card_movements")
    op.drop_index("ix_account_movements_account_id_id", table_name="account_movements")
    op.drop_index("ix_financial_transactions_user_card_date", table_name="financial_transactions")
    op.drop_index("ix_financial_transactions_user_category_date", table_name="financial_transactions")
    op.drop_index("ix_financial_transactions_user_account_date", table_name="financial_transactions")
    op.drop_index("ix_financial_transactions_user_status_date", table_name="financial_transactions")

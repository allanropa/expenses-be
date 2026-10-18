"""Create accounts, categories, ledger operations and transactions."""

from alembic import op
import sqlalchemy as sa

revision = "0002_ledger"
down_revision = "0001_foundations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "name"),
    )
    op.create_index("ix_categories_user_id", "categories", ["user_id"])

    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("account_type", sa.String(length=16), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("opening_balance", sa.Numeric(20, 4), nullable=False),
        sa.Column("opening_balance_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "name"),
    )
    op.create_index("ix_accounts_user_id", "accounts", ["user_id"])

    op.create_table(
        "financial_operations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("operation_type", sa.String(length=24), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reverses_operation_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reverses_operation_id"], ["financial_operations.id"]),
        sa.UniqueConstraint("user_id", "idempotency_key"),
    )
    op.create_index("ix_financial_operations_user_id", "financial_operations", ["user_id"])

    op.create_table(
        "account_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("operation_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.ForeignKeyConstraint(["operation_id"], ["financial_operations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_account_movements_operation_id", "account_movements", ["operation_id"])
    op.create_index("ix_account_movements_account_id", "account_movements", ["account_id"])

    op.create_table(
        "financial_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("operation_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("transaction_type", sa.String(length=8), nullable=False),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("replaced_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["operation_id"], ["financial_operations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["replaced_by_id"], ["financial_transactions.id"]),
        sa.UniqueConstraint("operation_id"),
    )
    op.create_index("ix_financial_transactions_user_id", "financial_transactions", ["user_id"])
    op.create_index("ix_financial_transactions_transaction_date", "financial_transactions", ["transaction_date"])
    op.create_index("ix_financial_transactions_account_id", "financial_transactions", ["account_id"])
    op.create_index("ix_financial_transactions_category_id", "financial_transactions", ["category_id"])
    op.create_index("ix_financial_transactions_status", "financial_transactions", ["status"])

    op.create_table(
        "transfers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("operation_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source_account_id", sa.Integer(), nullable=False),
        sa.Column("destination_account_id", sa.Integer(), nullable=False),
        sa.Column("source_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("source_currency", sa.String(length=3), nullable=False),
        sa.Column("destination_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("destination_currency", sa.String(length=3), nullable=False),
        sa.Column("transfer_date", sa.Date(), nullable=False),
        sa.Column("exchange_rate", sa.Numeric(20, 10), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["operation_id"], ["financial_operations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["destination_account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("operation_id"),
    )
    op.create_index("ix_transfers_user_id", "transfers", ["user_id"])
    op.create_index("ix_transfers_transfer_date", "transfers", ["transfer_date"])


def downgrade() -> None:
    op.drop_index("ix_transfers_transfer_date", table_name="transfers")
    op.drop_index("ix_transfers_user_id", table_name="transfers")
    op.drop_table("transfers")
    op.drop_index("ix_financial_transactions_status", table_name="financial_transactions")
    op.drop_index("ix_financial_transactions_category_id", table_name="financial_transactions")
    op.drop_index("ix_financial_transactions_account_id", table_name="financial_transactions")
    op.drop_index("ix_financial_transactions_transaction_date", table_name="financial_transactions")
    op.drop_index("ix_financial_transactions_user_id", table_name="financial_transactions")
    op.drop_table("financial_transactions")
    op.drop_index("ix_account_movements_account_id", table_name="account_movements")
    op.drop_index("ix_account_movements_operation_id", table_name="account_movements")
    op.drop_table("account_movements")
    op.drop_index("ix_financial_operations_user_id", table_name="financial_operations")
    op.drop_table("financial_operations")
    op.drop_index("ix_accounts_user_id", table_name="accounts")
    op.drop_table("accounts")
    op.drop_index("ix_categories_user_id", table_name="categories")
    op.drop_table("categories")

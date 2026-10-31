"""Add recurring payments and recurring transaction markers."""

from alembic import op
import sqlalchemy as sa


revision = "0013_recurring_payments"
down_revision = "0012_budget_summary_flag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recurring_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("transaction_type", sa.String(length=8), nullable=False),
        sa.Column("source_account_id", sa.Integer(), nullable=True),
        sa.Column("destination_account_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("frequency", sa.String(length=8), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=True),
        sa.Column("day_of_month", sa.Integer(), nullable=True),
        sa.Column("month", sa.Integer(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("last_processed_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["destination_account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recurring_payments_user_id", "recurring_payments", ["user_id"])
    op.create_index("ix_recurring_payments_is_active", "recurring_payments", ["is_active"])
    op.add_column("financial_transactions", sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_financial_transactions_is_recurring", "financial_transactions", ["is_recurring"])
    op.alter_column("financial_transactions", "is_recurring", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_financial_transactions_is_recurring", table_name="financial_transactions")
    op.drop_column("financial_transactions", "is_recurring")
    op.drop_index("ix_recurring_payments_is_active", table_name="recurring_payments")
    op.drop_index("ix_recurring_payments_user_id", table_name="recurring_payments")
    op.drop_table("recurring_payments")

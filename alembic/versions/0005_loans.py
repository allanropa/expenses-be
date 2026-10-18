"""Create received loans and amortization schedules."""

from alembic import op
import sqlalchemy as sa

revision = "0005_loans"
down_revision = "0004_budgets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "loans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("operation_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source_account_id", sa.Integer(), nullable=True),
        sa.Column("interest_category_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("principal_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("annual_effective_rate", sa.Numeric(12, 8), nullable=False),
        sa.Column("monthly_rate", sa.Numeric(12, 10), nullable=False),
        sa.Column("term_months", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("first_payment_date", sa.Date(), nullable=False),
        sa.Column("record_as_income", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["operation_id"], ["financial_operations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["interest_category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("operation_id"),
    )
    op.create_index("ix_loans_user_id", "loans", ["user_id"])

    op.create_table(
        "loan_installments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("loan_id", sa.Integer(), nullable=False),
        sa.Column("installment_number", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("principal_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("interest_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("total_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["loan_id"], ["loans.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_loan_installments_loan_id", "loan_installments", ["loan_id"])
    op.create_index("ix_loan_installments_due_date", "loan_installments", ["due_date"])

    op.create_table(
        "loan_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("operation_id", sa.Integer(), nullable=False),
        sa.Column("loan_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("movement_type", sa.String(length=24), nullable=False),
        sa.ForeignKeyConstraint(["operation_id"], ["financial_operations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["loan_id"], ["loans.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_loan_movements_operation_id", "loan_movements", ["operation_id"])
    op.create_index("ix_loan_movements_loan_id", "loan_movements", ["loan_id"])

    op.create_table(
        "loan_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("operation_id", sa.Integer(), nullable=False),
        sa.Column("loan_id", sa.Integer(), nullable=False),
        sa.Column("source_account_id", sa.Integer(), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("scheduled_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("principal_paid", sa.Numeric(20, 4), nullable=False),
        sa.Column("interest_paid", sa.Numeric(20, 4), nullable=False),
        sa.Column("extra_principal", sa.Numeric(20, 4), nullable=False),
        sa.Column("total_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["operation_id"], ["financial_operations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["loan_id"], ["loans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("operation_id"),
    )
    op.create_index("ix_loan_payments_loan_id", "loan_payments", ["loan_id"])


def downgrade() -> None:
    op.drop_index("ix_loan_payments_loan_id", table_name="loan_payments")
    op.drop_table("loan_payments")
    op.drop_index("ix_loan_movements_loan_id", table_name="loan_movements")
    op.drop_index("ix_loan_movements_operation_id", table_name="loan_movements")
    op.drop_table("loan_movements")
    op.drop_index("ix_loan_installments_due_date", table_name="loan_installments")
    op.drop_index("ix_loan_installments_loan_id", table_name="loan_installments")
    op.drop_table("loan_installments")
    op.drop_index("ix_loans_user_id", table_name="loans")
    op.drop_table("loans")

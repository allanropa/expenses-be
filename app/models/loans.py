from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class Loan(Base):
    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_id: Mapped[int] = mapped_column(ForeignKey("financial_operations.id", ondelete="RESTRICT"), nullable=False, unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True)
    interest_category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    principal_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    annual_effective_rate: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    monthly_rate: Mapped[Decimal] = mapped_column(Numeric(12, 10), nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    first_payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    record_as_income: Mapped[bool] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class LoanInstallment(Base):
    __tablename__ = "loan_installments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.id", ondelete="CASCADE"), nullable=False, index=True)
    installment_number: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    principal_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    interest_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")


class LoanMovement(Base):
    __tablename__ = "loan_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_id: Mapped[int] = mapped_column(ForeignKey("financial_operations.id", ondelete="CASCADE"), nullable=False, index=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.id", ondelete="RESTRICT"), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    movement_type: Mapped[str] = mapped_column(String(24), nullable=False)


class LoanPayment(Base):
    __tablename__ = "loan_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_id: Mapped[int] = mapped_column(ForeignKey("financial_operations.id", ondelete="RESTRICT"), nullable=False, unique=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    scheduled_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    principal_paid: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    interest_paid: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    extra_principal: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class CreditCard(Base):
    __tablename__ = "credit_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    issuing_bank: Mapped[str | None] = mapped_column(String(120), nullable=True)
    statement_closing_day: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class CardCurrency(Base):
    __tablename__ = "card_currencies"
    __table_args__ = (UniqueConstraint("card_id", "currency"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("credit_cards.id", ondelete="CASCADE"), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    credit_limit: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)


class InterestRateConfiguration(Base):
    __tablename__ = "interest_rate_configurations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("credit_cards.id", ondelete="CASCADE"), nullable=False, index=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    monthly_rate: Mapped[Decimal] = mapped_column(Numeric(20, 12), nullable=False)
    rate_type: Mapped[str] = mapped_column(String(16), nullable=False, default="fixed")
    periodicity: Mapped[str] = mapped_column(String(16), nullable=False, default="monthly")
    calculation_method: Mapped[str] = mapped_column(String(16), nullable=False, default="flat")
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)


class CreditPurchase(Base):
    __tablename__ = "credit_purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_id: Mapped[int] = mapped_column(ForeignKey("financial_operations.id", ondelete="RESTRICT"), nullable=False, unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("credit_cards.id", ondelete="RESTRICT"), nullable=False, index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    installments_count: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_interest_rate: Mapped[Decimal] = mapped_column(Numeric(20, 12), nullable=False)
    financing_method: Mapped[str] = mapped_column(String(16), nullable=False, default="flat")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Installment(Base):
    __tablename__ = "installments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_id: Mapped[int] = mapped_column(ForeignKey("credit_purchases.id", ondelete="CASCADE"), nullable=False, index=True)
    installment_number: Mapped[int] = mapped_column(Integer, nullable=False)
    statement_closing_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    principal_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    estimated_interest: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    estimated_total: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")


class CardCharge(Base):
    __tablename__ = "card_charges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("credit_cards.id", ondelete="RESTRICT"), nullable=False, index=True)
    purchase_id: Mapped[int | None] = mapped_column(ForeignKey("credit_purchases.id", ondelete="RESTRICT"), nullable=True)
    charge_type: Mapped[str] = mapped_column(String(24), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    charge_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    is_estimated: Mapped[bool] = mapped_column(nullable=False, default=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class CardPayment(Base):
    __tablename__ = "card_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_id: Mapped[int] = mapped_column(ForeignKey("financial_operations.id", ondelete="RESTRICT"), nullable=False, unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("credit_cards.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True)
    obligation_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    obligation_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    source_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    source_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(20, 10), nullable=True)
    fee_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    fee_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class CardPaymentAllocation(Base):
    __tablename__ = "card_payment_allocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("card_payments.id", ondelete="CASCADE"), nullable=False, index=True)
    charge_id: Mapped[int] = mapped_column(ForeignKey("card_charges.id", ondelete="RESTRICT"), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)


class CardMovement(Base):
    __tablename__ = "card_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_id: Mapped[int] = mapped_column(ForeignKey("financial_operations.id", ondelete="CASCADE"), nullable=False, index=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("credit_cards.id", ondelete="RESTRICT"), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

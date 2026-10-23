from __future__ import annotations

from datetime import date
from typing import Literal
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.domain.money import normalize_currency


class LoanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    principal_amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    annual_effective_rate: Decimal = Field(ge=0)
    term_months: int = Field(ge=1, le=360)
    start_date: date
    first_payment_date: date
    source_account_id: int | None = None
    record_as_income: bool = False

    @field_validator("currency")
    @classmethod
    def currency_code(cls, value: str) -> str:
        return normalize_currency(value)


class LoanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    annual_effective_rate: Decimal | None = Field(default=None, ge=0)
    term_months: int | None = Field(default=None, ge=1, le=360)
    start_date: date | None = None
    first_payment_date: date | None = None
    record_as_income: bool | None = None


class LoanExtraCharge(BaseModel):
    amount: Decimal = Field(gt=0)
    category_id: int
    description: str = Field(min_length=1, max_length=2000)


class LoanPaymentCreate(BaseModel):
    source_account_id: int
    payment_date: date
    scheduled_amount: Decimal | None = Field(default=None, gt=0)
    interest_paid: Decimal | None = Field(default=None, ge=0)
    extra_principal: Decimal = Field(default=Decimal("0"), ge=0)
    recalculate_installments: bool = False
    is_abono: bool = False
    notes: str | None = Field(default=None, max_length=2000)
    extra_charges: list[LoanExtraCharge] | None = None


class LoanInstallmentResponse(BaseModel):
    id: int
    installment_number: int
    due_date: date
    principal_amount: Decimal
    interest_amount: Decimal
    total_amount: Decimal
    status: str


class LoanResponse(BaseModel):
    id: int
    name: str
    principal_amount: Decimal
    outstanding_principal: Decimal
    currency: str
    annual_effective_rate: Decimal
    monthly_rate: Decimal
    term_months: int
    start_date: date
    first_payment_date: date
    record_as_income: bool
    status: str
    installments: list[LoanInstallmentResponse] = []


class LoanPaymentViewResponse(BaseModel):
    id: int
    status: Literal["paid", "pending"]
    kind: Literal["payment", "abono"]
    date: date
    amount: Decimal
    principal_amount: Decimal
    interest_amount: Decimal
    extra_principal: Decimal
    notes: str | None = None


class LoanPaymentResponse(BaseModel):
    id: int
    loan_id: int
    payment_date: date
    scheduled_amount: Decimal
    principal_paid: Decimal
    interest_paid: Decimal
    extra_principal: Decimal
    total_amount: Decimal
    notes: str | None

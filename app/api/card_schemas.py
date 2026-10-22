from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.domain.money import normalize_currency


class CardCurrencyCreate(BaseModel):
    currency: str = Field(min_length=3, max_length=3)
    credit_limit: Decimal | None = Field(default=None, gt=0)

    @field_validator("currency")
    @classmethod
    def currency_code(cls, value: str) -> str:
        return normalize_currency(value)


class CardCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    issuing_bank: str | None = Field(default=None, max_length=120)
    statement_closing_day: int = Field(ge=1, le=31)
    currencies: list[CardCurrencyCreate] = Field(min_length=1, max_length=2)
    description: str | None = Field(default=None, max_length=2000)


class CardUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    issuing_bank: str | None = Field(default=None, max_length=120)
    statement_closing_day: int | None = Field(default=None, ge=1, le=31)
    description: str | None = Field(default=None, max_length=2000)
    credit_limits: dict[str, Decimal | None] | None = None

    @field_validator("credit_limits")
    @classmethod
    def validate_credit_limits(cls, value: dict[str, Decimal | None] | None):
        if value is None:
            return value
        normalized = {}
        for currency, limit in value.items():
            normalized_currency = normalize_currency(currency)
            if limit is not None and limit <= 0:
                raise ValueError("El límite de crédito debe ser mayor que cero")
            normalized[normalized_currency] = limit
        return normalized


class CardCurrencyResponse(BaseModel):
    currency: str
    credit_limit: Decimal | None
    outstanding_debt: Decimal
    available_credit: Decimal | None


class InterestConfigCreate(BaseModel):
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    monthly_rate: Decimal = Field(ge=0)
    rate_type: str = "fixed"
    periodicity: str = "monthly"
    calculation_method: str = "flat"
    effective_from: date
    effective_to: date | None = None

    @field_validator("currency")
    @classmethod
    def currency_code(cls, value: str | None) -> str | None:
        return normalize_currency(value) if value else None


class InterestConfigResponse(InterestConfigCreate):
    id: int


class CardResponse(BaseModel):
    id: int
    name: str
    issuing_bank: str | None
    statement_closing_day: int
    description: str | None
    is_archived: bool
    currencies: list[CardCurrencyResponse]
    interest_rates: list[InterestConfigResponse]


class PurchaseCreate(BaseModel):
    card_id: int
    category_id: int
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    purchase_date: date
    installments_count: int = Field(ge=1, le=120)
    description: str = Field(min_length=1, max_length=2000)

    @field_validator("currency")
    @classmethod
    def currency_code(cls, value: str) -> str:
        return normalize_currency(value)


class InstallmentResponse(BaseModel):
    id: int
    installment_number: int
    statement_closing_date: date
    principal_amount: Decimal
    estimated_interest: Decimal
    estimated_total: Decimal
    status: str


class PurchaseResponse(BaseModel):
    id: int
    card_id: int
    category_id: int
    amount: Decimal
    currency: str
    purchase_date: date
    installments_count: int
    monthly_interest_rate: Decimal
    financing_method: str
    status: str
    description: str
    installments: list[InstallmentResponse]


class CardChargeCreate(BaseModel):
    charge_type: Literal["interest", "fee", "adjustment"]
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    charge_date: date
    category_id: int
    description: str = Field(min_length=1, max_length=2000)

    @field_validator("currency")
    @classmethod
    def currency_code(cls, value: str) -> str:
        return normalize_currency(value)


class PaymentExtraCharge(BaseModel):
    amount: Decimal = Field(gt=0)
    category_id: int
    description: str = Field(min_length=1, max_length=2000)


class PaymentCreate(BaseModel):
    card_id: int
    source_account_id: int | None = None
    obligation_amount: Decimal = Field(gt=0)
    obligation_currency: str = Field(min_length=3, max_length=3)
    source_amount: Decimal | None = Field(default=None, gt=0)
    exchange_rate: Decimal | None = Field(default=None, gt=0)
    fee_amount: Decimal | None = Field(default=None, gt=0)
    payment_date: date
    notes: str | None = Field(default=None, max_length=2000)
    extra_charges: list[PaymentExtraCharge] | None = None

    @field_validator("obligation_currency")
    @classmethod
    def currency_code(cls, value: str) -> str:
        return normalize_currency(value)


class PaymentResponse(BaseModel):
    id: int
    card_id: int
    source_account_id: int | None
    obligation_amount: Decimal
    obligation_currency: str
    source_amount: Decimal | None
    source_currency: str | None
    exchange_rate: Decimal | None
    fee_amount: Decimal | None
    payment_date: date
    notes: str | None


class CardBalanceAdjustmentCreate(BaseModel):
    currency: str = Field(min_length=3, max_length=3)
    target_debt: Decimal = Field(ge=0)
    adjustment_date: date
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("currency")
    @classmethod
    def currency_code(cls, value: str) -> str:
        return normalize_currency(value)

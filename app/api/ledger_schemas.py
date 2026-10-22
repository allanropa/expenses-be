from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.money import normalize_currency


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["income", "expense", "both"] = "both"

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("El nombre de la categoría no puede estar vacío")
        return name


class CategoryResponse(CategoryCreate):
    id: int
    is_archived: bool


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    account_type: Literal["savings", "checking", "cash", "other"]
    currency: str = Field(min_length=3, max_length=3)
    opening_balance: Decimal = Decimal("0")
    opening_balance_date: date
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return normalize_currency(value)


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class BalanceAdjustmentCreate(BaseModel):
    target_balance: Decimal
    adjustment_date: date
    description: str | None = Field(default=None, max_length=2000)


class AccountResponse(BaseModel):
    id: int
    name: str
    account_type: str
    currency: str
    opening_balance: Decimal
    opening_balance_date: date
    current_balance: Decimal
    description: str | None
    is_archived: bool


class AccountMovementResponse(BaseModel):
    id: int
    operation_id: int
    operation_type: str
    effective_date: date
    amount: Decimal = Field(gt=0)
    currency: str
    description: str | None


class TransactionCreate(BaseModel):
    transaction_type: Literal["income", "expense"]
    amount: Decimal
    currency: str = Field(min_length=3, max_length=3)
    transaction_date: date
    account_id: int
    category_id: int
    description: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return normalize_currency(value)


class TransactionUpdate(BaseModel):
    transaction_type: Literal["income", "expense"] | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    transaction_date: date | None = None
    account_id: int | None = None
    category_id: int | None = None
    description: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        return normalize_currency(value) if value else value


class TransactionResponse(BaseModel):
    id: int
    transaction_type: str
    amount: Decimal
    currency: str
    original_amount: Decimal | None
    original_currency: str | None
    transaction_date: date
    account_id: int | None
    card_id: int | None
    credit_purchase_id: int | None
    category_id: int
    payment_method: str
    description: str | None
    notes: str | None
    status: str


class TransferCreate(BaseModel):
    source_account_id: int
    destination_account_id: int
    source_amount: Decimal = Field(gt=0)
    destination_amount: Decimal | None = Field(default=None, gt=0)
    transfer_date: date
    exchange_rate: Decimal | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_accounts_and_conversion(self):
        if self.source_account_id == self.destination_account_id:
            raise ValueError("Las cuentas de origen y destino deben ser diferentes")
        return self


class TransferResponse(BaseModel):
    id: int
    source_account_id: int
    destination_account_id: int
    source_amount: Decimal
    source_currency: str
    destination_amount: Decimal
    destination_currency: str
    transfer_date: date
    exchange_rate: Decimal | None
    description: str | None

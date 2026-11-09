from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


Frequency = Literal["weekly", "monthly", "yearly"]
TransactionKind = Literal["income", "expense"]


class RecurringPaymentCreate(BaseModel):
    transaction_type: TransactionKind
    source_account_id: int | None = None
    destination_account_id: int | None = None
    card_id: int | None = None
    currency: str | None = None
    amount: Decimal = Field(gt=0)
    category_id: int
    description: str | None = Field(default=None, max_length=2000)
    frequency: Frequency
    weekday: int | None = Field(default=None, ge=0, le=6)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    month: int | None = Field(default=None, ge=1, le=12)
    start_date: date
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_schedule(self):
        if self.transaction_type == "expense" and ((self.source_account_id is None) == (self.card_id is None)):
            raise ValueError("Un gasto recurrente requiere una cuenta o una tarjeta")
        if self.card_id is not None and (self.transaction_type != "expense" or not self.currency or self.destination_account_id is not None):
            raise ValueError("La tarjeta requiere un gasto y una moneda válida")
        if self.transaction_type == "income" and self.destination_account_id is None:
            raise ValueError("Un ingreso recurrente requiere una cuenta destino")
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("La fecha final no puede ser anterior a la fecha inicial")
        if self.frequency == "weekly" and self.weekday is None:
            raise ValueError("La frecuencia semanal requiere un día de la semana")
        if self.frequency == "monthly" and self.day_of_month is None:
            raise ValueError("La frecuencia mensual requiere un día del mes")
        if self.frequency == "yearly" and (self.month is None or self.day_of_month is None):
            raise ValueError("La frecuencia anual requiere mes y día")
        return self


class RecurringPaymentUpdate(RecurringPaymentCreate):
    is_active: bool = True


class RecurringPaymentResponse(BaseModel):
    id: int
    transaction_type: str
    source_account_id: int | None
    destination_account_id: int | None
    card_id: int | None
    amount: Decimal
    currency: str
    category_id: int
    description: str | None
    frequency: str
    weekday: int | None
    day_of_month: int | None
    month: int | None
    start_date: date
    end_date: date | None
    is_active: bool

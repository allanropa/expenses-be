from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.domain.money import normalize_currency
from app.domain.enums import BudgetPeriod, BudgetScope, BudgetType, SpendingType


class BudgetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    budget_type: BudgetType
    target_amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    period_type: BudgetPeriod = BudgetPeriod.MONTHLY
    start_date: date | None = None
    end_date: date | None = None
    scope: BudgetScope = BudgetScope.GENERAL
    spending_type: SpendingType
    category_id: int | None = None
    category_ids: list[int] | None = None
    account_id: int | None = None
    account_ids: list[int] | None = None
    card_id: int | None = None
    card_ids: list[int] | None = None
    eligible_weekdays: list[int] | None = None
    alert_threshold: Decimal = Field(default=Decimal("0.8"), ge=0, le=1)
    show_in_summary: bool = True

    @model_validator(mode="after")
    def validate_budget(self):
        if self.period_type == BudgetPeriod.CUSTOM and (self.start_date is None or self.end_date is None):
            raise ValueError("Un presupuesto personalizado requiere fecha de inicio y fin")
        if self.start_date is not None and self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("El final del presupuesto no puede preceder al inicio")
        if self.scope == BudgetScope.CATEGORY and not (self.category_ids or self.category_id):
            raise ValueError("Un presupuesto de categoría requiere una categoría")
        if self.scope == BudgetScope.GENERAL and any(value is not None for value in (self.account_id, self.card_id)):
            raise ValueError("Un presupuesto general no puede tener un objetivo")
        if self.eligible_weekdays is not None and any(day not in range(7) for day in self.eligible_weekdays):
            raise ValueError("Los días elegibles deben estar entre 0 y 6")
        self.currency = normalize_currency(self.currency)
        return self


class BudgetResponse(BaseModel):
    id: int
    name: str
    budget_type: str
    target_amount: Decimal
    currency: str
    period_type: str
    start_date: date
    end_date: date
    scope: str
    spending_type: str
    category_id: int | None
    category_ids: list[int] | None
    account_id: int | None
    account_ids: list[int] | None
    card_id: int | None
    card_ids: list[int] | None
    eligible_weekdays: list[int] | None
    alert_threshold: Decimal
    is_archived: bool
    show_in_summary: bool


class BudgetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    target_amount: Decimal | None = Field(default=None, gt=0)
    budget_type: BudgetType | None = None
    period_type: BudgetPeriod | None = None
    start_date: date | None = None
    end_date: date | None = None
    scope: BudgetScope | None = None
    spending_type: SpendingType | None = None
    category_id: int | None = None
    category_ids: list[int] | None = None
    account_id: int | None = None
    account_ids: list[int] | None = None
    card_id: int | None = None
    card_ids: list[int] | None = None
    eligible_weekdays: list[int] | None = None
    alert_threshold: Decimal | None = Field(default=None, ge=0, le=1)
    show_in_summary: bool | None = None


class BudgetSummary(BaseModel):
    budget_id: int
    currency: str
    period_start: date
    period_end: date
    accumulated_budget: Decimal
    actual_spending: Decimal
    balance: Decimal
    percentage_used: Decimal
    excess: Decimal
    equivalent_budget_days: Decimal | None
    daily_history: list[dict]


class AlertResponse(BaseModel):
    id: int
    alert_type: str
    message: str
    read_at: str | None

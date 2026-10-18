from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from app.domain.money import normalize_amount, normalize_currency


@dataclass(frozen=True)
class InstallmentEstimate:
    number: int
    statement_closing_date: date
    principal: Decimal
    interest: Decimal
    total: Decimal


def add_months(value: date, months: int, day: int | None = None) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(month_index, 12)
    month = month_index + 1
    target_day = day or value.day
    return date(year, month, min(target_day, monthrange(year, month)[1]))


def closing_date_for_month(year: int, month: int, closing_day: int) -> date:
    return date(year, month, min(closing_day, monthrange(year, month)[1]))


def first_statement_closing_date(purchase_date: date, closing_day: int) -> date:
    current = closing_date_for_month(purchase_date.year, purchase_date.month, closing_day)
    if purchase_date.day < current.day:
        return current
    return add_months(current, 1, closing_day)


def estimate_installments(
    amount: Decimal,
    currency: str,
    installment_count: int,
    monthly_rate: Decimal,
    purchase_date: date,
    closing_day: int,
) -> list[InstallmentEstimate]:
    currency = normalize_currency(currency)
    if installment_count < 1:
        raise ValueError("Debe existir al menos una cuota")
    if monthly_rate < 0:
        raise ValueError("La tasa no puede ser negativa")
    amount = normalize_amount(amount, currency)
    quantum = Decimal(1).scaleb(-{ "COP": 0, "USD": 2 }[currency])
    principal_share = (amount / installment_count).quantize(quantum, rounding=ROUND_HALF_UP)
    interest_share = Decimal("0") if installment_count == 1 else (amount * monthly_rate).quantize(quantum, rounding=ROUND_HALF_UP)
    first_closing = first_statement_closing_date(purchase_date, closing_day)
    result: list[InstallmentEstimate] = []
    allocated_principal = Decimal("0")
    for number in range(1, installment_count + 1):
        principal = amount - allocated_principal if number == installment_count else principal_share
        allocated_principal += principal
        result.append(
            InstallmentEstimate(
                number=number,
                statement_closing_date=add_months(first_closing, number - 1, closing_day),
                principal=principal,
                interest=interest_share,
                total=principal + interest_share,
            )
        )
    return result

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, localcontext


@dataclass(frozen=True)
class LoanInstallmentEstimate:
    number: int
    due_date: date
    principal: Decimal
    interest: Decimal
    total: Decimal


def add_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(index, 12)
    month = month_index + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def monthly_rate_from_effective_annual(annual_rate: Decimal) -> Decimal:
    if annual_rate < 0:
        raise ValueError("La tasa efectiva anual no puede ser negativa")
    with localcontext() as context:
        context.prec = 40
        return ((Decimal(1) + annual_rate).ln() / Decimal(12)).exp() - Decimal(1)


def fixed_monthly_payment(principal: Decimal, monthly_rate: Decimal, periods: int, currency: str) -> Decimal:
    if periods < 1:
        raise ValueError("El plazo debe tener al menos una cuota")
    quantum = Decimal(1) if currency == "COP" else Decimal("0.01")
    if monthly_rate == 0:
        return (principal / periods).quantize(quantum, rounding=ROUND_HALF_UP)
    factor = (Decimal(1) + monthly_rate) ** periods
    payment = principal * monthly_rate * factor / (factor - Decimal(1))
    return payment.quantize(quantum, rounding=ROUND_HALF_UP)


def amortization_schedule(
    principal: Decimal,
    currency: str,
    annual_effective_rate: Decimal,
    term_months: int,
    first_payment_date: date,
) -> tuple[Decimal, list[LoanInstallmentEstimate]]:
    monthly_rate = monthly_rate_from_effective_annual(annual_effective_rate)
    payment = fixed_monthly_payment(principal, monthly_rate, term_months, currency)
    quantum = Decimal(1) if currency == "COP" else Decimal("0.01")
    balance = principal
    schedule: list[LoanInstallmentEstimate] = []
    for number in range(1, term_months + 1):
        interest = (balance * monthly_rate).quantize(quantum, rounding=ROUND_HALF_UP)
        principal_part = balance if number == term_months else min(balance, payment - interest)
        principal_part = principal_part.quantize(quantum, rounding=ROUND_HALF_UP)
        total = (principal_part + interest).quantize(quantum, rounding=ROUND_HALF_UP)
        balance = (balance - principal_part).quantize(quantum, rounding=ROUND_HALF_UP)
        schedule.append(LoanInstallmentEstimate(number, add_months(first_payment_date, number - 1), principal_part, interest, total))
    return monthly_rate, schedule


def schedule_with_payment(
    principal: Decimal,
    monthly_rate: Decimal,
    payment: Decimal,
    currency: str,
    first_payment_date: date,
    first_installment_number: int,
) -> list[LoanInstallmentEstimate]:
    """Build a schedule keeping a fixed payment and shortening the term."""
    quantum = Decimal(1) if currency == "COP" else Decimal("0.01")
    balance = principal.quantize(quantum, rounding=ROUND_HALF_UP)
    schedule: list[LoanInstallmentEstimate] = []
    number = first_installment_number
    while balance > 0:
        interest = (balance * monthly_rate).quantize(quantum, rounding=ROUND_HALF_UP)
        principal_part = min(balance, payment - interest).quantize(quantum, rounding=ROUND_HALF_UP)
        if principal_part <= 0:
            raise ValueError("El monto de la cuota no cubre los intereses")
        total = (principal_part + interest).quantize(quantum, rounding=ROUND_HALF_UP)
        balance = (balance - principal_part).quantize(quantum, rounding=ROUND_HALF_UP)
        schedule.append(
            LoanInstallmentEstimate(
                number,
                add_months(first_payment_date, number - first_installment_number),
                principal_part,
                interest,
                total,
            )
        )
        number += 1
        if len(schedule) > 360:
            raise ValueError("No se pudo recalcular el plan de cuotas")
    return schedule

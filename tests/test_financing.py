from datetime import date
from decimal import Decimal

from app.domain.financing import estimate_installments, first_statement_closing_date


def test_flat_interest_starts_on_first_multi_installment_and_reconciles():
    installments = estimate_installments(
        Decimal("1000000"),
        "COP",
        5,
        Decimal("0.02"),
        date(2026, 1, 10),
        15,
    )
    assert installments[0].interest == Decimal("20000")
    assert installments[0].total == Decimal("220000")
    assert sum(item.principal for item in installments) == Decimal("1000000")
    assert sum(item.total for item in installments) == Decimal("1100000")


def test_single_installment_is_interest_free_and_cutoff_day_goes_next_cycle():
    installments = estimate_installments(
        Decimal("100.00"),
        "USD",
        1,
        Decimal("0.02"),
        date(2026, 1, 15),
        15,
    )
    assert installments[0].interest == Decimal("0.00")
    assert installments[0].statement_closing_date == date(2026, 2, 15)


def test_short_month_closing_day_is_clamped():
    assert first_statement_closing_date(date(2026, 2, 1), 31) == date(2026, 2, 28)
    assert first_statement_closing_date(date(2026, 2, 28), 31) == date(2026, 3, 31)

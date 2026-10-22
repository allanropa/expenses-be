from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.budget_schemas import BudgetCreate
from app.domain.money import normalize_amount
from app.models.budgets import Alert, Budget
from app.models.ledger import FinancialTransaction
from app.domain.enums import BudgetPeriod, BudgetScope, BudgetType, TransactionStatus, TransactionType

_FAR_PAST = date(2000, 1, 1)
_FAR_FUTURE = date(2099, 12, 31)


def eligible_days(start: date, end: date, weekdays: list[int] | None) -> int:
    count = 0
    current = start
    while current <= end:
        if weekdays is None or current.weekday() in weekdays:
            count += 1
        current += timedelta(days=1)
    return count


def budget_transactions(db: Session, budget: Budget, start: date, end: date, pool=None):
    if pool is None:
        pool = db.query(FinancialTransaction).filter(
            FinancialTransaction.user_id == budget.user_id,
            FinancialTransaction.transaction_type == TransactionType.EXPENSE,
            FinancialTransaction.status == TransactionStatus.ACTIVE,
            FinancialTransaction.payment_method == budget.spending_type,
            FinancialTransaction.currency == budget.currency,
            FinancialTransaction.transaction_date >= start,
            FinancialTransaction.transaction_date <= end,
        ).all()
    transactions = [item for item in pool if (
        item.user_id == budget.user_id
        and item.transaction_type == TransactionType.EXPENSE
        and item.status == TransactionStatus.ACTIVE
        and item.payment_method == budget.spending_type
        and item.currency == budget.currency
        and start <= item.transaction_date <= end
        and (budget.scope != BudgetScope.CATEGORY or item.category_id == budget.category_id)
        and (budget.scope != BudgetScope.ACCOUNT or item.account_id == budget.account_id)
        and (budget.scope != BudgetScope.CARD or item.card_id == budget.card_id)
    )]
    return sorted(transactions, key=lambda item: (item.transaction_date, item.id))


def _is_recurring(budget: Budget) -> bool:
    return budget.period_type != BudgetPeriod.CUSTOM


def summary_period(budget: Budget, start: date | None = None, end: date | None = None) -> tuple[date, date]:
    today = date.today()
    if budget.period_type == BudgetPeriod.DAILY:
        period_start, period_end = start or today, end or today
    elif budget.period_type == BudgetPeriod.MONTHLY:
        period_start, period_end = start or today.replace(day=1), end or today
    elif budget.period_type == BudgetPeriod.WEEKLY:
        monday = today - timedelta(days=today.weekday())
        period_start, period_end = start or monday, end or monday + timedelta(days=6)
    else:
        period_start, period_end = start or budget.start_date, end or budget.end_date
    if budget.budget_type == BudgetType.MAXIMUM:
        if budget.period_type == BudgetPeriod.MONTHLY:
            period_end = today.replace(day=monthrange(today.year, today.month)[1])
        elif budget.period_type == BudgetPeriod.WEEKLY:
            period_end = today + timedelta(days=6 - today.weekday())
        elif budget.period_type == BudgetPeriod.DAILY:
            period_end = today
    return max(period_start, budget.start_date), min(period_end, budget.end_date)


def calculate_summary(
    db: Session, budget: Budget, start: date | None = None, end: date | None = None, pool=None
):
    period_start, period_end = summary_period(budget, start, end)
    if period_end < period_start:
        raise HTTPException(
            status_code=422, detail="El período consultado no intersecta el presupuesto"
        )
    transactions = budget_transactions(db, budget, period_start, period_end, pool)
    actual = sum((Decimal(item.amount) for item in transactions), Decimal("0"))
    if budget.budget_type == BudgetType.DAILY:
        accumulated = Decimal(budget.target_amount) * eligible_days(
            period_start, period_end, budget.eligible_weekdays
        )
        equivalent_days = abs(accumulated - actual) / Decimal(budget.target_amount)
    else:
        accumulated = Decimal(budget.target_amount)
        equivalent_days = None
    balance = accumulated - actual
    percentage = (actual / accumulated * 100) if accumulated else Decimal("0")
    history: dict[date, dict] = {}
    for transaction in transactions:
        day = history.setdefault(
            transaction.transaction_date, {"amount": Decimal("0"), "transactions": []}
        )
        day["amount"] += Decimal(transaction.amount)
        day["transactions"].append(
            {
                "id": transaction.id,
                "description": transaction.description,
                "amount": transaction.amount,
            }
        )
    return {
        "budget_id": budget.id,
        "currency": budget.currency,
        "period_start": period_start,
        "period_end": period_end,
        "accumulated_budget": normalize_amount(
            accumulated, budget.currency, positive=False
        ),
        "actual_spending": normalize_amount(actual, budget.currency, positive=False),
        "balance": normalize_amount(balance, budget.currency, positive=False),
        "percentage_used": percentage.quantize(Decimal("0.01")),
        "excess": normalize_amount(
            max(-balance, Decimal("0")), budget.currency, positive=False
        ),
        "equivalent_budget_days": (
            equivalent_days.quantize(Decimal("0.01"))
            if equivalent_days is not None
            else None
        ),
        "daily_history": [
            {
                "date": key,
                "amount": normalize_amount(value["amount"], budget.currency),
                "transactions": value["transactions"],
            }
            for key, value in sorted(history.items())
        ],
    }


def create_budget(db: Session, user_id: int, payload: BudgetCreate) -> Budget:
    target = normalize_amount(payload.target_amount, payload.currency)
    data = payload.model_dump(exclude={"target_amount"})
    if data.get("start_date") is None:
        data["start_date"] = _FAR_PAST
    if data.get("end_date") is None:
        data["end_date"] = _FAR_FUTURE
    budget = Budget(user_id=user_id, target_amount=target, **data)
    db.add(budget)
    db.flush()
    return budget


def maybe_alert(db: Session, budget: Budget, summary: dict) -> None:
    if summary["percentage_used"] < Decimal(budget.alert_threshold) * 100:
        return
    dedupe_key = f"budget:{budget.id}:{summary['period_end'].isoformat()}"
    existing = (
        db.query(Alert)
        .filter(Alert.user_id == budget.user_id, Alert.dedupe_key == dedupe_key)
        .one_or_none()
    )
    if existing:
        return
    db.add(
        Alert(
            user_id=budget.user_id,
            budget_id=budget.id,
            alert_type="budget_threshold",
            dedupe_key=dedupe_key,
            message=f"El presupuesto {budget.name} ha utilizado {summary['percentage_used']}%.",
        )
    )

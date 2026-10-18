from calendar import monthrange
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.domain.cards import card_debt
from app.models.budgets import Budget
from app.models.cards import CardCurrency, CreditCard
from app.models.ledger import Account, FinancialTransaction
from app.models.loans import Loan
from app.services.budgets import calculate_summary
from app.services.ledger import account_balance
from app.services.loans import outstanding_principal

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def selected_period(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    if date_from and date_to:
        return date_from, date_to
    today = date.today()
    return date(today.year, today.month, 1), date(today.year, today.month, monthrange(today.year, today.month)[1])


@router.get("")
def dashboard(
    date_from: date | None = None,
    date_to: date | None = None,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    period_start, period_end = selected_period(date_from, date_to)
    transactions = db.query(FinancialTransaction).filter(
        FinancialTransaction.user_id == context.user.id,
        FinancialTransaction.status == "active",
        FinancialTransaction.transaction_date >= period_start,
        FinancialTransaction.transaction_date <= period_end,
    ).all()
    income: dict[str, Decimal] = {}
    expenses: dict[str, Decimal] = {}
    for item in transactions:
        if item.transaction_type == "income":
            income[item.currency] = income.get(item.currency, Decimal("0")) + Decimal(item.amount)
        elif item.transaction_type == "expense":
            expenses[item.currency] = expenses.get(item.currency, Decimal("0")) + Decimal(item.amount)
    accounts = db.query(Account).filter(Account.user_id == context.user.id, Account.is_archived.is_(False)).all()
    cards = db.query(CreditCard).filter(CreditCard.user_id == context.user.id, CreditCard.is_archived.is_(False)).all()
    debt = []
    for card in cards:
        for currency in db.query(CardCurrency).filter(CardCurrency.card_id == card.id).all():
            debt.append({"card_id": card.id, "card_name": card.name, "currency": currency.currency, "amount": card_debt(db, card.id, currency.currency)})
    budgets = []
    for budget in db.query(Budget).filter(Budget.user_id == context.user.id, Budget.is_archived.is_(False)).all():
        if budget.end_date >= period_start and budget.start_date <= period_end:
            if budget.period_type != "custom":
                budgets.append({**calculate_summary(db, budget), "name": budget.name})
            else:
                budgets.append({**calculate_summary(db, budget, period_start, period_end), "name": budget.name})
    loans = []
    for loan in db.query(Loan).filter(Loan.user_id == context.user.id, Loan.status == "active").all():
        loans.append({
            "id": loan.id,
            "name": loan.name,
            "currency": loan.currency,
            "outstanding": outstanding_principal(db, loan.id),
            "monthly_rate": loan.monthly_rate,
            "annual_effective_rate": loan.annual_effective_rate,
        })
    recent = db.query(FinancialTransaction).filter(
        FinancialTransaction.user_id == context.user.id,
        FinancialTransaction.status == "active",
    ).order_by(FinancialTransaction.transaction_date.desc(), FinancialTransaction.id.desc()).limit(20).all()
    account_names = {a.id: a.name for a in accounts}
    card_names = {c.id: c.name for c in cards}
    transaction_list = []
    for item in recent:
        source = account_names.get(item.account_id) if item.account_id else card_names.get(item.card_id, "")
        transaction_list.append({
            "id": item.id,
            "transaction_type": item.transaction_type,
            "amount": item.amount,
            "currency": item.currency,
            "original_amount": item.original_amount,
            "original_currency": item.original_currency,
            "transaction_date": item.transaction_date,
            "payment_method": item.payment_method,
            "description": item.description,
            "category_id": item.category_id,
            "source": source,
        })
    return {
        "period": {"start": period_start, "end": period_end},
        "income_by_currency": income,
        "consumption_by_currency": expenses,
        "difference_by_currency": {currency: income.get(currency, 0) - expenses.get(currency, 0) for currency in set(income) | set(expenses)},
        "accounts": [{"id": account.id, "name": account.name, "currency": account.currency, "balance": account_balance(db, account)} for account in accounts],
        "card_debt": debt,
        "loan_debt": loans,
        "budgets": budgets,
        "recent_transactions": transaction_list,
    }

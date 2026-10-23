from calendar import monthrange
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.models.budgets import Budget
from app.models.cards import CardCurrency, CardMovement, CreditCard
from app.models.ledger import Account, FinancialOperation, FinancialTransaction, Transfer
from app.models.loans import Loan, LoanMovement
from app.services.budgets import calculate_summary, summary_period
from app.services.ledger import account_balance
from app.domain.enums import BudgetPeriod, TransactionStatus, TransactionType

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
        FinancialTransaction.status == TransactionStatus.ACTIVE,
        FinancialTransaction.transaction_date >= period_start,
        FinancialTransaction.transaction_date <= period_end,
    ).all()
    income: dict[str, Decimal] = {}
    expenses: dict[str, Decimal] = {}
    for item in transactions:
        if item.transaction_type == TransactionType.INCOME:
            income[item.currency] = income.get(item.currency, Decimal("0")) + Decimal(item.amount)
        elif item.transaction_type == TransactionType.EXPENSE:
            expenses[item.currency] = expenses.get(item.currency, Decimal("0")) + Decimal(item.amount)
    accounts = db.query(Account).filter(Account.user_id == context.user.id, Account.is_archived.is_(False)).all()
    cards = db.query(CreditCard).filter(CreditCard.user_id == context.user.id, CreditCard.is_archived.is_(False)).all()
    card_ids = [card.id for card in cards]
    currencies = db.query(CardCurrency).filter(CardCurrency.card_id.in_(card_ids)).all() if card_ids else []
    debt_rows = db.query(
        CardCurrency.card_id,
        CardCurrency.currency,
        func.coalesce(func.sum(CardMovement.amount), 0),
    ).outerjoin(
        CardMovement,
        (CardMovement.card_id == CardCurrency.card_id)
        & (CardMovement.currency == CardCurrency.currency),
    ).filter(CardCurrency.card_id.in_(card_ids)).group_by(CardCurrency.card_id, CardCurrency.currency).all() if card_ids else []
    debts = {(row[0], row[1]): row[2] for row in debt_rows}
    debt = [
        {"card_id": card.id, "card_name": card.name, "currency": item.currency, "amount": debts[(card.id, item.currency)]}
        for card in cards
        for item in currencies
        if item.card_id == card.id
    ]
    budgets = []
    budget_items = db.query(Budget).filter(
        Budget.user_id == context.user.id,
        Budget.is_archived.is_(False),
        Budget.show_in_summary.is_(True),
    ).all()
    relevant_budgets = [budget for budget in budget_items if budget.end_date >= period_start and budget.start_date <= period_end]
    ranges = [summary_period(budget, period_start, period_end) for budget in relevant_budgets]
    if ranges:
        budget_transactions = db.query(FinancialTransaction).filter(
            FinancialTransaction.user_id == context.user.id,
            FinancialTransaction.transaction_type == TransactionType.EXPENSE,
            FinancialTransaction.status == TransactionStatus.ACTIVE,
            FinancialTransaction.transaction_date >= min(start for start, _ in ranges),
            FinancialTransaction.transaction_date <= max(end for _, end in ranges),
        ).all()
    else:
        budget_transactions = []
    for budget in relevant_budgets:
        if budget.period_type != BudgetPeriod.CUSTOM:
            budgets.append({**calculate_summary(db, budget, pool=budget_transactions), "name": budget.name})
        else:
            budgets.append({**calculate_summary(db, budget, period_start, period_end, budget_transactions), "name": budget.name})
    loans = []
    active_loans = db.query(Loan).filter(Loan.user_id == context.user.id, Loan.status == TransactionStatus.ACTIVE).all()
    loan_ids = [loan.id for loan in active_loans]
    loan_balances: dict[int, Decimal] = {
        int(row[0]): Decimal(row[1])
        for row in db.query(LoanMovement.loan_id, func.coalesce(func.sum(LoanMovement.amount), 0))
        .filter(LoanMovement.loan_id.in_(loan_ids))
        .group_by(LoanMovement.loan_id)
        .all()
    } if loan_ids else {}
    for loan in active_loans:
        loans.append({
            "id": loan.id,
            "name": loan.name,
            "currency": loan.currency,
            "outstanding": Decimal(loan_balances.get(loan.id, 0)),
            "monthly_rate": loan.monthly_rate,
            "annual_effective_rate": loan.annual_effective_rate,
        })
    recent = db.query(FinancialTransaction).filter(
        FinancialTransaction.user_id == context.user.id,
        FinancialTransaction.status == TransactionStatus.ACTIVE,
    ).limit(20).all()
    recent_transfers = db.query(Transfer, FinancialOperation.created_at).join(
        FinancialOperation, Transfer.operation_id == FinancialOperation.id,
    ).filter(Transfer.user_id == context.user.id).limit(20).all()
    account_names = {a.id: a.name for a in accounts}
    card_names = {c.id: c.name for c in cards}
    recent_entries = [(item.transaction_date, item.created_at, item.id, "transaction", item) for item in recent]
    recent_entries.extend(
        (item.transfer_date, created_at, item.id, "transfer", item)
        for item, created_at in recent_transfers
    )
    recent_entries.sort(key=lambda entry: (entry[0], entry[1], entry[2]), reverse=True)
    transaction_list = []
    for _, _, _, entry_type, item in recent_entries[:20]:
        if entry_type == "transfer":
            transaction_list.append({
                "id": item.id,
                "entry_type": "transfer",
                "transaction_type": "transfer",
                "amount": item.source_amount,
                "currency": item.source_currency,
                "original_amount": item.destination_amount,
                "original_currency": item.destination_currency,
                "transaction_date": item.transfer_date,
                "payment_method": "transfer",
                "description": item.description,
                "category_id": None,
                "source": account_names.get(item.source_account_id, f"Cuenta #{item.source_account_id}"),
                "destination": account_names.get(item.destination_account_id, f"Cuenta #{item.destination_account_id}"),
            })
            continue
        source = account_names.get(item.account_id) if item.account_id is not None else (card_names.get(item.card_id, "") if item.card_id is not None else "")
        transaction_list.append({
            "id": item.id,
            "entry_type": "transaction",
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
            "destination": None,
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

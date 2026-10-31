from calendar import monthrange
from datetime import date, timedelta
import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.recurring_schemas import RecurringPaymentCreate, RecurringPaymentUpdate
from app.api.ledger_schemas import TransactionCreate
from app.domain.money import normalize_amount
from app.models.ledger import Account, FinancialOperation
from app.models.recurring import RecurringPayment
from app.services.ledger import create_transaction, get_owned_account, get_owned_category

logger = logging.getLogger(__name__)


def _account_for(payment: RecurringPayment, db: Session, user_id: int) -> Account:
    account_id = payment.source_account_id if payment.transaction_type == "expense" else payment.destination_account_id
    if account_id is None:
        raise HTTPException(status_code=422, detail="La recurrencia no tiene una cuenta válida")
    account = get_owned_account(db, user_id, account_id)
    if account.is_archived:
        raise HTTPException(status_code=422, detail="La cuenta de la recurrencia está archivada")
    return account


def _safe_date(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, monthrange(year, month)[1]))


def _next_occurrence(payment: RecurringPayment, current: date) -> date | None:
    if payment.frequency == "weekly":
        days = (payment.weekday - current.weekday()) % 7
        return current + timedelta(days=days)
    if payment.frequency == "monthly":
        candidate = _safe_date(current.year, current.month, payment.day_of_month or 1)
        if candidate < current:
            if current.month == 12:
                candidate = _safe_date(current.year + 1, 1, payment.day_of_month or 1)
            else:
                candidate = _safe_date(current.year, current.month + 1, payment.day_of_month or 1)
        return candidate
    candidate = _safe_date(current.year, payment.month or 1, payment.day_of_month or 1)
    if candidate < current:
        candidate = _safe_date(current.year + 1, payment.month or 1, payment.day_of_month or 1)
    return candidate


def _first_occurrence(payment: RecurringPayment) -> date:
    return _next_occurrence(payment, payment.start_date) or payment.start_date


def create_recurring(db: Session, user_id: int, payload: RecurringPaymentCreate) -> RecurringPayment:
    account = _account_for_payload(db, user_id, payload)
    get_owned_category(db, user_id, payload.category_id)
    amount = normalize_amount(payload.amount, account.currency)
    payment = RecurringPayment(
        user_id=user_id,
        transaction_type=payload.transaction_type,
        source_account_id=payload.source_account_id,
        destination_account_id=payload.destination_account_id,
        amount=amount,
        category_id=payload.category_id,
        description=payload.description,
        frequency=payload.frequency,
        weekday=payload.weekday,
        day_of_month=payload.day_of_month,
        month=payload.month,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    db.add(payment)
    db.flush()
    return payment


def update_recurring(db: Session, user_id: int, payment: RecurringPayment, payload: RecurringPaymentUpdate) -> RecurringPayment:
    account = _account_for_payload(db, user_id, payload)
    get_owned_category(db, user_id, payload.category_id)
    payment.transaction_type = payload.transaction_type
    payment.source_account_id = payload.source_account_id
    payment.destination_account_id = payload.destination_account_id
    payment.amount = normalize_amount(payload.amount, account.currency)
    payment.category_id = payload.category_id
    payment.description = payload.description
    payment.frequency = payload.frequency
    payment.weekday = payload.weekday
    payment.day_of_month = payload.day_of_month
    payment.month = payload.month
    payment.start_date = payload.start_date
    payment.end_date = payload.end_date
    payment.is_active = payload.is_active
    return payment


def _account_for_payload(db: Session, user_id: int, payload: RecurringPaymentCreate) -> Account:
    account_id = payload.source_account_id if payload.transaction_type == "expense" else payload.destination_account_id
    if account_id is None:
        raise HTTPException(status_code=422, detail="La recurrencia no tiene una cuenta válida")
    account = get_owned_account(db, user_id, account_id)
    if account.is_archived:
        raise HTTPException(status_code=422, detail="La cuenta de la recurrencia está archivada")
    return account


def process_payment(db: Session, payment: RecurringPayment, today: date) -> None:
    if not payment.is_active:
        return
    current = payment.last_processed_date + timedelta(days=1) if payment.last_processed_date else payment.start_date
    occurrence = _first_occurrence(payment) if current == payment.start_date else _next_occurrence(payment, current)
    while occurrence is not None and occurrence <= today:
        if payment.end_date is not None and occurrence > payment.end_date:
            payment.is_active = False
            break
        key = f"recurring:{payment.id}:{occurrence.isoformat()}"
        operation = db.query(FinancialOperation).filter(
            FinancialOperation.user_id == payment.user_id,
            FinancialOperation.idempotency_key == key,
        ).one_or_none()
        if operation is None:
            account = _account_for(payment, db, payment.user_id)
            try:
                transaction = create_transaction(
                    db,
                    payment.user_id,
                    TransactionCreate(
                        transaction_type=payment.transaction_type,
                        amount=payment.amount,
                        currency=account.currency,
                        transaction_date=occurrence,
                        account_id=account.id,
                        category_id=payment.category_id,
                        description=payment.description,
                        is_recurring=True,
                    ),
                    key,
                )
                logger.info("Generated recurring transaction %s for payment %s", transaction.id, payment.id)
            except HTTPException as exc:
                if exc.status_code != 422:
                    raise
                logger.info("Skipped recurring payment %s on %s: %s", payment.id, occurrence, exc.detail)
                db.rollback()
                payment = db.query(RecurringPayment).filter(RecurringPayment.id == payment.id).one()
        payment.last_processed_date = occurrence
        db.commit()
        db.refresh(payment)
        current = occurrence + timedelta(days=1)
        occurrence = _next_occurrence(payment, current)
    db.commit()


def process_due_recurring_payments() -> None:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        payments = db.query(RecurringPayment).filter(RecurringPayment.is_active.is_(True)).all()
        today = date.today()
        for payment in payments:
            try:
                process_payment(db, payment, today)
            except Exception:
                db.rollback()
                logger.exception("Unable to process recurring payment %s", payment.id)
    finally:
        db.close()

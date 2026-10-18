from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.ledger_schemas import AccountCreate, BalanceAdjustmentCreate, TransactionCreate, TransactionUpdate, TransferCreate
from app.domain.money import normalize_amount, normalize_currency
from app.models.ledger import Account, AccountMovement, Category, FinancialOperation, FinancialTransaction, Transfer


def not_found(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


def account_balance(db: Session, account: Account) -> Decimal:
    movements = db.query(func.coalesce(func.sum(AccountMovement.amount), 0)).filter(AccountMovement.account_id == account.id).scalar()
    return Decimal(account.opening_balance) + Decimal(movements or 0)


def get_owned_account(db: Session, user_id: int, account_id: int) -> Account:
    account = db.query(Account).filter(Account.id == account_id, Account.user_id == user_id).one_or_none()
    if account is None:
        raise not_found("Cuenta no encontrada")
    return account


def get_owned_category(db: Session, user_id: int, category_id: int) -> Category:
    category = db.query(Category).filter(Category.id == category_id, Category.user_id == user_id, Category.is_archived.is_(False)).one_or_none()
    if category is None:
        raise not_found("Categoría no encontrada")
    return category


def create_operation(db: Session, user_id: int, operation_type: str, effective_date: date, idempotency_key: str | None = None) -> FinancialOperation:
    operation = FinancialOperation(
        user_id=user_id,
        operation_type=operation_type,
        effective_date=effective_date,
        idempotency_key=idempotency_key,
    )
    db.add(operation)
    db.flush()
    return operation


def create_account(db: Session, user_id: int, payload: AccountCreate) -> Account:
    currency = normalize_currency(payload.currency)
    try:
        opening_balance = normalize_amount(payload.opening_balance, currency, positive=False)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    account = Account(
        user_id=user_id,
        name=payload.name.strip(),
        account_type=payload.account_type,
        currency=currency,
        opening_balance=opening_balance,
        opening_balance_date=payload.opening_balance_date,
        description=payload.description,
    )
    db.add(account)
    db.flush()
    return account


def create_transaction(
    db: Session,
    user_id: int,
    payload: TransactionCreate,
    idempotency_key: str | None = None,
) -> FinancialTransaction:
    account = get_owned_account(db, user_id, payload.account_id)
    category = get_owned_category(db, user_id, payload.category_id)
    if account.currency != normalize_currency(payload.currency):
        raise HTTPException(status_code=422, detail="La moneda no coincide con la cuenta")
    if category.kind not in ("both", payload.transaction_type):
        raise HTTPException(status_code=422, detail="La categoría no corresponde al tipo de transacción")
    try:
        amount = normalize_amount(payload.amount, account.currency)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    operation = create_operation(db, user_id, payload.transaction_type, payload.transaction_date, idempotency_key)
    signed_amount = amount if payload.transaction_type == "income" else -amount
    db.add(AccountMovement(operation_id=operation.id, account_id=account.id, amount=signed_amount, currency=account.currency))
    transaction = FinancialTransaction(
        operation_id=operation.id,
        user_id=user_id,
        transaction_type=payload.transaction_type,
        amount=amount,
        currency=account.currency,
        transaction_date=payload.transaction_date,
        account_id=account.id,
        category_id=category.id,
        description=payload.description,
        notes=payload.notes,
    )
    db.add(transaction)
    db.flush()
    return transaction


def reverse_transaction(db: Session, user_id: int, transaction: FinancialTransaction, reason: str) -> None:
    if transaction.card_id is not None or transaction.credit_purchase_id is not None:
        _reverse_credit_transaction(db, user_id, transaction)
        return
    account = get_owned_account(db, user_id, transaction.account_id)
    operation = db.query(FinancialOperation).filter(FinancialOperation.id == transaction.operation_id, FinancialOperation.user_id == user_id).one()
    original_movement = db.query(AccountMovement).filter(AccountMovement.operation_id == operation.id).one()
    reversal = create_operation(db, user_id, "reversal", transaction.transaction_date)
    db.add(AccountMovement(operation_id=reversal.id, account_id=account.id, amount=-original_movement.amount, currency=account.currency))
    operation.status = "voided"
    reversal.reverses_operation_id = operation.id
    transaction.status = "voided"


def _reverse_credit_transaction(db: Session, user_id: int, transaction: FinancialTransaction) -> None:
    from app.models.cards import CardMovement, CreditPurchase, Installment

    operation = db.query(FinancialOperation).filter(
        FinancialOperation.id == transaction.operation_id,
        FinancialOperation.user_id == user_id,
    ).one()
    reversal = create_operation(db, user_id, "reversal", transaction.transaction_date)
    for movement in db.query(CardMovement).filter(CardMovement.operation_id == operation.id).all():
        db.add(CardMovement(operation_id=reversal.id, card_id=movement.card_id, amount=-movement.amount, currency=movement.currency))
    if transaction.credit_purchase_id is not None:
        purchase = db.query(CreditPurchase).filter(CreditPurchase.id == transaction.credit_purchase_id, CreditPurchase.user_id == user_id).one_or_none()
        if purchase is not None:
            purchase.status = "voided"
            for installment in db.query(Installment).filter(Installment.purchase_id == purchase.id).all():
                installment.status = "voided"
    operation.status = "voided"
    reversal.reverses_operation_id = operation.id
    transaction.status = "voided"


def create_transfer(db: Session, user_id: int, payload: TransferCreate, idempotency_key: str | None = None) -> Transfer:
    source = get_owned_account(db, user_id, payload.source_account_id)
    destination = get_owned_account(db, user_id, payload.destination_account_id)
    try:
        source_amount = normalize_amount(payload.source_amount, source.currency)
        destination_amount = normalize_amount(payload.destination_amount or payload.source_amount, destination.currency)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if source.currency == destination.currency:
        if payload.destination_amount is not None and destination_amount != source_amount:
            raise HTTPException(status_code=422, detail="Una transferencia en la misma moneda debe tener el mismo monto")
        exchange_rate = None
    else:
        if payload.destination_amount is None or payload.exchange_rate is None or payload.exchange_rate <= 0:
            raise HTTPException(status_code=422, detail="Una transferencia multidivisa requiere monto destino y tasa")
        exchange_rate = payload.exchange_rate

    operation = create_operation(db, user_id, "transfer", payload.transfer_date, idempotency_key)
    db.add_all(
        [
            AccountMovement(operation_id=operation.id, account_id=source.id, amount=-source_amount, currency=source.currency),
            AccountMovement(operation_id=operation.id, account_id=destination.id, amount=destination_amount, currency=destination.currency),
        ]
    )
    transfer = Transfer(
        operation_id=operation.id,
        user_id=user_id,
        source_account_id=source.id,
        destination_account_id=destination.id,
        source_amount=source_amount,
        source_currency=source.currency,
        destination_amount=destination_amount,
        destination_currency=destination.currency,
        transfer_date=payload.transfer_date,
        exchange_rate=exchange_rate,
        description=payload.description,
    )
    db.add(transfer)
    db.flush()
    return transfer


def adjust_account_balance(db: Session, user_id: int, account_id: int, payload: BalanceAdjustmentCreate, idempotency_key: str | None = None) -> Account:
    account = get_owned_account(db, user_id, account_id)
    try:
        target = normalize_amount(payload.target_balance, account.currency, positive=False)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    difference = target - account_balance(db, account)
    difference = normalize_amount(difference, account.currency, positive=False)
    if difference == 0:
        raise HTTPException(status_code=422, detail="El saldo ya coincide con el valor indicado")
    operation = create_operation(db, user_id, "balance_adjustment", payload.adjustment_date, idempotency_key)
    db.add(AccountMovement(operation_id=operation.id, account_id=account.id, amount=difference, currency=account.currency))
    db.flush()
    return account

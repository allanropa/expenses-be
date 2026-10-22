from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context, require_csrf
from app.api.ledger_schemas import TransactionCreate, TransactionResponse, TransactionUpdate
from app.db.session import get_db
from app.models.ledger import FinancialOperation, FinancialTransaction
from app.services.ledger import create_transaction, reverse_transaction
from app.domain.enums import TransactionStatus

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def response_for(transaction: FinancialTransaction) -> TransactionResponse:
    from app.domain.money import normalize_amount

    return TransactionResponse(
        id=transaction.id,
        transaction_type=transaction.transaction_type,
        amount=normalize_amount(transaction.amount, transaction.currency),
        currency=transaction.currency,
        original_amount=normalize_amount(transaction.original_amount, transaction.original_currency) if transaction.original_amount is not None and transaction.original_currency else None,
        original_currency=transaction.original_currency,
        transaction_date=transaction.transaction_date,
        account_id=transaction.account_id,
        card_id=transaction.card_id,
        credit_purchase_id=transaction.credit_purchase_id,
        category_id=transaction.category_id,
        payment_method=transaction.payment_method,
        description=transaction.description,
        notes=transaction.notes,
        status=transaction.status,
    )


def find_idempotent(db: Session, user_id: int, key: str | None) -> FinancialTransaction | None:
    if not key:
        return None
    operation = db.query(FinancialOperation).filter(FinancialOperation.user_id == user_id, FinancialOperation.idempotency_key == key).one_or_none()
    if operation is None:
        return None
    return db.query(FinancialTransaction).filter(FinancialTransaction.operation_id == operation.id).one_or_none()


@router.get("", response_model=list[TransactionResponse])
def list_transactions(
    date_from: date | None = None,
    date_to: date | None = None,
    transaction_type: str | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
    search: str | None = None,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    query = db.query(FinancialTransaction).filter(
        FinancialTransaction.user_id == context.user.id,
        FinancialTransaction.status == TransactionStatus.ACTIVE,
    )
    if date_from:
        query = query.filter(FinancialTransaction.transaction_date >= date_from)
    if date_to:
        query = query.filter(FinancialTransaction.transaction_date <= date_to)
    if transaction_type:
        query = query.filter(FinancialTransaction.transaction_type == transaction_type)
    if account_id:
        query = query.filter(FinancialTransaction.account_id == account_id)
    if category_id:
        query = query.filter(FinancialTransaction.category_id == category_id)
    if search:
        query = query.filter(FinancialTransaction.description.ilike(f"%{search}%"))
    return [response_for(item) for item in query.order_by(FinancialTransaction.transaction_date.desc(), FinancialTransaction.id.desc()).all()]


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_new_transaction(
    payload: TransactionCreate,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    existing = find_idempotent(db, context.user.id, idempotency_key)
    if existing:
        response.status_code = status.HTTP_200_OK
        return response_for(existing)
    try:
        transaction = create_transaction(db, context.user.id, payload, idempotency_key)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    db.refresh(transaction)
    return response_for(transaction)


@router.patch("/{transaction_id}", response_model=TransactionResponse)
def update_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    original = db.query(FinancialTransaction).filter(
        FinancialTransaction.id == transaction_id,
        FinancialTransaction.user_id == context.user.id,
        FinancialTransaction.status == TransactionStatus.ACTIVE,
    ).one_or_none()
    if original is None:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    values = {
        "transaction_type": payload.transaction_type or original.transaction_type,
        "amount": payload.amount if payload.amount is not None else original.amount,
        "currency": payload.currency or original.currency,
        "transaction_date": payload.transaction_date or original.transaction_date,
        "account_id": payload.account_id or original.account_id,
        "category_id": payload.category_id or original.category_id,
        "description": payload.description if payload.description is not None else original.description,
        "notes": payload.notes if payload.notes is not None else original.notes,
    }
    reverse_transaction(db, context.user.id, original, "update")
    replacement = create_transaction(db, context.user.id, TransactionCreate(**values))
    original.replaced_by_id = replacement.id
    db.commit()
    db.refresh(replacement)
    return response_for(replacement)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    transaction_id: int,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    transaction = db.query(FinancialTransaction).filter(
        FinancialTransaction.id == transaction_id,
        FinancialTransaction.user_id == context.user.id,
        FinancialTransaction.status == TransactionStatus.ACTIVE,
    ).one_or_none()
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    reverse_transaction(db, context.user.id, transaction, "delete")
    db.commit()

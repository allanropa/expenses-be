from datetime import date
from typing import Literal, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import Integer, String, cast as sql_cast, literal, or_, select, union_all
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context, require_csrf
from app.api.ledger_schemas import TransactionCreate, TransactionResponse, TransactionUpdate
from app.db.session import get_db
from app.models.ledger import FinancialOperation, FinancialTransaction, Transfer
from app.services.ledger import create_transaction, reverse_transaction
from app.domain.enums import TransactionStatus
from app.api.pagination import Pagination

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def response_for(transaction: FinancialTransaction) -> TransactionResponse:
    from app.domain.money import normalize_amount

    return TransactionResponse(
        id=transaction.id,
        entry_type="transaction",
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
        category_ids=transaction.category_ids or [transaction.category_id],
        destination_account_id=None,
        payment_method=transaction.payment_method,
        description=transaction.description,
        notes=transaction.notes,
        status=transaction.status,
    )


def response_for_transfer(transfer: Transfer) -> TransactionResponse:
    from app.domain.money import normalize_amount

    return TransactionResponse(
        id=transfer.id,
        entry_type="transfer",
        transaction_type="transfer",
        amount=normalize_amount(transfer.source_amount, transfer.source_currency),
        currency=transfer.source_currency,
        original_amount=normalize_amount(transfer.destination_amount, transfer.destination_currency),
        original_currency=transfer.destination_currency,
        transaction_date=transfer.transfer_date,
        account_id=transfer.source_account_id,
        card_id=None,
        credit_purchase_id=None,
        category_id=None,
        destination_account_id=transfer.destination_account_id,
        payment_method="transfer",
        description=transfer.description,
        notes=None,
        status="active",
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
    card_id: int | None = None,
    category_id: int | None = None,
    search: str | None = None,
    pagination: Pagination = Depends(),
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    transaction_entries = select(
        literal("transaction").label("entry_type"),
        FinancialTransaction.id.label("id"),
        FinancialTransaction.transaction_date.label("entry_date"),
        FinancialTransaction.created_at.label("created_at"),
        FinancialTransaction.transaction_type.label("transaction_type"),
        FinancialTransaction.account_id.label("account_id"),
        sql_cast(literal(None), Integer).label("destination_account_id"),
        FinancialTransaction.description.label("description"),
    ).where(
        FinancialTransaction.user_id == context.user.id,
        FinancialTransaction.status == TransactionStatus.ACTIVE,
    )
    transfer_entries = select(
        literal("transfer").label("entry_type"),
        Transfer.id.label("id"),
        Transfer.transfer_date.label("entry_date"),
        FinancialOperation.created_at.label("created_at"),
        literal("transfer").label("transaction_type"),
        Transfer.source_account_id.label("account_id"),
        Transfer.destination_account_id.label("destination_account_id"),
        Transfer.description.label("description"),
    ).where(
        Transfer.user_id == context.user.id,
        Transfer.operation_id == FinancialOperation.id,
    )

    if date_from:
        transaction_entries = transaction_entries.where(FinancialTransaction.transaction_date >= date_from)
        transfer_entries = transfer_entries.where(Transfer.transfer_date >= date_from)
    if date_to:
        transaction_entries = transaction_entries.where(FinancialTransaction.transaction_date <= date_to)
        transfer_entries = transfer_entries.where(Transfer.transfer_date <= date_to)
    if transaction_type == "transfer":
        transaction_entries = transaction_entries.where(literal(False))
    elif transaction_type:
        transaction_entries = transaction_entries.where(FinancialTransaction.transaction_type == transaction_type)
        transfer_entries = transfer_entries.where(literal(False))
    if account_id:
        transaction_entries = transaction_entries.where(FinancialTransaction.account_id == account_id)
        transfer_entries = transfer_entries.where(
            or_(Transfer.source_account_id == account_id, Transfer.destination_account_id == account_id)
        )
    if card_id:
        transaction_entries = transaction_entries.where(FinancialTransaction.card_id == card_id)
        transfer_entries = transfer_entries.where(literal(False))
    if category_id:
        category_ids_match = (
            sql_cast(FinancialTransaction.category_ids, JSONB).contains([category_id])
            if db.bind is not None and db.bind.dialect.name == "postgresql"
            else sql_cast(FinancialTransaction.category_ids, String).contains(f"[{category_id}]")
        )
        transaction_entries = transaction_entries.where(
            or_(FinancialTransaction.category_id == category_id, category_ids_match)
        )
        transfer_entries = transfer_entries.where(literal(False))
    if search:
        transaction_entries = transaction_entries.where(FinancialTransaction.description.ilike(f"%{search}%"))
        transfer_entries = transfer_entries.where(Transfer.description.ilike(f"%{search}%"))

    entries = union_all(transaction_entries, transfer_entries).subquery()
    rows = db.execute(
        select(entries)
        .order_by(entries.c.entry_date.desc(), entries.c.created_at.desc(), entries.c.id.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    ).mappings().all()
    result = []
    for row in rows:
        if row["entry_type"] == "transaction":
            item = db.query(FinancialTransaction).filter(FinancialTransaction.id == row["id"]).one()
            result.append(response_for(item))
        else:
            transfer = db.query(Transfer).filter(Transfer.id == row["id"]).one()
            result.append(response_for_transfer(transfer))
    return result


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
    if original.card_id is not None or original.credit_purchase_id is not None:
        raise HTTPException(
            status_code=422,
            detail="Las transacciones generadas por tarjetas no se pueden editar; elimínelas o modifique la operación de origen",
        )
    if original.account_id is None or original.category_id is None:
        raise HTTPException(status_code=422, detail="La transacción no tiene referencias completas")
    replacement_payload = TransactionCreate(
        transaction_type=cast(Literal["income", "expense"], payload.transaction_type or original.transaction_type),
        amount=payload.amount if payload.amount is not None else original.amount,
        currency=payload.currency or original.currency,
        transaction_date=payload.transaction_date or original.transaction_date,
        account_id=payload.account_id or original.account_id,
        category_id=payload.category_id or original.category_id,
        description=payload.description if payload.description is not None else original.description,
        notes=payload.notes if payload.notes is not None else original.notes,
    )
    reverse_transaction(db, context.user.id, original, "update")
    replacement = create_transaction(db, context.user.id, replacement_payload)
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

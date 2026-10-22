from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.orm import Session
from decimal import Decimal

from app.api.deps import AuthContext, get_auth_context, require_csrf
from app.api.ledger_schemas import AccountCreate, AccountMovementResponse, AccountResponse, AccountUpdate, BalanceAdjustmentCreate
from app.db.session import get_db
from app.models.ledger import Account, AccountMovement, FinancialOperation, FinancialTransaction, Transfer
from app.services.ledger import account_balance, adjust_account_balance, create_account, get_owned_account
from app.api.pagination import Pagination

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def to_response(db: Session, account: Account, balance: Decimal | None = None) -> AccountResponse:
    from app.domain.money import normalize_amount

    balance = normalize_amount(account_balance(db, account), account.currency, positive=False) if balance is None else normalize_amount(balance, account.currency, positive=False)
    opening_balance = normalize_amount(account.opening_balance, account.currency, positive=False)
    return AccountResponse(
        id=account.id,
        name=account.name,
        account_type=account.account_type,
        currency=account.currency,
        opening_balance=opening_balance,
        opening_balance_date=account.opening_balance_date,
        current_balance=balance,
        description=account.description,
        is_archived=account.is_archived,
    )


@router.get("", response_model=list[AccountResponse])
def list_accounts(context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    accounts = db.query(Account).filter(Account.user_id == context.user.id, Account.is_archived.is_(False)).order_by(Account.name).all()
    balances = dict(
        db.query(AccountMovement.account_id, func.coalesce(func.sum(AccountMovement.amount), 0))
        .filter(AccountMovement.account_id.in_([account.id for account in accounts]))
        .group_by(AccountMovement.account_id)
        .all()
    ) if accounts else {}
    return [to_response(db, account, Decimal(account.opening_balance) + Decimal(balances.get(account.id, 0))) for account in accounts]


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_new_account(
    payload: AccountCreate,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    try:
        account = create_account(db, context.user.id, payload)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ya existe una cuenta con ese nombre") from None
    db.refresh(account)
    return to_response(db, account)


@router.patch("/{account_id}", response_model=AccountResponse)
def update_account(
    account_id: int,
    payload: AccountUpdate,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    account = get_owned_account(db, context.user.id, account_id)
    if payload.name is not None:
        account.name = payload.name.strip()
    if payload.description is not None:
        account.description = payload.description
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ya existe una cuenta con ese nombre") from None
    db.refresh(account)
    return to_response(db, account)


@router.post("/{account_id}/archive", response_model=AccountResponse)
def archive_account(
    account_id: int,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    account = get_owned_account(db, context.user.id, account_id)
    account.is_archived = True
    db.commit()
    db.refresh(account)
    return to_response(db, account)


@router.get("/{account_id}", response_model=AccountResponse)
def get_account(
    account_id: int,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    return to_response(db, get_owned_account(db, context.user.id, account_id))


@router.get("/{account_id}/movements", response_model=list[AccountMovementResponse])
def account_movements(
    account_id: int,
    pagination: Pagination = Depends(),
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    account = get_owned_account(db, context.user.id, account_id)
    movements = db.query(AccountMovement).filter(AccountMovement.account_id == account.id).order_by(AccountMovement.id.desc()).offset(pagination.offset).limit(pagination.limit).all()
    operation_ids = [item.operation_id for item in movements]
    operations = {
        item.id: item
        for item in db.query(FinancialOperation).filter(FinancialOperation.id.in_(operation_ids)).all()
    } if operation_ids else {}
    transactions = {
        item.operation_id: item
        for item in db.query(FinancialTransaction).filter(FinancialTransaction.operation_id.in_(operation_ids)).all()
    } if operation_ids else {}
    transfers = {
        item.operation_id: item
        for item in db.query(Transfer).filter(Transfer.operation_id.in_(operation_ids)).all()
    } if operation_ids else {}
    result = []
    for item in movements:
        operation = operations[item.operation_id]
        transaction = transactions.get(operation.id)
        transfer = transfers.get(operation.id)
        result.append(
            AccountMovementResponse(
                id=item.id,
                operation_id=item.operation_id,
                operation_type=operation.operation_type,
                effective_date=operation.effective_date,
                amount=item.amount,
                currency=item.currency,
                description=(transaction.description if transaction else transfer.description if transfer else None),
            )
        )
    return result


@router.post("/{account_id}/balance-adjustments", response_model=AccountResponse)
def adjust_balance(
    account_id: int,
    payload: BalanceAdjustmentCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    account = adjust_account_balance(db, context.user.id, account_id, payload, idempotency_key)
    db.commit()
    db.refresh(account)
    return to_response(db, account)

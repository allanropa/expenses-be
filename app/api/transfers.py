from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context, require_csrf
from app.api.ledger_schemas import TransferCreate, TransferResponse
from app.db.session import get_db
from app.models.ledger import FinancialOperation, Transfer
from app.services.ledger import create_transfer

router = APIRouter(prefix="/api/transfers", tags=["transfers"])


def response_for(transfer: Transfer) -> TransferResponse:
    from app.domain.money import normalize_amount

    return TransferResponse(
        id=transfer.id,
        source_account_id=transfer.source_account_id,
        destination_account_id=transfer.destination_account_id,
        source_amount=normalize_amount(transfer.source_amount, transfer.source_currency),
        source_currency=transfer.source_currency,
        destination_amount=normalize_amount(transfer.destination_amount, transfer.destination_currency),
        destination_currency=transfer.destination_currency,
        transfer_date=transfer.transfer_date,
        exchange_rate=transfer.exchange_rate,
        description=transfer.description,
    )


@router.get("", response_model=list[TransferResponse])
def list_transfers(context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    return [response_for(item) for item in db.query(Transfer).filter(Transfer.user_id == context.user.id).order_by(Transfer.transfer_date.desc()).all()]


@router.post("", response_model=TransferResponse, status_code=status.HTTP_201_CREATED)
def create_new_transfer(
    payload: TransferCreate,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    if idempotency_key:
        operation = db.query(FinancialOperation).filter(
            FinancialOperation.user_id == context.user.id,
            FinancialOperation.idempotency_key == idempotency_key,
        ).one_or_none()
        if operation:
            existing = db.query(Transfer).filter(Transfer.operation_id == operation.id).one()
            response.status_code = status.HTTP_200_OK
            return response_for(existing)
    transfer = create_transfer(db, context.user.id, payload, idempotency_key)
    db.commit()
    db.refresh(transfer)
    return response_for(transfer)

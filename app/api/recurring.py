from decimal import Decimal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context, require_csrf
from app.api.recurring_schemas import RecurringPaymentCreate, RecurringPaymentResponse, RecurringPaymentUpdate
from app.db.session import get_db
from app.models.ledger import Account
from app.models.recurring import RecurringPayment
from app.services.recurring import create_recurring, update_recurring

router = APIRouter(prefix="/api/recurring-payments", tags=["recurring-payments"])


def to_response(db: Session, payment: RecurringPayment) -> RecurringPaymentResponse:
    account_id = payment.source_account_id if payment.transaction_type == "expense" else payment.destination_account_id
    account = db.query(Account).filter(Account.id == account_id).one_or_none()
    return RecurringPaymentResponse(
        id=payment.id,
        transaction_type=payment.transaction_type,
        source_account_id=payment.source_account_id,
        destination_account_id=payment.destination_account_id,
        card_id=payment.card_id,
        amount=Decimal(payment.amount),
        currency=payment.currency if payment.card_id is not None else account.currency,
        category_id=payment.category_id,
        description=payment.description,
        frequency=payment.frequency,
        weekday=payment.weekday,
        day_of_month=payment.day_of_month,
        month=payment.month,
        start_date=payment.start_date,
        end_date=payment.end_date,
        is_active=payment.is_active,
    )


@router.get("", response_model=list[RecurringPaymentResponse])
def list_recurring(
    active_only: bool = Query(True),
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    query = db.query(RecurringPayment).filter(RecurringPayment.user_id == context.user.id)
    if active_only:
        query = query.filter(RecurringPayment.is_active.is_(True))
    return [to_response(db, item) for item in query.order_by(RecurringPayment.id.desc()).all()]


@router.post("", response_model=RecurringPaymentResponse, status_code=status.HTTP_201_CREATED)
def create_new_recurring(
    payload: RecurringPaymentCreate,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    payment = create_recurring(db, context.user.id, payload)
    db.commit()
    db.refresh(payment)
    return to_response(db, payment)


@router.patch("/{payment_id}", response_model=RecurringPaymentResponse)
def update_existing_recurring(
    payment_id: int,
    payload: RecurringPaymentUpdate,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    payment = db.query(RecurringPayment).filter(
        RecurringPayment.id == payment_id,
        RecurringPayment.user_id == context.user.id,
    ).one_or_none()
    if payment is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Pago recurrente no encontrado")
    update_recurring(db, context.user.id, payment, payload)
    db.commit()
    db.refresh(payment)
    return to_response(db, payment)


@router.post("/{payment_id}/deactivate", response_model=RecurringPaymentResponse)
def deactivate_recurring(
    payment_id: int,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    payment = db.query(RecurringPayment).filter(
        RecurringPayment.id == payment_id,
        RecurringPayment.user_id == context.user.id,
    ).one_or_none()
    if payment is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Pago recurrente no encontrado")
    payment.is_active = False
    db.commit()
    db.refresh(payment)
    return to_response(db, payment)

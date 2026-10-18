from datetime import date
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.cards import CardCharge, CardMovement


def card_debt(db: Session, card_id: int, currency: str) -> Decimal:
    value = db.query(func.coalesce(func.sum(CardMovement.amount), 0)).filter(
        CardMovement.card_id == card_id,
        CardMovement.currency == currency,
    ).scalar()
    return Decimal(value or 0)


def charge_paid(db: Session, charge_id: int) -> Decimal:
    from app.models.cards import CardPaymentAllocation

    value = db.query(func.coalesce(func.sum(CardPaymentAllocation.amount), 0)).filter(
        CardPaymentAllocation.charge_id == charge_id,
    ).scalar()
    return Decimal(value or 0)


def outstanding_charges(db: Session, card_id: int, currency: str):
    charges = db.query(CardCharge).filter(
        CardCharge.card_id == card_id,
        CardCharge.currency == currency,
    ).order_by(CardCharge.charge_date, CardCharge.id).all()
    return [(charge, charge.amount - charge_paid(db, charge.id)) for charge in charges if charge.amount - charge_paid(db, charge.id) > 0]

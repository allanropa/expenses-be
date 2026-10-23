from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.card_schemas import (
    CardBalanceAdjustmentCreate,
    CardChargeCreate,
    CardCurrencyResponse,
    CardCreate,
    CardResponse,
    CardUpdate,
    InstallmentResponse,
    InterestConfigCreate,
    InterestConfigResponse,
    PaymentCreate,
    PaymentResponse,
    PurchaseCreate,
    PurchaseResponse,
)
from app.api.deps import AuthContext, get_auth_context, require_csrf
from app.db.session import get_db
from app.domain.cards import card_debt
from app.domain.financing import add_months, closing_date_for_month
from app.domain.money import normalize_amount
from app.models.cards import (
    CardCharge,
    CardCurrency,
    CardMovement,
    CardPayment,
    CreditCard,
    CreditPurchase,
    Installment,
    InterestRateConfiguration,
)
from app.models.ledger import FinancialOperation
from app.services.cards import adjust_card_debt, create_card, create_charge, create_payment, create_purchase, get_owned_card, supported_currency
from app.domain.enums import TransactionStatus
from app.api.pagination import Pagination

router = APIRouter(prefix="/api/cards", tags=["credit cards"])


def card_response(db: Session, card: CreditCard) -> CardResponse:
    currencies = []
    for item in db.query(CardCurrency).filter(CardCurrency.card_id == card.id).order_by(CardCurrency.currency).all():
        debt = normalize_amount(card_debt(db, card.id, item.currency), item.currency, positive=False)
        available = normalize_amount(item.credit_limit - debt, item.currency, positive=False) if item.credit_limit is not None else None
        currencies.append(CardCurrencyResponse(currency=item.currency, credit_limit=item.credit_limit, outstanding_debt=debt, available_credit=available))
    return CardResponse(
        id=card.id,
        name=card.name,
        issuing_bank=card.issuing_bank,
        statement_closing_day=card.statement_closing_day,
        description=card.description,
        is_archived=card.is_archived,
        currencies=currencies,
        interest_rates=[
            InterestConfigResponse.model_validate(item, from_attributes=True)
            for item in db.query(InterestRateConfiguration)
            .filter(InterestRateConfiguration.card_id == card.id)
            .order_by(InterestRateConfiguration.effective_from.desc(), InterestRateConfiguration.id.desc())
            .all()
        ],
    )


def card_responses(db: Session, cards: list[CreditCard]) -> list[CardResponse]:
    if not cards:
        return []
    card_ids = [card.id for card in cards]
    currencies = db.query(CardCurrency).filter(CardCurrency.card_id.in_(card_ids)).order_by(CardCurrency.currency).all()
    debts = {
        (card_id, currency): amount
        for card_id, currency, amount in db.query(
            CardMovement.card_id,
            CardMovement.currency,
            func.coalesce(func.sum(CardMovement.amount), 0),
        )
        .filter(CardMovement.card_id.in_(card_ids))
        .group_by(CardMovement.card_id, CardMovement.currency)
        .all()
    }
    rates: dict[int, list[InterestRateConfiguration]] = {}
    for rate in db.query(InterestRateConfiguration).filter(InterestRateConfiguration.card_id.in_(card_ids)).order_by(
        InterestRateConfiguration.effective_from.desc(), InterestRateConfiguration.id.desc()
    ).all():
        rates.setdefault(rate.card_id, []).append(rate)
    currencies_by_card: dict[int, list[CardCurrency]] = {}
    for item in currencies:
        currencies_by_card.setdefault(item.card_id, []).append(item)
    responses = []
    for card in cards:
        response_currencies = []
        for item in currencies_by_card.get(card.id, []):
            debt = normalize_amount(debts.get((card.id, item.currency), 0), item.currency, positive=False)
            available = normalize_amount(item.credit_limit - debt, item.currency, positive=False) if item.credit_limit is not None else None
            response_currencies.append(CardCurrencyResponse(currency=item.currency, credit_limit=item.credit_limit, outstanding_debt=debt, available_credit=available))
        responses.append(CardResponse(
            id=card.id,
            name=card.name,
            issuing_bank=card.issuing_bank,
            statement_closing_day=card.statement_closing_day,
            description=card.description,
            is_archived=card.is_archived,
            currencies=response_currencies,
            interest_rates=[InterestConfigResponse.model_validate(item, from_attributes=True) for item in rates.get(card.id, [])],
        ))
    return responses


def purchase_response(db: Session, purchase: CreditPurchase) -> PurchaseResponse:
    installments = db.query(Installment).filter(Installment.purchase_id == purchase.id).order_by(Installment.installment_number).all()
    return PurchaseResponse(
        id=purchase.id,
        card_id=purchase.card_id,
        category_id=purchase.category_id,
        amount=purchase.amount,
        currency=purchase.currency,
        purchase_date=purchase.purchase_date,
        installments_count=purchase.installments_count,
        monthly_interest_rate=purchase.monthly_interest_rate,
        financing_method=purchase.financing_method,
        status=purchase.status,
        description=purchase.description,
        installments=[InstallmentResponse.model_validate(item, from_attributes=True) for item in installments],
    )


def payment_response(payment: CardPayment) -> PaymentResponse:
    return PaymentResponse(
        id=payment.id,
        card_id=payment.card_id,
        source_account_id=payment.source_account_id,
        obligation_amount=payment.obligation_amount,
        obligation_currency=payment.obligation_currency,
        source_amount=payment.source_amount,
        source_currency=payment.source_currency,
        exchange_rate=payment.exchange_rate,
        fee_amount=payment.fee_amount,
        payment_date=payment.payment_date,
        notes=payment.notes,
    )


@router.get("", response_model=list[CardResponse])
def list_cards(archived: bool = Query(False), context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    cards = db.query(CreditCard).filter(CreditCard.user_id == context.user.id, CreditCard.is_archived.is_(archived)).order_by(CreditCard.name).all()
    return card_responses(db, cards)


@router.post("", response_model=CardResponse, status_code=status.HTTP_201_CREATED)
def create_new_card(
    payload: CardCreate,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    card = create_card(db, context.user.id, payload)
    db.commit()
    db.refresh(card)
    return card_response(db, card)


@router.get("/{card_id}", response_model=CardResponse)
def get_card(card_id: int, context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    return card_response(db, get_owned_card(db, context.user.id, card_id))


@router.post("/{card_id}/archive", response_model=CardResponse)
def archive_card(
    card_id: int,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    card = get_owned_card(db, context.user.id, card_id)
    card.is_archived = True
    db.commit()
    return card_response(db, card)


@router.post("/{card_id}/unarchive", response_model=CardResponse)
def unarchive_card(card_id: int, context: AuthContext = Depends(require_csrf), db: Session = Depends(get_db)):
    card = get_owned_card(db, context.user.id, card_id)
    card.is_archived = False
    db.commit()
    return card_response(db, card)


@router.patch("/{card_id}", response_model=CardResponse)
def update_card(
    card_id: int,
    payload: CardUpdate,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    card = get_owned_card(db, context.user.id, card_id)
    if payload.name is not None:
        card.name = payload.name.strip()
    if payload.issuing_bank is not None:
        card.issuing_bank = payload.issuing_bank if payload.issuing_bank else None
    if payload.statement_closing_day is not None:
        card.statement_closing_day = payload.statement_closing_day
    if payload.description is not None:
        card.description = payload.description
    if payload.credit_limits is not None:
        for currency, limit in payload.credit_limits.items():
            item = db.query(CardCurrency).filter(CardCurrency.card_id == card.id, CardCurrency.currency == currency).one_or_none()
            if item:
                item.credit_limit = limit
    db.commit()
    db.refresh(card)
    return card_response(db, card)


@router.post("/{card_id}/interest-rates", response_model=InterestConfigResponse, status_code=status.HTTP_201_CREATED)
def add_interest_rate(
    card_id: int,
    payload: InterestConfigCreate,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    card = get_owned_card(db, context.user.id, card_id)
    if payload.effective_to and payload.effective_to < payload.effective_from:
        raise HTTPException(status_code=422, detail="El fin de vigencia no puede preceder al inicio")
    if payload.currency:
        supported_currency(db, card.id, payload.currency)
    config = InterestRateConfiguration(
        card_id=card.id,
        currency=payload.currency,
        monthly_rate=payload.monthly_rate,
        rate_type=payload.rate_type,
        periodicity=payload.periodicity,
        calculation_method=payload.calculation_method,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@router.get("/{card_id}/interest-rates", response_model=list[InterestConfigResponse])
def list_interest_rates(card_id: int, context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    card = get_owned_card(db, context.user.id, card_id)
    return db.query(InterestRateConfiguration).filter(InterestRateConfiguration.card_id == card.id).order_by(InterestRateConfiguration.effective_from.desc()).all()


@router.post("/{card_id}/purchases", response_model=PurchaseResponse, status_code=status.HTTP_201_CREATED)
def create_new_purchase(
    card_id: int,
    payload: PurchaseCreate,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    if payload.card_id != card_id:
        raise HTTPException(status_code=422, detail="La tarjeta de la ruta no coincide")
    if idempotency_key:
        operation = db.query(FinancialOperation).filter(FinancialOperation.user_id == context.user.id, FinancialOperation.idempotency_key == idempotency_key).one_or_none()
        if operation:
            existing = db.query(CreditPurchase).filter(CreditPurchase.operation_id == operation.id).one_or_none()
            if existing:
                response.status_code = status.HTTP_200_OK
                return purchase_response(db, existing)
    purchase = create_purchase(db, context.user.id, payload, idempotency_key)
    db.commit()
    db.refresh(purchase)
    return purchase_response(db, purchase)


@router.get("/{card_id}/purchases", response_model=list[PurchaseResponse])
def list_purchases(card_id: int, pagination: Pagination = Depends(), context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    card = get_owned_card(db, context.user.id, card_id)
    purchases = db.query(CreditPurchase).filter(CreditPurchase.card_id == card.id, CreditPurchase.status == TransactionStatus.ACTIVE).order_by(CreditPurchase.purchase_date.desc()).offset(pagination.offset).limit(pagination.limit).all()
    return [purchase_response(db, purchase) for purchase in purchases]


@router.post("/{card_id}/charges", status_code=status.HTTP_201_CREATED)
def create_new_charge(
    card_id: int,
    payload: CardChargeCreate,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    try:
        charge = create_charge(db, context.user.id, card_id, payload)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    db.refresh(charge)
    return {"id": charge.id, "amount": charge.amount, "currency": charge.currency, "charge_type": charge.charge_type}


@router.post("/{card_id}/payments", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
def create_new_payment(
    card_id: int,
    payload: PaymentCreate,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    if payload.card_id != card_id:
        raise HTTPException(status_code=422, detail="La tarjeta de la ruta no coincide")
    if idempotency_key:
        operation = db.query(FinancialOperation).filter(FinancialOperation.user_id == context.user.id, FinancialOperation.idempotency_key == idempotency_key).one_or_none()
        if operation:
            existing = db.query(CardPayment).filter(CardPayment.operation_id == operation.id).one_or_none()
            if existing:
                response.status_code = status.HTTP_200_OK
                return payment_response(existing)
    try:
        payment = create_payment(db, context.user.id, payload, idempotency_key)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    db.refresh(payment)
    return payment_response(payment)


@router.get("/{card_id}/payments", response_model=list[PaymentResponse])
def list_payments(card_id: int, pagination: Pagination = Depends(), context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    card = get_owned_card(db, context.user.id, card_id)
    items = db.query(CardPayment).filter(CardPayment.card_id == card.id).order_by(CardPayment.payment_date.desc()).offset(pagination.offset).limit(pagination.limit).all()
    return [payment_response(item) for item in items]


@router.get("/{card_id}/statement")
def next_statement(card_id: int, context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    card = get_owned_card(db, context.user.id, card_id)
    today = date.today()
    current = closing_date_for_month(today.year, today.month, card.statement_closing_day)
    closing = current if today.day < current.day else add_months(current, 1, card.statement_closing_day)
    installments = db.query(Installment).join(CreditPurchase, Installment.purchase_id == CreditPurchase.id).filter(
        CreditPurchase.card_id == card.id,
        Installment.statement_closing_date == closing,
    ).all()
    charges = db.query(CardCharge).filter(
        CardCharge.card_id == card.id,
        CardCharge.charge_date <= closing,
        CardCharge.charge_type != "purchase_principal",
    ).order_by(CardCharge.charge_date, CardCharge.id).all()
    grouped: dict[str, Decimal] = {}
    for installment in installments:
        currency = db.query(CreditPurchase.currency).filter(CreditPurchase.id == installment.purchase_id).scalar()
        grouped[currency] = grouped.get(currency, Decimal("0")) + installment.estimated_total
    for charge in charges:
        grouped[charge.currency] = grouped.get(charge.currency, Decimal("0")) + charge.amount
    return {"next_closing_date": closing, "estimated_amount_by_currency": grouped}


@router.post("/{card_id}/balance-adjustments", response_model=CardResponse)
def adjust_balance(
    card_id: int,
    payload: CardBalanceAdjustmentCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    card = adjust_card_debt(db, context.user.id, card_id, payload, idempotency_key)
    db.commit()
    db.refresh(card)
    return card_response(db, card)

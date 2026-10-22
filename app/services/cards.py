from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.card_schemas import CardBalanceAdjustmentCreate, CardChargeCreate, CardCreate, PaymentCreate, PurchaseCreate
from app.domain.cards import card_debt, outstanding_charges
from app.domain.financing import estimate_installments
from app.domain.money import normalize_amount, normalize_currency
from app.models.cards import (
    CardCharge,
    CardCurrency,
    CardMovement,
    CardPayment,
    CardPaymentAllocation,
    CreditCard,
    CreditPurchase,
    Installment,
    InterestRateConfiguration,
)
from app.models.ledger import AccountMovement, Category, FinancialTransaction
from app.services.ledger import create_operation, get_owned_account, get_owned_category, not_found


def get_owned_card(db: Session, user_id: int, card_id: int) -> CreditCard:
    card = db.query(CreditCard).filter(CreditCard.id == card_id, CreditCard.user_id == user_id).one_or_none()
    if card is None:
        raise not_found("Tarjeta no encontrada")
    return card


def supported_currency(db: Session, card_id: int, currency: str) -> CardCurrency:
    item = db.query(CardCurrency).filter(CardCurrency.card_id == card_id, CardCurrency.currency == currency).one_or_none()
    if item is None:
        raise HTTPException(status_code=422, detail="La tarjeta no soporta esa moneda")
    return item


def default_payment_category(db: Session, user_id: int) -> Category:
    category = db.query(Category).filter(Category.user_id == user_id, Category.name == "Pagos de deuda", Category.is_archived.is_(False)).one_or_none()
    if category:
        return category
    category = db.query(Category).filter(Category.user_id == user_id, Category.name == "Otros gastos", Category.is_archived.is_(False)).one_or_none()
    if category:
        return category
    category = Category(user_id=user_id, name="Pagos de deuda", kind="expense")
    db.add(category)
    db.flush()
    return category


def applicable_rate(db: Session, card_id: int, currency: str, purchase_date: date) -> Decimal:
    exact = db.query(InterestRateConfiguration).filter(
        InterestRateConfiguration.card_id == card_id,
        InterestRateConfiguration.currency == currency,
        InterestRateConfiguration.effective_from <= purchase_date,
        (InterestRateConfiguration.effective_to.is_(None) | (InterestRateConfiguration.effective_to >= purchase_date)),
    ).order_by(InterestRateConfiguration.effective_from.desc()).first()
    if exact:
        return exact.monthly_rate
    generic = db.query(InterestRateConfiguration).filter(
        InterestRateConfiguration.card_id == card_id,
        InterestRateConfiguration.currency.is_(None),
        InterestRateConfiguration.effective_from <= purchase_date,
        (InterestRateConfiguration.effective_to.is_(None) | (InterestRateConfiguration.effective_to >= purchase_date)),
    ).order_by(InterestRateConfiguration.effective_from.desc()).first()
    return generic.monthly_rate if generic else Decimal("0")


def create_card(db: Session, user_id: int, payload: CardCreate) -> CreditCard:
    currencies = {item.currency for item in payload.currencies}
    if len(currencies) != len(payload.currencies):
        raise HTTPException(status_code=422, detail="No se puede repetir una moneda")
    card = CreditCard(
        user_id=user_id,
        name=payload.name.strip(),
        issuing_bank=payload.issuing_bank,
        statement_closing_day=payload.statement_closing_day,
        description=payload.description,
    )
    db.add(card)
    db.flush()
    for item in payload.currencies:
        limit = normalize_amount(item.credit_limit, item.currency) if item.credit_limit is not None else None
        db.add(CardCurrency(card_id=card.id, currency=item.currency, credit_limit=limit))
    db.flush()
    return card


def create_purchase(db: Session, user_id: int, payload: PurchaseCreate, idempotency_key: str | None = None) -> CreditPurchase:
    card = get_owned_card(db, user_id, payload.card_id)
    currency = normalize_currency(payload.currency)
    supported_currency(db, card.id, currency)
    category = get_owned_category(db, user_id, payload.category_id)
    if category.kind not in ("both", "expense"):
        raise HTTPException(status_code=422, detail="La categoría no corresponde a un gasto")
    try:
        amount = normalize_amount(payload.amount, currency)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    rate = applicable_rate(db, card.id, currency, payload.purchase_date)
    estimates = estimate_installments(amount, currency, payload.installments_count, rate, payload.purchase_date, card.statement_closing_day)
    operation = create_operation(db, user_id, "credit_purchase", payload.purchase_date, idempotency_key)
    purchase = CreditPurchase(
        operation_id=operation.id,
        user_id=user_id,
        card_id=card.id,
        category_id=category.id,
        amount=amount,
        currency=currency,
        purchase_date=payload.purchase_date,
        installments_count=payload.installments_count,
        monthly_interest_rate=rate,
        description=payload.description.strip(),
    )
    db.add(purchase)
    db.flush()
    db.add(CardMovement(operation_id=operation.id, card_id=card.id, amount=amount, currency=currency))
    charge = CardCharge(user_id=user_id, card_id=card.id, purchase_id=purchase.id, charge_type="purchase_principal", amount=amount, currency=currency, charge_date=payload.purchase_date, is_estimated=False, description=payload.description)
    db.add(charge)
    transaction = FinancialTransaction(
        operation_id=operation.id,
        user_id=user_id,
        transaction_type="expense",
        amount=amount,
        currency=currency,
        transaction_date=payload.purchase_date,
        account_id=None,
        card_id=card.id,
        credit_purchase_id=purchase.id,
        payment_method="credit",
        category_id=category.id,
        description=payload.description,
    )
    db.add(transaction)
    for estimate in estimates:
        db.add(Installment(
            purchase_id=purchase.id,
            installment_number=estimate.number,
            statement_closing_date=estimate.statement_closing_date,
            principal_amount=estimate.principal,
            estimated_interest=estimate.interest,
            estimated_total=estimate.total,
        ))
    db.flush()
    return purchase


def create_charge(db: Session, user_id: int, card_id: int, payload: CardChargeCreate) -> CardCharge:
    card = get_owned_card(db, user_id, card_id)
    currency = normalize_currency(payload.currency)
    supported_currency(db, card.id, currency)
    category = get_owned_category(db, user_id, payload.category_id)
    amount = normalize_amount(payload.amount, currency)
    operation = create_operation(db, user_id, f"card_{payload.charge_type}", payload.charge_date)
    db.add(CardMovement(operation_id=operation.id, card_id=card.id, amount=amount, currency=currency))
    charge = CardCharge(user_id=user_id, card_id=card.id, charge_type=payload.charge_type, amount=amount, currency=currency, charge_date=payload.charge_date, is_estimated=False, description=payload.description)
    db.add(charge)
    db.add(FinancialTransaction(
        operation_id=operation.id,
        user_id=user_id,
        transaction_type="expense",
        amount=amount,
        currency=currency,
        transaction_date=payload.charge_date,
        account_id=None,
        card_id=card.id,
        payment_method="credit",
        category_id=category.id,
        description=payload.description,
    ))
    db.flush()
    return charge


def create_payment(db: Session, user_id: int, payload: PaymentCreate, idempotency_key: str | None = None) -> CardPayment:
    card = get_owned_card(db, user_id, payload.card_id)
    obligation_currency = normalize_currency(payload.obligation_currency)
    supported_currency(db, card.id, obligation_currency)
    obligation_amount = normalize_amount(payload.obligation_amount, obligation_currency)
    debt = card_debt(db, card.id, obligation_currency)
    if obligation_amount > debt:
        raise HTTPException(status_code=422, detail="El pago supera la deuda pendiente en esa moneda")

    source_account = get_owned_account(db, user_id, payload.source_account_id) if payload.source_account_id else None
    source_amount = None
    source_currency = None
    exchange_rate = None
    fee_amount = None
    if source_account:
        source_currency = source_account.currency
        source_amount = normalize_amount(payload.source_amount or payload.obligation_amount, source_currency)
        assert source_amount is not None
        if source_currency == obligation_currency:
            if source_amount != obligation_amount:
                raise HTTPException(status_code=422, detail="El monto de origen debe coincidir con el pago")
        else:
            if payload.source_amount is None or payload.exchange_rate is None or payload.exchange_rate <= 0:
                raise HTTPException(status_code=422, detail="Un pago multidivisa requiere monto de origen y tasa")
            expected_source = normalize_amount(obligation_amount * payload.exchange_rate, source_currency)
            if source_amount != expected_source:
                raise HTTPException(status_code=422, detail="El monto de origen no coincide con la tasa registrada")
            exchange_rate = payload.exchange_rate
        if payload.fee_amount is not None:
            fee_amount = normalize_amount(payload.fee_amount, source_currency)
    elif payload.source_amount is not None or payload.exchange_rate is not None or payload.fee_amount is not None:
        raise HTTPException(status_code=422, detail="Los datos de origen requieren una cuenta")

    operation = create_operation(db, user_id, "card_payment", payload.payment_date, idempotency_key)
    db.add(CardMovement(operation_id=operation.id, card_id=card.id, amount=-obligation_amount, currency=obligation_currency))
    payment = CardPayment(
        operation_id=operation.id,
        user_id=user_id,
        card_id=card.id,
        source_account_id=source_account.id if source_account else None,
        obligation_amount=obligation_amount,
        obligation_currency=obligation_currency,
        source_amount=source_amount,
        source_currency=source_currency,
        exchange_rate=exchange_rate,
        fee_amount=fee_amount,
        fee_currency=source_currency if fee_amount else None,
        payment_date=payload.payment_date,
        notes=payload.notes,
    )
    db.add(payment)
    db.flush()
    remaining = obligation_amount
    for charge, outstanding in outstanding_charges(db, card.id, obligation_currency):
        if remaining <= 0:
            break
        applied = min(remaining, outstanding)
        db.add(CardPaymentAllocation(payment_id=payment.id, charge_id=charge.id, amount=applied))
        remaining -= applied
    db.flush()
    if source_account:
        assert source_currency is not None
        assert source_amount is not None
        payment_operation = create_operation(db, user_id, "card_principal_payment", payload.payment_date)
        total_source = source_amount + (fee_amount or 0)
        db.add(AccountMovement(operation_id=payment_operation.id, account_id=source_account.id, amount=-total_source, currency=source_currency))
        db.add(FinancialTransaction(
            operation_id=payment_operation.id,
            user_id=user_id,
            transaction_type="payment",
            amount=total_source,
            currency=source_currency,
            original_amount=obligation_amount if source_currency != obligation_currency else None,
            original_currency=obligation_currency if source_currency != obligation_currency else None,
            transaction_date=payload.payment_date,
            account_id=source_account.id,
            card_id=card.id,
            category_id=default_payment_category(db, user_id).id,
            payment_method="debit",
            description=f"Pago tarjeta: {card.name}",
        ))
    if payload.extra_charges and source_account:
        assert source_currency is not None
        assert exchange_rate is not None or source_currency == obligation_currency
        for charge in payload.extra_charges:
            category = get_owned_category(db, user_id, charge.category_id)
            ec_amount = normalize_amount(charge.amount, obligation_currency)
            charge_operation = create_operation(db, user_id, "card_extra_charge", payload.payment_date)
            if source_currency == obligation_currency:
                deduction = ec_amount
            else:
                assert exchange_rate is not None
                deduction = normalize_amount(ec_amount * exchange_rate, source_currency)
            db.add(AccountMovement(operation_id=charge_operation.id, account_id=source_account.id, amount=-deduction, currency=source_currency))
            db.add(FinancialTransaction(
                operation_id=charge_operation.id,
                user_id=user_id,
                transaction_type="expense",
                amount=deduction,
                currency=source_currency,
                original_amount=ec_amount if source_currency != obligation_currency else None,
                original_currency=obligation_currency if source_currency != obligation_currency else None,
                transaction_date=payload.payment_date,
                account_id=source_account.id,
                card_id=card.id,
                category_id=category.id,
                payment_method="credit",
                description=charge.description,
            ))
    return payment


def adjust_card_debt(db: Session, user_id: int, card_id: int, payload: CardBalanceAdjustmentCreate, idempotency_key: str | None = None) -> CreditCard:
    card = get_owned_card(db, user_id, card_id)
    currency = normalize_currency(payload.currency)
    supported_currency(db, card.id, currency)
    target = normalize_amount(payload.target_debt, currency, positive=False)
    difference = normalize_amount(target - card_debt(db, card.id, currency), currency, positive=False)
    if difference == 0:
        raise HTTPException(status_code=422, detail="La deuda ya coincide con el valor indicado")
    operation = create_operation(db, user_id, "card_balance_adjustment", payload.adjustment_date, idempotency_key)
    db.add(CardMovement(operation_id=operation.id, card_id=card.id, amount=difference, currency=currency))
    if difference > 0:
        db.add(CardCharge(user_id=user_id, card_id=card.id, charge_type="adjustment", amount=difference, currency=currency, charge_date=payload.adjustment_date, is_estimated=False, description=payload.description))
    db.flush()
    return card

from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.loan_schemas import LoanCreate, LoanPaymentCreate
from app.domain.loans import amortization_schedule
from app.domain.money import normalize_amount, normalize_currency
from app.models.ledger import AccountMovement, Category, FinancialTransaction
from app.models.loans import Loan, LoanInstallment, LoanMovement, LoanPayment
from app.services.ledger import account_balance, create_operation, get_owned_account, get_owned_category, not_found
from app.domain.enums import InstallmentStatus, LoanStatus, TransactionStatus


def get_owned_loan(db: Session, user_id: int, loan_id: int) -> Loan:
    loan = db.query(Loan).filter(Loan.id == loan_id, Loan.user_id == user_id, Loan.status == TransactionStatus.ACTIVE).one_or_none()
    if loan is None:
        raise not_found("Préstamo no encontrado")
    return loan


def outstanding_principal(db: Session, loan_id: int) -> Decimal:
    value = db.query(func.coalesce(func.sum(LoanMovement.amount), 0)).filter(LoanMovement.loan_id == loan_id).scalar()
    return Decimal(value or 0)


def close_loan(db: Session, user_id: int, loan_id: int) -> Loan:
    loan = get_owned_loan(db, user_id, loan_id)
    db.query(LoanInstallment).filter(
        LoanInstallment.loan_id == loan.id,
        LoanInstallment.status != InstallmentStatus.PAID,
    ).delete(synchronize_session=False)
    loan.status = LoanStatus.ARCHIVED
    return loan


def default_interest_category(db: Session, user_id: int) -> Category:
    category = db.query(Category).filter(Category.user_id == user_id, Category.name == "Otros gastos", Category.is_archived.is_(False)).one_or_none()
    if category:
        return category
    category = Category(user_id=user_id, name="Otros gastos", kind="expense")
    db.add(category)
    db.flush()
    return category


def default_income_category(db: Session, user_id: int) -> Category:
    category = db.query(Category).filter(Category.user_id == user_id, Category.name == "Otros ingresos", Category.is_archived.is_(False)).one_or_none()
    if category:
        return category
    category = Category(user_id=user_id, name="Otros ingresos", kind="income")
    db.add(category)
    db.flush()
    return category


def create_loan(db: Session, user_id: int, payload: LoanCreate) -> Loan:
    currency = normalize_currency(payload.currency)
    principal = normalize_amount(payload.principal_amount, currency)
    if payload.record_as_income and payload.source_account_id is None:
        raise HTTPException(status_code=422, detail="Un préstamo registrado como ingreso requiere una cuenta destino")
    source = get_owned_account(db, user_id, payload.source_account_id) if payload.source_account_id else None
    if source and source.currency != currency:
        raise HTTPException(status_code=422, detail="La cuenta destino debe usar la moneda del préstamo")
    monthly_rate, schedule = amortization_schedule(principal, currency, payload.annual_effective_rate, payload.term_months, payload.first_payment_date)
    interest_category = default_interest_category(db, user_id)
    income_category = default_income_category(db, user_id) if payload.record_as_income else None
    operation = create_operation(db, user_id, "loan_disbursement", payload.start_date)
    loan = Loan(
        operation_id=operation.id,
        user_id=user_id,
        source_account_id=source.id if source else None,
        interest_category_id=interest_category.id,
        name=payload.name.strip(),
        principal_amount=principal,
        currency=currency,
        annual_effective_rate=payload.annual_effective_rate,
        monthly_rate=monthly_rate,
        term_months=payload.term_months,
        start_date=payload.start_date,
        first_payment_date=payload.first_payment_date,
        record_as_income=payload.record_as_income,
    )
    db.add(loan)
    db.flush()
    db.add(LoanMovement(operation_id=operation.id, loan_id=loan.id, amount=principal, currency=currency, movement_type="principal_disbursement"))
    if source:
        db.add(AccountMovement(operation_id=operation.id, account_id=source.id, amount=principal, currency=currency))
    if payload.record_as_income:
        if source is None or income_category is None:
            raise HTTPException(status_code=422, detail="El préstamo requiere una cuenta y categoría de ingreso")
        db.add(FinancialTransaction(
            operation_id=operation.id,
            user_id=user_id,
            transaction_type="income",
            amount=principal,
            currency=currency,
            transaction_date=payload.start_date,
            account_id=source.id,
            category_id=income_category.id,
            payment_method="debit",
            description=f"Desembolso de préstamo: {loan.name}",
        ))
    for item in schedule:
        db.add(LoanInstallment(
            loan_id=loan.id,
            installment_number=item.number,
            due_date=item.due_date,
            principal_amount=item.principal,
            interest_amount=item.interest,
            total_amount=item.total,
        ))
    db.flush()
    return loan


def create_payment(db: Session, user_id: int, loan_id: int, payload: LoanPaymentCreate) -> LoanPayment:
    loan = get_owned_loan(db, user_id, loan_id)
    source = get_owned_account(db, user_id, payload.source_account_id)
    if source.currency != loan.currency:
        raise HTTPException(status_code=422, detail="La cuenta de pago debe usar la moneda del préstamo")
    balance = normalize_amount(outstanding_principal(db, loan.id), loan.currency, positive=False)
    if balance <= 0:
        raise HTTPException(status_code=422, detail="El préstamo ya está pagado")
    installment = db.query(LoanInstallment).filter(LoanInstallment.loan_id == loan.id, LoanInstallment.status != "paid").order_by(LoanInstallment.installment_number).first()
    if installment is None:
        raise HTTPException(status_code=422, detail="No hay cuotas pendientes")
    scheduled_amount = normalize_amount(payload.scheduled_amount or installment.total_amount, loan.currency)
    extra = normalize_amount(payload.extra_principal, loan.currency, positive=False)
    if payload.interest_paid is not None:
        interest_paid = normalize_amount(payload.interest_paid, loan.currency, positive=False)
    else:
        interest_paid = min(Decimal(installment.interest_amount), scheduled_amount)
    if interest_paid > scheduled_amount:
        raise HTTPException(status_code=422, detail="El interés pagado no puede superar el monto programado")
    principal_paid = scheduled_amount - interest_paid
    total = scheduled_amount + extra
    extra_charge_total = sum(
        (normalize_amount(charge.amount, loan.currency) for charge in payload.extra_charges or []),
        Decimal("0"),
    )
    if total + extra_charge_total > account_balance(db, source):
        raise HTTPException(status_code=422, detail="El pago supera el saldo disponible de la cuenta")
    if principal_paid > balance:
        raise HTTPException(status_code=422, detail="El abono supera el capital pendiente")
    operation = create_operation(db, user_id, "loan_payment", payload.payment_date)
    db.add(LoanMovement(operation_id=operation.id, loan_id=loan.id, amount=-principal_paid - extra, currency=loan.currency, movement_type="principal_payment"))
    payment = LoanPayment(
        operation_id=operation.id,
        loan_id=loan.id,
        source_account_id=source.id,
        payment_date=payload.payment_date,
        scheduled_amount=scheduled_amount,
        principal_paid=principal_paid,
        interest_paid=interest_paid,
        extra_principal=extra,
        total_amount=total,
        notes=payload.notes,
    )
    db.add(payment)
    if interest_paid > 0:
        interest_operation = create_operation(db, user_id, "loan_interest", payload.payment_date)
        db.add(AccountMovement(operation_id=interest_operation.id, account_id=source.id, amount=-interest_paid, currency=loan.currency))
        db.add(FinancialTransaction(
            operation_id=interest_operation.id,
            user_id=user_id,
            transaction_type="expense",
            amount=interest_paid,
            currency=loan.currency,
            transaction_date=payload.payment_date,
            account_id=source.id,
            category_id=loan.interest_category_id,
            payment_method="debit",
            description=f"Interés de préstamo: {loan.name}",
        ))
    principal_total = principal_paid + extra
    if principal_total > 0:
        principal_operation = create_operation(db, user_id, "loan_principal_payment", payload.payment_date)
        db.add(AccountMovement(operation_id=principal_operation.id, account_id=source.id, amount=-principal_total, currency=loan.currency))
        db.add(FinancialTransaction(
            operation_id=principal_operation.id,
            user_id=user_id,
            transaction_type="payment",
            amount=principal_total,
            currency=loan.currency,
            transaction_date=payload.payment_date,
            account_id=source.id,
            category_id=loan.interest_category_id,
            payment_method="debit",
            description=f"Abono a capital: {loan.name}",
        ))
    if scheduled_amount >= installment.total_amount and extra == 0:
        installment.status = InstallmentStatus.PAID
    else:
        installment.status = InstallmentStatus.PARTIAL
    db.flush()
    if principal_total >= balance:
        loan.status = LoanStatus.ARCHIVED
        db.query(LoanInstallment).filter(
            LoanInstallment.loan_id == loan.id,
            LoanInstallment.status != InstallmentStatus.PAID,
        ).delete(synchronize_session=False)
        db.flush()
    if payload.extra_charges:
        for charge in payload.extra_charges:
            category = get_owned_category(db, user_id, charge.category_id)
            ec_amount = normalize_amount(charge.amount, loan.currency)
            charge_operation = create_operation(db, user_id, "loan_extra_charge", payload.payment_date)
            db.add(AccountMovement(operation_id=charge_operation.id, account_id=source.id, amount=-ec_amount, currency=loan.currency))
            db.add(FinancialTransaction(
                operation_id=charge_operation.id,
                user_id=user_id,
                transaction_type="expense",
                amount=ec_amount,
                currency=loan.currency,
                transaction_date=payload.payment_date,
                account_id=source.id,
                category_id=category.id,
                payment_method="debit",
                description=charge.description,
            ))
    return payment

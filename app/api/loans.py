from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context, require_csrf
from app.api.loan_schemas import LoanCreate, LoanInstallmentResponse, LoanPaymentCreate, LoanPaymentResponse, LoanResponse, LoanUpdate
from app.db.session import get_db
from app.domain.money import normalize_amount
from app.models.loans import Loan, LoanInstallment
from app.services.loans import close_loan, create_loan, create_payment, get_owned_loan, outstanding_principal
from app.domain.enums import LoanStatus, TransactionStatus
from app.api.pagination import Pagination

router = APIRouter(prefix="/api/loans", tags=["loans"])


def loan_response(db: Session, loan: Loan) -> LoanResponse:
    installments = db.query(LoanInstallment).filter(LoanInstallment.loan_id == loan.id).order_by(LoanInstallment.installment_number).all()
    return LoanResponse(
        id=loan.id,
        name=loan.name,
        principal_amount=loan.principal_amount,
        outstanding_principal=normalize_amount(outstanding_principal(db, loan.id), loan.currency, positive=False),
        currency=loan.currency,
        annual_effective_rate=loan.annual_effective_rate,
        monthly_rate=loan.monthly_rate,
        term_months=loan.term_months,
        start_date=loan.start_date,
        first_payment_date=loan.first_payment_date,
        record_as_income=loan.record_as_income,
        status=loan.status,
        installments=[LoanInstallmentResponse.model_validate(item, from_attributes=True) for item in installments],
    )


@router.get("", response_model=list[LoanResponse])
def list_loans(
    archived: bool = Query(False),
    pagination: Pagination = Depends(),
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    target_status = LoanStatus.ARCHIVED if archived else TransactionStatus.ACTIVE
    loans = db.query(Loan).filter(Loan.user_id == context.user.id, Loan.status == target_status).order_by(Loan.start_date.desc()).offset(pagination.offset).limit(pagination.limit).all()
    return [loan_response(db, loan) for loan in loans]


@router.post("", response_model=LoanResponse, status_code=status.HTTP_201_CREATED)
def create_new_loan(payload: LoanCreate, context: AuthContext = Depends(require_csrf), db: Session = Depends(get_db)):
    loan = create_loan(db, context.user.id, payload)
    db.commit()
    db.refresh(loan)
    return loan_response(db, loan)


@router.get("/{loan_id}", response_model=LoanResponse)
def get_loan(loan_id: int, context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    return loan_response(db, get_owned_loan(db, context.user.id, loan_id))


@router.post("/{loan_id}/payments", response_model=LoanPaymentResponse, status_code=status.HTTP_201_CREATED)
def pay_loan(
    loan_id: int,
    payload: LoanPaymentCreate,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    payment = create_payment(db, context.user.id, loan_id, payload)
    db.commit()
    db.refresh(payment)
    return LoanPaymentResponse.model_validate(payment, from_attributes=True)


@router.patch("/{loan_id}", response_model=LoanResponse)
def update_loan(loan_id: int, payload: LoanUpdate, context: AuthContext = Depends(require_csrf), db: Session = Depends(get_db)):
    loan = get_owned_loan(db, context.user.id, loan_id)
    if any(
        value is not None
        for value in (
            payload.annual_effective_rate,
            payload.term_months,
            payload.start_date,
            payload.first_payment_date,
            payload.record_as_income,
        )
    ):
        raise HTTPException(
            status_code=422,
            detail="La tasa, el plazo, las fechas y el registro como ingreso son inmutables; cierre el préstamo para detenerlo",
        )
    if payload.name is not None:
        loan.name = payload.name.strip()
    db.commit()
    db.refresh(loan)
    return loan_response(db, loan)


@router.post("/{loan_id}/archive", response_model=LoanResponse)
def archive_loan(loan_id: int, context: AuthContext = Depends(require_csrf), db: Session = Depends(get_db)):
    loan = close_loan(db, context.user.id, loan_id)
    db.commit()
    db.refresh(loan)
    return loan_response(db, loan)


@router.post("/{loan_id}/close", response_model=LoanResponse)
def close_existing_loan(loan_id: int, context: AuthContext = Depends(require_csrf), db: Session = Depends(get_db)):
    loan = close_loan(db, context.user.id, loan_id)
    db.commit()
    db.refresh(loan)
    return loan_response(db, loan)

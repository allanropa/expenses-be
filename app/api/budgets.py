from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.budget_schemas import AlertResponse, BudgetCreate, BudgetResponse, BudgetSummary, BudgetUpdate
from app.api.deps import AuthContext, get_auth_context, require_csrf
from app.db.session import get_db
from app.models.budgets import Alert, Budget
from app.domain.money import normalize_amount
from app.services.budgets import calculate_summary, create_budget, maybe_alert

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


def owned_budget(db: Session, user_id: int, budget_id: int) -> Budget:
    budget = db.query(Budget).filter(Budget.id == budget_id, Budget.user_id == user_id, Budget.is_archived.is_(False)).one_or_none()
    if budget is None:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
    return budget


@router.get("", response_model=list[BudgetResponse])
def list_budgets(context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    return db.query(Budget).filter(Budget.user_id == context.user.id, Budget.is_archived.is_(False)).order_by(Budget.start_date.desc()).all()


@router.post("", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
def create_new_budget(payload: BudgetCreate, context: AuthContext = Depends(require_csrf), db: Session = Depends(get_db)):
    budget = create_budget(db, context.user.id, payload)
    db.commit()
    db.refresh(budget)
    return budget


@router.get("/{budget_id}/summary", response_model=BudgetSummary)
def budget_summary(
    budget_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    budget = owned_budget(db, context.user.id, budget_id)
    summary = calculate_summary(db, budget, date_from, date_to)
    maybe_alert(db, budget, summary)
    db.commit()
    return summary


@router.get("/{budget_id}", response_model=BudgetResponse)
def get_budget(budget_id: int, context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    return owned_budget(db, context.user.id, budget_id)


@router.patch("/{budget_id}", response_model=BudgetResponse)
def update_budget(
    budget_id: int,
    payload: BudgetUpdate,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    budget = owned_budget(db, context.user.id, budget_id)
    if payload.start_date and payload.end_date and payload.end_date < payload.start_date:
        raise HTTPException(status_code=422, detail="El final no puede preceder al inicio")
    if payload.name is not None:
        budget.name = payload.name.strip()
    if payload.target_amount is not None:
        budget.target_amount = normalize_amount(payload.target_amount, budget.currency)
    if payload.budget_type is not None:
        budget.budget_type = payload.budget_type
    if payload.period_type is not None:
        budget.period_type = payload.period_type
    if payload.scope is not None:
        budget.scope = payload.scope
    if payload.spending_type is not None:
        budget.spending_type = payload.spending_type
    if payload.category_id is not None:
        budget.category_id = payload.category_id
    if payload.account_id is not None:
        budget.account_id = payload.account_id
    if payload.card_id is not None:
        budget.card_id = payload.card_id
    if payload.eligible_weekdays is not None:
        budget.eligible_weekdays = payload.eligible_weekdays
    if payload.start_date is not None:
        budget.start_date = payload.start_date
    if payload.end_date is not None:
        budget.end_date = payload.end_date
    if budget.end_date < budget.start_date:
        raise HTTPException(status_code=422, detail="El final no puede preceder al inicio")
    if payload.alert_threshold is not None:
        budget.alert_threshold = payload.alert_threshold
    db.commit()
    db.refresh(budget)
    return budget


@router.post("/{budget_id}/archive", response_model=BudgetResponse)
def archive_budget(budget_id: int, context: AuthContext = Depends(require_csrf), db: Session = Depends(get_db)):
    budget = owned_budget(db, context.user.id, budget_id)
    budget.is_archived = True
    db.commit()
    return budget


@router.get("/alerts", response_model=list[AlertResponse])
def list_alerts(context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    return db.query(Alert).filter(Alert.user_id == context.user.id).order_by(Alert.created_at.desc()).all()


@router.post("/alerts/{alert_id}/read", response_model=AlertResponse)
def mark_alert_read(alert_id: int, context: AuthContext = Depends(require_csrf), db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id, Alert.user_id == context.user.id).one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    from datetime import datetime, timezone

    alert.read_at = datetime.now(timezone.utc)
    db.commit()
    return alert

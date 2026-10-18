from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_csrf, get_auth_context
from app.api.schemas import SettingsResponse, SettingsUpdateRequest
from app.db.session import get_db

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
def get_settings(context: AuthContext = Depends(get_auth_context)) -> SettingsResponse:
    return SettingsResponse(
        reporting_currency=context.user.settings.reporting_currency,
        timezone=context.user.settings.timezone,
    )


@router.patch("", response_model=SettingsResponse)
def update_settings(
    payload: SettingsUpdateRequest,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> SettingsResponse:
    if payload.reporting_currency is not None:
        context.user.settings.reporting_currency = payload.reporting_currency
    if payload.timezone is not None:
        context.user.settings.timezone = payload.timezone
    db.commit()
    return SettingsResponse(
        reporting_currency=context.user.settings.reporting_currency,
        timezone=context.user.settings.timezone,
    )

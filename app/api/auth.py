
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context, require_csrf
from app.api.schemas import (
    LoginRequest,
    PasswordChangeRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    SessionResponse,
    UserResponse,
)
from app.core.config import settings
from app.core.security import hash_password, new_session_values, verify_password
from app.core.rate_limit import check_login_allowed, clear_login_failures, record_login_failure
from app.db.session import get_db
from app.domain.default_categories import DEFAULT_CATEGORIES
from app.models.auth import AuthSession, User, UserSettings
from app.models.ledger import Category

router = APIRouter(prefix="/api/auth", tags=["auth"])


def create_auth_session(db: Session, user: User) -> tuple[AuthSession, str]:
    db.query(AuthSession).filter(
        AuthSession.user_id == user.id,
        (AuthSession.revoked_at.is_not(None) | (AuthSession.expires_at <= datetime.now(timezone.utc))),
    ).delete(synchronize_session=False)
    raw_token, token_hash, csrf_token, expires_at = new_session_values()
    session = AuthSession(user_id=user.id, token_hash=token_hash, csrf_token=csrf_token, expires_at=expires_at)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session, raw_token


def set_session_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )


@router.post("/register", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)) -> SessionResponse:
    user = User(
        email=str(payload.email).lower(),
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip(),
    )
    user.settings = UserSettings()
    db.add(user)
    try:
        db.flush()
        db.add_all([Category(user_id=user.id, name=name, kind=kind) for name, kind in DEFAULT_CATEGORIES])
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El correo ya está registrado") from None
    db.refresh(user)
    session, raw_token = create_auth_session(db, user)
    set_session_cookie(response, raw_token)
    return SessionResponse(user=UserResponse.model_validate(user), csrf_token=session.csrf_token)


@router.post("/login", response_model=SessionResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> SessionResponse:
    email = str(payload.email).lower()
    ip = request.client.host if request.client else "unknown"
    if not check_login_allowed(ip, email):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Demasiados intentos de inicio de sesión")
    user = db.query(User).filter(User.email == email).one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        record_login_failure(ip, email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Correo o contraseña inválidos")
    clear_login_failures(ip, email)
    session, raw_token = create_auth_session(db, user)
    set_session_cookie(response, raw_token)
    return SessionResponse(user=UserResponse.model_validate(user), csrf_token=session.csrf_token)


@router.get("/session", response_model=SessionResponse)
def session(context: AuthContext = Depends(get_auth_context)) -> SessionResponse:
    return SessionResponse(user=UserResponse.model_validate(context.user), csrf_token=context.session.csrf_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, context: AuthContext = Depends(require_csrf), db: Session = Depends(get_db)) -> Response:
    context.session.revoked_at = context.session.created_at
    db.commit()
    response.delete_cookie(settings.session_cookie_name)
    return response


@router.patch("/profile", response_model=UserResponse)
def update_profile(
    payload: ProfileUpdateRequest,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> UserResponse:
    context.user.display_name = payload.display_name.strip()
    db.commit()
    db.refresh(context.user)
    return UserResponse.model_validate(context.user)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Response:
    if not verify_password(payload.current_password, context.user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La contraseña actual es inválida")
    context.user.password_hash = hash_password(payload.new_password)
    db.query(AuthSession).filter(
        AuthSession.user_id == context.user.id,
        AuthSession.id != context.session.id,
        AuthSession.revoked_at.is_(None),
    ).update({AuthSession.revoked_at: context.session.created_at}, synchronize_session=False)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

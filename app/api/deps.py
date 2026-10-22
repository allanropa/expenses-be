import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import tokens_match
from app.db.session import get_db
from app.models.auth import AuthSession, User


@dataclass
class AuthContext:
    user: User
    session: AuthSession


def get_auth_context(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticación requerida")

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    session = db.query(AuthSession).filter(AuthSession.token_hash == token_hash).one_or_none()
    now = datetime.now(timezone.utc)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida o expirada")
    expires_at = session.expires_at.replace(tzinfo=timezone.utc) if session.expires_at.tzinfo is None else session.expires_at
    if session.revoked_at is not None or expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida o expirada")
    if not session.user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inactivo")
    return AuthContext(user=session.user, session=session)


def require_csrf(request: Request, context: AuthContext = Depends(get_auth_context)) -> AuthContext:
    received = request.headers.get("X-CSRF-Token")
    if not tokens_match(context.session.csrf_token, received):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token CSRF inválido")
    return context

"""Endpoint di autenticazione. Nessuna registrazione pubblica."""
from __future__ import annotations

import time

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.audit import audit
from app.core.security import SESSION_COOKIE, ensure_admin_user, login, logout
from app.db import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])

# rate limiting minimo per IP sul login (in-memory, sufficiente mono-utente)
_attempts: dict[str, list[float]] = {}
_WINDOW_S = 60.0
_MAX_PER_WINDOW = 10


def _rate_limit(ip: str) -> None:
    now = time.monotonic()
    bucket = [t for t in _attempts.get(ip, []) if now - t < _WINDOW_S]
    if len(bucket) >= _MAX_PER_WINDOW:
        raise HTTPException(status_code=429, detail="Troppi tentativi. Riprovare più tardi.")
    bucket.append(now)
    _attempts[ip] = bucket


class LoginRequest(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)


@router.post("/login")
def do_login(payload: LoginRequest, request: Request, response: Response,
             db: Session = Depends(get_db)):
    settings = get_settings()
    if settings.auth_disabled:
        return {"authenticated": True, "auth_disabled": True, "csrf_token": None}
    _rate_limit(request.client.host if request.client else "unknown")
    ensure_admin_user(db)
    token, csrf = login(db, payload.username, payload.password)
    response.set_cookie(
        SESSION_COOKIE, token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    audit(db, actor=payload.username, action="login")
    db.commit()
    return {"authenticated": True, "csrf_token": csrf}


@router.post("/logout")
def do_logout(response: Response, db: Session = Depends(get_db),
              session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    if session_token:
        logout(db, session_token)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"authenticated": False}


@router.get("/me")
def me(db: Session = Depends(get_db), request: Request = None,
       session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    """Stato sessione senza sollevare 401 (il frontend decide il redirect)."""
    settings = get_settings()
    if settings.auth_disabled:
        return {"authenticated": True, "auth_disabled": True, "username": settings.admin_username,
                "mode": settings.app_mode}
    from app.core.security import _get_valid_session  # uso interno consapevole
    sess = _get_valid_session(db, session_token)
    if sess is None:
        return {"authenticated": False, "mode": settings.app_mode}
    return {"authenticated": True, "username": settings.admin_username,
            "csrf_token": sess.csrf_token, "mode": settings.app_mode}

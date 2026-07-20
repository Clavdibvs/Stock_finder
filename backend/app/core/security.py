"""Accesso privato mono-utente.

- un solo account amministratore, nessuna registrazione;
- password con hash Argon2id;
- sessione opaca: nel DB si conserva solo l'hash SHA-256 del token;
- cookie HttpOnly + Secure + SameSite=Strict;
- CSRF double-submit token per i metodi mutanti;
- lockout temporaneo dopo tentativi falliti;
- login disattivabile (DDR_AUTH_DISABLED=true) quando l'istanza è protetta
  da Tailscale o access proxy.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Cookie, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import AuthSession, User, utcnow

_hasher = PasswordHasher()

SESSION_COOKIE = "ddr_session"

# messaggio unico e non informativo per ogni fallimento di login
LOGIN_FAILED_MSG = "Credenziali non valide"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def ensure_admin_user(db: Session) -> User | None:
    """Crea l'unico utente admin dalla config, se non esiste. Nessuna registrazione."""
    settings = get_settings()
    user = db.scalar(select(User).where(User.username == settings.admin_username))
    if user is None:
        if not settings.admin_password:
            return None  # verrà creato dal bootstrap
        user = User(
            username=settings.admin_username,
            password_hash=hash_password(settings.admin_password),
        )
        db.add(user)
        db.commit()
    return user


def login(db: Session, username: str, password: str) -> tuple[str, str]:
    """Ritorna (session_token, csrf_token) o solleva 401/429.

    Messaggi d'errore volutamente non informativi: non rivelano se esiste
    l'utente o se l'account è bloccato per lockout.
    """
    settings = get_settings()
    user = db.scalar(select(User).where(User.username == username))
    now = utcnow()

    if user is None:
        # confronto fittizio per uniformare i tempi di risposta
        verify_password(hash_password("x"), password)
        raise HTTPException(status_code=401, detail=LOGIN_FAILED_MSG)

    if user.locked_until is not None and user.locked_until > now:
        raise HTTPException(status_code=429, detail=LOGIN_FAILED_MSG)

    if not verify_password(user.password_hash, password):
        user.failed_attempts += 1
        if user.failed_attempts >= settings.login_max_attempts:
            user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
            user.failed_attempts = 0
        db.commit()
        raise HTTPException(status_code=401, detail=LOGIN_FAILED_MSG)

    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    db.add(AuthSession(
        token_hash=_token_hash(token),
        user_id=user.id,
        csrf_token=csrf,
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
    ))
    db.commit()
    return token, csrf


def logout(db: Session, token: str) -> None:
    sess = db.get(AuthSession, _token_hash(token))
    if sess is not None:
        sess.revoked_at = utcnow()
        db.commit()


def _get_valid_session(db: Session, token: str | None) -> AuthSession | None:
    if not token:
        return None
    sess = db.get(AuthSession, _token_hash(token))
    if sess is None or sess.revoked_at is not None:
        return None
    expires = sess.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires < datetime.now(UTC):
        return None
    return sess


def require_auth(
    request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None),
) -> str:
    """Dependency per gli endpoint privati. Ritorna lo username autenticato."""
    settings = get_settings()
    if settings.auth_disabled:
        return settings.admin_username

    sess = _get_valid_session(db, session_token)
    if sess is None:
        raise HTTPException(status_code=401, detail="Autenticazione richiesta")

    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if not x_csrf_token or not hmac.compare_digest(x_csrf_token, sess.csrf_token):
            raise HTTPException(status_code=403, detail="Token CSRF mancante o non valido")

    user = db.get(User, sess.user_id)
    return user.username if user else settings.admin_username

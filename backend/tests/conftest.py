"""Fixture condivise: DB in-memory, client demo, client con auth."""
from __future__ import annotations

import os

# ambiente di default per TUTTI i test, impostato prima di ogni import app
os.environ.setdefault("DDR_DATABASE_URL", "sqlite://")
os.environ.setdefault("DDR_APP_MODE", "demo")
os.environ.setdefault("DDR_AUTH_DISABLED", "true")
os.environ.setdefault("DDR_COOKIE_SECURE", "false")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db import reset_engine
from app.models import Base


@pytest.fixture
def db():
    """DB SQLite in-memory isolato, senza passare dall'engine globale."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _fresh_env(**overrides):
    env = {
        "DDR_DATABASE_URL": "sqlite://",
        "DDR_APP_MODE": "demo",
        "DDR_AUTH_DISABLED": "true",
        "DDR_COOKIE_SECURE": "false",
        "DDR_ADMIN_PASSWORD": "",
        "DDR_SESSION_SECRET": "test-secret",
    }
    env.update(overrides)
    for k, v in env.items():
        os.environ[k] = v
    get_settings.cache_clear()
    reset_engine()


@pytest.fixture(scope="session")
def demo_client():
    """App completa in modalità demo (seed incluso). Condivisa: sola lettura."""
    _fresh_env()
    from app.main import app
    with TestClient(app) as client:
        yield client
    _fresh_env()


@pytest.fixture
def auth_client():
    """App con autenticazione attiva e utente admin."""
    _fresh_env(DDR_AUTH_DISABLED="false", DDR_ADMIN_PASSWORD="test-password-123",
               DDR_APP_MODE="demo")
    from app.api.auth import _attempts
    _attempts.clear()  # il rate limiter in-memory non deve trapelare tra i test
    from app.main import app
    with TestClient(app) as client:
        yield client
    _fresh_env()

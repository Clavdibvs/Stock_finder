"""Protezione endpoint privati, login rate limiting, lockout, CSRF."""
from __future__ import annotations

PROTECTED = [
    "/api/dashboard", "/api/watchlist", "/api/quality",
    "/api/settings", "/api/sources/registry", "/api/sources/claims",
]


class TestEndpointProtection:
    def test_all_private_endpoints_require_auth(self, auth_client):
        for path in PROTECTED:
            r = auth_client.get(path)
            assert r.status_code == 401, f"{path} deve richiedere autenticazione"

    def test_health_is_public(self, auth_client):
        assert auth_client.get("/api/health").status_code == 200

    def test_no_registration_endpoint(self, auth_client):
        """Nessuna registrazione pubblica, in nessuna variante."""
        for path in ["/api/auth/register", "/api/auth/signup", "/api/register",
                     "/api/users", "/register", "/signup"]:
            r = auth_client.post(path, json={"username": "x", "password": "y"})
            assert r.status_code in (404, 405), f"{path} non deve esistere"

    def test_no_api_docs_exposed(self, auth_client):
        for path in ["/docs", "/redoc", "/openapi.json"]:
            assert auth_client.get(path).status_code == 404


class TestLogin:
    def test_login_success_sets_cookie(self, auth_client):
        r = auth_client.post("/api/auth/login",
                             json={"username": "admin", "password": "test-password-123"})
        assert r.status_code == 200
        assert r.json()["authenticated"] is True
        assert r.json()["csrf_token"]
        assert "ddr_session" in r.cookies

    def test_login_failure_generic_message(self, auth_client):
        """Messaggio non informativo: non rivela se l'utente esiste."""
        r1 = auth_client.post("/api/auth/login",
                              json={"username": "admin", "password": "sbagliata"})
        r2 = auth_client.post("/api/auth/login",
                              json={"username": "utente-inesistente", "password": "x"})
        assert r1.status_code == 401 and r2.status_code == 401
        assert r1.json()["detail"] == r2.json()["detail"]
        assert "admin" not in r1.json()["detail"].lower()

    def test_lockout_after_failed_attempts(self, auth_client):
        """Blocco temporaneo dopo ripetuti tentativi falliti."""
        for _ in range(5):
            auth_client.post("/api/auth/login",
                             json={"username": "admin", "password": "sbagliata"})
        r = auth_client.post("/api/auth/login",
                             json={"username": "admin", "password": "test-password-123"})
        assert r.status_code == 429  # anche la password giusta è bloccata

    def test_session_grants_access(self, auth_client):
        auth_client.post("/api/auth/login",
                         json={"username": "admin", "password": "test-password-123"})
        assert auth_client.get("/api/dashboard").status_code == 200

    def test_csrf_required_for_mutations(self, auth_client):
        login = auth_client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "test-password-123"})
        csrf = login.json()["csrf_token"]
        # senza header CSRF -> 403
        r = auth_client.post("/api/watchlist", json={"security_id": 1})
        assert r.status_code == 403
        # con header -> passa il controllo CSRF (404: security inesistente)
        r = auth_client.post("/api/watchlist", json={"security_id": 999999},
                             headers={"X-CSRF-Token": csrf})
        assert r.status_code == 404

    def test_ip_rate_limit(self, auth_client):
        """Rate limiting sul login: oltre 10 richieste/minuto -> 429."""
        last = None
        for _ in range(11):
            last = auth_client.post("/api/auth/login",
                                    json={"username": "x", "password": "y"})
        assert last.status_code == 429

    def test_logout_revokes_session(self, auth_client):
        auth_client.post("/api/auth/login",
                         json={"username": "admin", "password": "test-password-123"})
        assert auth_client.get("/api/dashboard").status_code == 200
        auth_client.post("/api/auth/logout")
        assert auth_client.get("/api/dashboard").status_code == 401

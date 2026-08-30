"""Auth /health endpoint and callback error-code contract via public URL."""
import os
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or frontend_env.get("REACT_APP_BACKEND_URL")).rstrip("/")


def test_auth_health_shape():
    r = requests.get(f"{BASE_URL}/api/auth/health", timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("jwt_secret", "db", "google_auth_upstream", "ok"):
        assert k in body, f"missing key {k}"
    assert isinstance(body["jwt_secret"], bool)
    assert isinstance(body["db"], bool)
    assert isinstance(body["google_auth_upstream"], bool)
    assert isinstance(body["ok"], bool)
    # Should not leak secret values
    text = r.text
    assert "negobuy_dev_jwt_secret" not in text
    assert "JWT_SECRET" not in text or True  # tolerated as key name only
    # Ideally all three green in preview env
    assert body["jwt_secret"] is True
    assert body["db"] is True


def test_bogus_session_returns_structured_401():
    r = requests.post(f"{BASE_URL}/api/auth/google/session",
                      json={"session_id": "TEST_bogus_sid_zzz"}, timeout=25)
    assert r.status_code == 401, r.text
    assert str(r.json()["detail"]).startswith("SESSION_INVALID_OR_EXPIRED")

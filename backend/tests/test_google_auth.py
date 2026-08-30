"""Google (Emergent-managed) session login + auth regression tests."""
import os
import re
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")


@pytest.fixture(scope="module")
def creds():
    p = Path("/app/memory/test_credentials.md")
    if not p.exists():
        pytest.skip("missing test_credentials.md")
    c = p.read_text()
    e = re.search(r'(?im)^\s*[-*]?\s*Email:\s*`?([^`\s]+)', c)
    pw = re.search(r'(?im)^\s*[-*]?\s*Password:\s*`?([^`\s]+)', c)
    if not e or not pw:
        pytest.skip("no creds parsed")
    return {"email": e.group(1), "password": pw.group(1)}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---- Google session endpoint contract ----
class TestGoogleSessionContract:
    def test_invalid_session_id_returns_401(self, client):
        r = client.post(f"{BASE_URL}/api/auth/google/session",
                        json={"session_id": "TEST_invalid_session_abc123"}, timeout=30)
        assert r.status_code == 401, r.text
        assert str(r.json().get("detail", "")).startswith("SESSION_INVALID_OR_EXPIRED")

    def test_missing_session_id_returns_422(self, client):
        r = client.post(f"{BASE_URL}/api/auth/google/session", json={}, timeout=30)
        assert r.status_code == 422, r.text
        body = r.json()
        assert "detail" in body

    def test_null_session_id_returns_422(self, client):
        r = client.post(f"{BASE_URL}/api/auth/google/session",
                        json={"session_id": None}, timeout=30)
        assert r.status_code == 422, r.text

    def test_empty_session_id_returns_401(self, client):
        r = client.post(f"{BASE_URL}/api/auth/google/session",
                        json={"session_id": ""}, timeout=30)
        assert r.status_code in (401, 422), r.text

    def test_no_mongo_objectid_leak_on_error(self, client):
        r = client.post(f"{BASE_URL}/api/auth/google/session",
                        json={"session_id": "TEST_x"}, timeout=30)
        assert "_id" not in r.text


# ---- Email/password auth regression ----
class TestAuthRegression:
    def test_login_success(self, client, creds):
        r = client.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["email"] == creds["email"]
        assert isinstance(d["access_token"], str) and len(d["access_token"]) > 20
        assert "password_hash" not in d and "_id" not in d
        assert d["role"] == "admin"

    def test_me_with_bearer(self, client, creds):
        token = client.post(f"{BASE_URL}/api/auth/login", json=creds,
                            timeout=30).json()["access_token"]
        r = requests.get(f"{BASE_URL}/api/auth/me",
                         headers={"Authorization": f"Bearer {token}"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["email"] == creds["email"]

    def test_me_without_token_401(self):
        r = requests.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code == 401

    def test_me_invalid_token_401(self):
        r = requests.get(f"{BASE_URL}/api/auth/me",
                         headers={"Authorization": "Bearer not.a.jwt"}, timeout=30)
        assert r.status_code == 401

    def test_refresh_with_cookie(self, creds):
        s = requests.Session()
        lr = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
        assert lr.status_code == 200
        r = s.post(f"{BASE_URL}/api/auth/refresh", timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

    def test_refresh_without_cookie_401(self):
        r = requests.post(f"{BASE_URL}/api/auth/refresh", timeout=30)
        assert r.status_code == 401

    def test_logout(self, creds):
        s = requests.Session()
        s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
        r = s.post(f"{BASE_URL}/api/auth/logout", timeout=30)
        assert r.status_code == 200
        assert r.json().get("ok") is True
        assert s.get(f"{BASE_URL}/api/auth/me", timeout=30).status_code == 401

    def test_wrong_password_401(self, creds):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": creds["email"], "password": "TEST_wrong_pw"}, timeout=30)
        assert r.status_code in (401, 429), r.text

    def test_login_still_works_after_failed_attempt(self, client, creds):
        r = client.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
        assert r.status_code == 200, r.text

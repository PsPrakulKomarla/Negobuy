"""In-process monkeypatched tests for Emergent Google session login.

Uses httpx.AsyncClient + ASGITransport inside a single asyncio.run per test to
avoid Motor "Event loop is closed" issues that TestClient triggers by creating
a fresh loop for every request.
"""
import os
import sys
import uuid
import asyncio
import pytest

sys.path.insert(0, "/app/backend")

os.environ.setdefault("REACT_APP_BACKEND_URL", "http://localhost:8001")

import httpx  # noqa: E402
import auth as auth_module  # noqa: E402
import db as db_module  # noqa: E402
from server import app  # noqa: E402


class _FakeResp:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


_ORIG_ASYNC_CLIENT = httpx.AsyncClient


class _FakeAsyncClient:
    _next_response = None  # _FakeResp or Exception

    def __new__(cls, *a, **kw):
        # If caller passes a transport (e.g. our ASGITransport in tests), delegate
        # to the real httpx.AsyncClient so the test HTTP calls still work.
        if "transport" in kw:
            return _ORIG_ASYNC_CLIENT(*a, **kw)
        return object.__new__(cls)

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None, **kw):
        resp = _FakeAsyncClient._next_response
        if isinstance(resp, Exception):
            raise resp
        return resp


@pytest.fixture(autouse=True)
def _patch_and_reset(monkeypatch):
    # Patch httpx.AsyncClient reference used inside auth.google_session
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    # Reset idempotency cache
    auth_module._gsession_cache.clear()
    # Reset motor client so it binds to the fresh event loop of each test
    db_module._client = None
    db_module._db = None
    yield
    auth_module._gsession_cache.clear()
    db_module._client = None
    db_module._db = None


async def _post(client, path, json_body):
    return await client.post(path, json=json_body)


async def _get(client, path, headers=None):
    return await client.get(path, headers=headers or {})


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _cleanup_email(email):
    db = db_module.get_db()
    u = await db.users.find_one({"email": email.lower()})
    if u:
        await db.users.delete_one({"id": u["id"]})
        await db.organizations.delete_one({"id": u.get("organization_id")})
        await db.memberships.delete_many({"user_id": u["id"]})


def test_new_user_blank_name():
    email = f"newg_{uuid.uuid4().hex[:8]}@example.com"
    _FakeAsyncClient._next_response = _FakeResp(200, {
        "email": email, "name": "", "picture": None,
    })
    sid = f"TEST_sid_{uuid.uuid4().hex}"

    async def _flow():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/auth/google/session", json={"session_id": sid})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["email"] == email
            assert body["name"] == email.split("@")[0]
            assert body.get("organization_name")
            assert isinstance(body["access_token"], str) and len(body["access_token"]) > 20

            me = await c.get("/api/auth/me",
                             headers={"Authorization": f"Bearer {body['access_token']}"})
            assert me.status_code == 200
            assert me.json()["email"] == email

            # Idempotency
            r2 = await c.post("/api/auth/google/session", json={"session_id": sid})
            assert r2.status_code == 200
            assert r2.json()["email"] == email
        await _cleanup_email(email)

    _run(_flow())


def test_new_user_whitespace_name_falls_back():
    email = f"newg_{uuid.uuid4().hex[:8]}@example.com"
    _FakeAsyncClient._next_response = _FakeResp(200, {
        "email": email, "name": "   ", "picture": "http://x/y.png",
    })

    async def _flow():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/auth/google/session",
                             json={"session_id": f"TEST_{uuid.uuid4().hex}"})
            assert r.status_code == 200, r.text
            assert r.json()["name"] == email.split("@")[0]
        await _cleanup_email(email)

    _run(_flow())


def test_existing_admin_login_via_google_no_duplicate():
    _FakeAsyncClient._next_response = _FakeResp(200, {
        "email": "admin@negobuy.ai", "name": "NegoBuy Admin", "picture": None,
    })

    async def _flow():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/auth/google/session",
                             json={"session_id": f"TEST_{uuid.uuid4().hex}"})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["email"] == "admin@negobuy.ai"
            assert body["role"] == "admin"
            db = db_module.get_db()
            cnt = await db.users.count_documents({"email": "admin@negobuy.ai"})
            assert cnt == 1

    _run(_flow())


def test_upstream_reject_returns_structured_401():
    _FakeAsyncClient._next_response = _FakeResp(404, {"detail": "user_data_not_found"})

    async def _flow():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/auth/google/session", json={"session_id": "TEST_bad"})
            assert r.status_code == 401, r.text
            assert str(r.json()["detail"]).startswith("SESSION_INVALID_OR_EXPIRED")

    _run(_flow())


def test_upstream_missing_email_returns_401():
    _FakeAsyncClient._next_response = _FakeResp(200, {"name": "X"})

    async def _flow():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/auth/google/session", json={"session_id": "TEST_no_email"})
            assert r.status_code == 401, r.text
            assert "GOOGLE_PROFILE_INCOMPLETE" in str(r.json()["detail"])

    _run(_flow())


def test_upstream_network_error_returns_502():
    _FakeAsyncClient._next_response = httpx.ConnectError("boom")

    async def _flow():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/auth/google/session", json={"session_id": "TEST_net"})
            assert r.status_code == 502, r.text
            assert "Auth service unreachable" in str(r.json()["detail"])

    _run(_flow())

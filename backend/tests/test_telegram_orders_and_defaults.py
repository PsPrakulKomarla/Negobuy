"""Iteration 15 — Telegram login-persistence bug fix, Accept-Order human-approval gate,
orders/alerts endpoints, default tile vendor injection in auto-sourcing, plus regressions.

SAFETY: never calls POST /api/telegram/link/start (real OTP) nor
POST /api/sourcing/campaigns/{id}/launch (real Telegram messages).
"""
import os
import re
import uuid

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

ADMIN = {"email": "admin@negobuy.ai", "password": "NegoBuy@2026"}


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("access_token")
    assert tok, f"no access_token in {r.json()}"
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="session")
def deals(client):
    r = client.get(f"{BASE_URL}/api/telegram/deals", timeout=60)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert isinstance(d, list)
    return d


# --------------------------------------------------------------- auth / health
class TestAuthAndHealth:
    def test_admin_login(self, client):
        r = client.get(f"{BASE_URL}/api/auth/me", timeout=60)
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN["email"]

    def test_dashboard_stats(self, client):
        r = client.get(f"{BASE_URL}/api/dashboard/stats", timeout=60)
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_ai_status_gemini_no_secrets(self, client):
        r = client.get(f"{BASE_URL}/api/ai/status", timeout=60)
        assert r.status_code == 200
        body = r.json()
        assert body["active_provider"] == "gemini"
        raw = r.text
        assert not re.search(r"AIza[0-9A-Za-z_\-]{10,}", raw)
        assert not re.search(r"sk-[0-9A-Za-z_\-]{10,}", raw)


# ------------------------------------------------ BUG FIX: login persistence
class TestTelegramLoginPersistence:
    def test_verify_without_pending_login_returns_409(self, client):
        r = client.post(f"{BASE_URL}/api/telegram/link/verify",
                        json={"code": "12345"}, timeout=60)
        assert r.status_code == 409, f"expected 409, got {r.status_code}: {r.text[:300]}"
        assert "Start the login first" in r.json().get("detail", "")

    def test_verify_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/telegram/link/verify",
                          json={"code": "12345"}, timeout=60)
        assert r.status_code in (401, 403)

    def test_verify_validation(self, client):
        r = client.post(f"{BASE_URL}/api/telegram/link/verify", json={}, timeout=60)
        assert r.status_code == 422

    def test_status_authorized(self, client):
        r = client.get(f"{BASE_URL}/api/telegram/status", timeout=60)
        assert r.status_code == 200
        st = r.json()
        assert st["linked"] is True
        assert st["authorized"] is True, f"session did not survive restarts: {st}"
        assert st.get("pending_code") is False
        assert "session" not in r.text and "api_hash" not in r.text


# ---------------------------------------------- Accept-Order guardrail gate
class TestAcceptOrderGuardrails:
    def test_unknown_deal_404(self, client):
        r = client.post(f"{BASE_URL}/api/telegram/deals/{uuid.uuid4().hex}/accept", timeout=60)
        assert r.status_code == 404
        assert "not found" in r.json()["detail"].lower()

    def test_no_quote_400(self, client, deals):
        target = next((d for d in deals
                       if d.get("agreed_price") is None and d.get("latest_quote") is None
                       and not d.get("order_id")), None)
        if not target:
            pytest.skip("no deal without a quote available")
        r = client.post(f"{BASE_URL}/api/telegram/deals/{target['id']}/accept", timeout=60)
        assert r.status_code == 400, f"{r.status_code}: {r.text[:300]}"
        assert "No quoted price yet" in r.json()["detail"]

    def test_already_placed_409(self, client, deals):
        target = next((d for d in deals if d.get("order_id")), None)
        if not target:
            pytest.skip("no ORDER_PLACED deal available")
        assert target.get("status") == "ORDER_PLACED"
        r = client.post(f"{BASE_URL}/api/telegram/deals/{target['id']}/accept", timeout=60)
        assert r.status_code == 409, f"{r.status_code}: {r.text[:300]}"
        assert "already placed" in r.json()["detail"].lower()

    def test_accept_requires_auth(self, deals):
        did = deals[0]["id"] if deals else uuid.uuid4().hex
        r = requests.post(f"{BASE_URL}/api/telegram/deals/{did}/accept", timeout=60)
        assert r.status_code in (401, 403)


# ------------------------------------------------------- orders / alerts
class TestOrdersAndAlerts:
    def test_orders_list(self, client, deals):
        r = client.get(f"{BASE_URL}/api/telegram/orders", timeout=60)
        assert r.status_code == 200
        orders = r.json()
        assert isinstance(orders, list)
        assert '"_id"' not in r.text
        placed = [d for d in deals if d.get("order_id")]
        if placed:
            assert len(orders) >= 1, "ORDER_PLACED deal exists but /orders is empty"
            o = orders[0]
            for k in ("vendor", "price", "currency", "status", "deal_id"):
                assert k in o, f"missing {k} in order {o}"
            assert o["status"] == "ACCEPTED"
            assert isinstance(o["price"], (int, float))
            # order must correspond to a deal that carries the order id
            ids = {d.get("order_id") for d in placed}
            assert any(o2["id"] in ids for o2 in orders), "no order matches deal.order_id"

    def test_orders_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/telegram/orders", timeout=60)
        assert r.status_code in (401, 403)

    def test_alerts_list(self, client):
        r = client.get(f"{BASE_URL}/api/telegram/alerts", timeout=60)
        assert r.status_code == 200
        alerts = r.json()
        assert isinstance(alerts, list)
        assert '"_id"' not in r.text
        for a in alerts:
            assert "message" in a and "type" in a

    def test_alerts_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/telegram/alerts", timeout=60)
        assert r.status_code in (401, 403)


# ------------------------------------------------- default tile vendor
class TestDefaultTileVendor:
    def test_tile_material_injects_slv_first(self, client):
        r = client.post(f"{BASE_URL}/api/sourcing/discover", json={
            "material": "Kajaria vitrified floor tiles", "target_price": 420,
            "max_price": 450, "currency": "INR", "location": "Bengaluru",
            "max_vendors": 6}, timeout=300)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        camp = r.json()
        cands = camp["candidates"]
        assert cands, "no candidates"
        first = cands[0]
        assert first["name"] == "SLV Ceramics (Muddinapalya)", first
        assert first["phone"] == "+919980402205"
        assert first.get("default") is True
        # no duplicate of the default phone
        assert [c["phone"] for c in cands].count("+919980402205") == 1
        assert '"_id"' not in r.text

    def test_non_tile_material_no_default(self, client):
        r = client.post(f"{BASE_URL}/api/sourcing/discover", json={
            "material": "industrial ball bearings", "target_price": 100,
            "max_price": 150, "currency": "INR", "location": "Pune",
            "max_vendors": 5}, timeout=300)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        cands = r.json()["candidates"]
        assert all(c["phone"] != "+919980402205" for c in cands), cands
        assert all(not c.get("default") for c in cands)

    def test_max_price_below_target_400(self, client):
        r = client.post(f"{BASE_URL}/api/sourcing/discover", json={
            "material": "tiles", "target_price": 500, "max_price": 400,
            "currency": "INR"}, timeout=60)
        assert r.status_code == 400
        assert "target price" in r.json()["detail"].lower()

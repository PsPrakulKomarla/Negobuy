"""Iteration 14 — Gemini provider abstraction + Auto-Sourcing backend tests.

Covers:
  * GET /api/ai/status  (shape, active provider, no secret leakage)
  * GET /api/system/status (no secret leakage)
  * POST /api/missions/extract (Gemini path returns structured JSON)
  * Missions CRUD regression
  * POST /api/sourcing/discover (real web search) + validation (400)
  * GET /api/sourcing/campaigns, /campaigns/{id}
  * GET /api/dashboard/stats regression
DOES NOT call /api/sourcing/campaigns/{id}/launch (real Telegram side effects).
"""
import os
import re
import json
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

backend_env = dotenv_values("/app/backend/.env")
SECRET_KEYS = [k for k in backend_env
               if re.search(r"KEY|TOKEN|SECRET|PASSWORD|SID|HASH", k, re.I)]
SECRET_VALUES = [backend_env[k] for k in SECRET_KEYS
                 if backend_env.get(k) and len(str(backend_env[k])) >= 12]


@pytest.fixture(scope="session")
def creds():
    content = Path("/app/memory/test_credentials.md").read_text(encoding="utf-8")
    email = re.search(r"(?im)^-\s*Email:\s*`([^`]+)`", content).group(1)
    password = re.search(r"(?im)^-\s*Password:\s*`([^`]+)`", content).group(1)
    return {"email": email, "password": password}


@pytest.fixture(scope="session")
def client(creds):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"Admin login failed {r.status_code}: {r.text[:300]}")
    token = r.json().get("access_token") or r.json().get("token")
    assert token, f"no access_token in login response: {r.text[:300]}"
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def _assert_no_secrets(text: str, where: str):
    for v in SECRET_VALUES:
        assert v not in text, f"SECRET LEAK in {where}: value of a backend .env secret exposed"
    # generic key-shaped strings
    for pat in (r"AIza[0-9A-Za-z_\-]{20,}", r"sk-[A-Za-z0-9_\-]{20,}", r"AQ\.[A-Za-z0-9_\-]{20,}"):
        assert not re.search(pat, text), f"SECRET-SHAPED string ({pat}) found in {where}"


# ----------------------------- AI provider status -----------------------------
class TestAIStatus:
    def test_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/ai/status", timeout=30)
        assert r.status_code in (401, 403), r.text[:300]

    def test_shape_and_active_provider(self, client):
        r = client.get(f"{BASE_URL}/api/ai/status", timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("active_provider") == "gemini", d
        p = d.get("providers")
        assert isinstance(p, dict), d
        for k in ("gemini", "openai", "xai"):
            assert k in p, d
            assert isinstance(p[k], str)
        assert p["gemini"] == "CONFIGURED", d
        assert p["openai"] == "CONFIGURED", d
        assert p["xai"] == "NOT_CONFIGURED", d

    def test_no_secret_leak(self, client):
        r = client.get(f"{BASE_URL}/api/ai/status", timeout=60)
        _assert_no_secrets(json.dumps(r.json()), "/api/ai/status")

    def test_system_status_no_secret_leak(self, client):
        r = client.get(f"{BASE_URL}/api/system/status", timeout=90)
        assert r.status_code == 200, r.text[:300]
        _assert_no_secrets(json.dumps(r.json()), "/api/system/status")
        assert r.json()["ai"]["configured"] is True, r.json()["ai"]


# ----------------------------- Gemini generation path -----------------------------
class TestGeminiExtract:
    def test_extract_requirement(self, client):
        r = client.post(f"{BASE_URL}/api/missions/extract", json={
            "text": "I need 500 boxes of Kajaria vitrified floor tiles 600x600mm "
                    "delivered to Bengaluru, target price 420 INR per box."
        }, timeout=180)
        assert r.status_code == 200, r.text[:500]
        d = r.json()
        assert isinstance(d, dict) and d, d
        body = d.get("requirement") if isinstance(d.get("requirement"), dict) else d
        assert body.get("title"), f"no title in extraction: {d}"
        assert body.get("quantity") is not None, f"no quantity: {d}"
        assert str(body.get("currency", "")).upper() in ("INR", "RS", "₹"), f"currency: {d}"


# ----------------------------- Missions CRUD regression -----------------------------
class TestMissionsCRUD:
    created = []
    restore = {}

    def test_create_get_update_delete(self, client):
        payload = {"title": "TEST_gemini_mission", "description": "TEST mission for iteration 14",
                   "requirement": {"title": "TEST tiles", "quantity": 100, "unit": "boxes",
                                   "currency": "INR", "target_price": 420}}
        r = client.post(f"{BASE_URL}/api/missions", json=payload, timeout=60)
        # Plan limit (free plan = 3 active missions) may be hit due to leftover test data.
        # Temporarily cancel leftover active missions, then restore them in teardown.
        while r.status_code == 402:
            active = [m for m in client.get(f"{BASE_URL}/api/missions", timeout=60).json()
                      if m.get("status") not in ("COMPLETED", "CANCELLED")
                      and m["id"] not in TestMissionsCRUD.restore]
            assert active, f"402 but no active mission to free up: {r.text[:300]}"
            v = active[0]
            p = client.patch(f"{BASE_URL}/api/missions/{v['id']}",
                             json={"status": "CANCELLED"}, timeout=60)
            assert p.status_code == 200, p.text[:200]
            TestMissionsCRUD.restore[v["id"]] = v["status"]
            r = client.post(f"{BASE_URL}/api/missions", json=payload, timeout=60)
        assert r.status_code in (200, 201), r.text[:400]
        m = r.json()
        mid = m.get("id")
        assert mid, m
        assert m.get("title") == "TEST_gemini_mission", m
        assert "_id" not in m, "MongoDB _id leaked in mission response"
        TestMissionsCRUD.created.append(mid)

        g = client.get(f"{BASE_URL}/api/missions/{mid}", timeout=60)
        assert g.status_code == 200, g.text[:300]
        assert g.json()["title"] == "TEST_gemini_mission"
        assert "_id" not in g.json()

        u = client.patch(f"{BASE_URL}/api/missions/{mid}", json={"title": "TEST_gemini_mission_v2"},
                         timeout=60)
        assert u.status_code == 200, u.text[:300]
        g2 = client.get(f"{BASE_URL}/api/missions/{mid}", timeout=60)
        assert g2.json()["title"] == "TEST_gemini_mission_v2", g2.json()

        lst = client.get(f"{BASE_URL}/api/missions", timeout=60)
        assert lst.status_code == 200
        assert any(x.get("id") == mid for x in lst.json())

        d = client.delete(f"{BASE_URL}/api/missions/{mid}", timeout=60)
        assert d.status_code in (200, 204), d.text[:300]
        TestMissionsCRUD.created.remove(mid)
        g3 = client.get(f"{BASE_URL}/api/missions/{mid}", timeout=60)
        assert g3.status_code == 404, g3.status_code

    def test_zz_restore_cancelled_missions(self, client):
        """Restore statuses of missions temporarily cancelled to free plan quota."""
        for mid, status in list(TestMissionsCRUD.restore.items()):
            p = client.patch(f"{BASE_URL}/api/missions/{mid}", json={"status": status}, timeout=60)
            assert p.status_code == 200, p.text[:200]
        TestMissionsCRUD.restore.clear()

    @classmethod
    def teardown_class(cls):
        pass


# ----------------------------- Auto-Sourcing -----------------------------
class TestAutoSourcing:
    campaign_id = None

    def test_discover_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/sourcing/discover",
                          json={"material": "tiles", "target_price": 1, "max_price": 2}, timeout=30)
        assert r.status_code in (401, 403), r.text[:300]

    def test_validation_max_lt_target(self, client):
        r = client.post(f"{BASE_URL}/api/sourcing/discover", json={
            "material": "Kajaria vitrified floor tiles", "target_price": 450,
            "max_price": 420, "currency": "INR", "location": "Bengaluru", "max_vendors": 3
        }, timeout=60)
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text[:300]}"
        assert "price" in r.text.lower()

    def test_validation_short_material(self, client):
        r = client.post(f"{BASE_URL}/api/sourcing/discover", json={
            "material": "a", "target_price": 10, "max_price": 20}, timeout=60)
        assert r.status_code == 422, r.status_code

    def test_discover(self, client):
        r = client.post(f"{BASE_URL}/api/sourcing/discover", json={
            "material": "Kajaria vitrified floor tiles", "target_price": 420, "max_price": 450,
            "currency": "INR", "location": "Bengaluru", "max_vendors": 6
        }, timeout=300)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:600]}"
        c = r.json()
        assert "_id" not in c, "MongoDB _id leaked in campaign response"
        assert c.get("id"), c
        assert c.get("status") == "DISCOVERED", c
        assert isinstance(c.get("candidates"), list), c
        assert isinstance(c.get("telegram_linked"), bool), c
        TestAutoSourcing.campaign_id = c["id"]
        print(f"discover returned {len(c['candidates'])} candidates")
        for cand in c["candidates"]:
            assert cand.get("name"), cand
            assert re.fullmatch(r"\+91[6-9]\d{9}", cand.get("phone", "")), cand
            assert cand.get("telegram_reachable") in (True, False, None), cand
            assert cand.get("status") == "FOUND", cand
        # phones unique
        phones = [x["phone"] for x in c["candidates"]]
        assert len(phones) == len(set(phones)), "duplicate phones returned"

    def test_list_campaigns(self, client):
        r = client.get(f"{BASE_URL}/api/sourcing/campaigns", timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert isinstance(r.json(), list)
        if TestAutoSourcing.campaign_id:
            assert any(x.get("id") == TestAutoSourcing.campaign_id for x in r.json()), \
                "created campaign not persisted/listed"

    def test_get_campaign(self, client):
        if not TestAutoSourcing.campaign_id:
            pytest.skip("no campaign created")
        r = client.get(f"{BASE_URL}/api/sourcing/campaigns/{TestAutoSourcing.campaign_id}",
                       timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["id"] == TestAutoSourcing.campaign_id
        assert "best" in d
        assert "_id" not in d

    def test_get_campaign_404(self, client):
        r = client.get(f"{BASE_URL}/api/sourcing/campaigns/does-not-exist-xyz", timeout=60)
        assert r.status_code == 404, r.status_code


# ----------------------------- Dashboard regression -----------------------------
class TestDashboard:
    def test_stats(self, client):
        r = client.get(f"{BASE_URL}/api/dashboard/stats", timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert isinstance(r.json(), dict) and r.json()

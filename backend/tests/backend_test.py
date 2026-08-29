"""NegoBuy Backend API tests - covers auth, missions, discovery, negotiation, offers, comparison, approval, dashboard, voice, billing."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://magical-sanderson-11.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

BUYER_EMAIL = "buyer@test.com"
BUYER_PASS = "test123"


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def token(session):
    r = session.post(f"{API}/auth/login", json={"email": BUYER_EMAIL, "password": BUYER_PASS}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "access_token" in data and data["access_token"]
    return data["access_token"]


@pytest.fixture(scope="session")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------------- AUTH ----------------
class TestAuth:
    def test_login_returns_token_and_user(self, session):
        r = session.post(f"{API}/auth/login", json={"email": BUYER_EMAIL, "password": BUYER_PASS}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["email"] == BUYER_EMAIL

    def test_login_invalid(self, session):
        r = session.post(f"{API}/auth/login", json={"email": BUYER_EMAIL, "password": "wrong"}, timeout=15)
        assert r.status_code in (400, 401, 403)

    def test_me_with_bearer(self, session, auth_headers):
        r = requests.get(f"{API}/auth/me", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert r.json()["email"] == BUYER_EMAIL

    def test_me_without_token(self, session):
        r = requests.get(f"{API}/auth/me", timeout=15)
        assert r.status_code in (401, 403)

    def test_register_and_logout(self, session):
        uniq = f"TEST_user_{int(time.time())}@example.com"
        r = requests.post(f"{API}/auth/register", json={
            "email": uniq, "password": "Test1234!", "name": "TEST User", "org_name": "TEST Org"
        }, timeout=15)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert "access_token" in data
        # logout
        h = {"Authorization": f"Bearer {data['access_token']}"}
        rl = requests.post(f"{API}/auth/logout", headers=h, timeout=15)
        assert rl.status_code in (200, 204)


# ---------------- AI EXTRACT ----------------
class TestExtract:
    def test_extract_requirement(self, auth_headers):
        payload = {"text": "I need 500 ergonomic office chairs under 5 lakh delivered to Bangalore within 10 days"}
        r = requests.post(f"{API}/missions/extract", headers=auth_headers, json=payload, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        # Structural checks; be tolerant of exact field names
        assert isinstance(data, dict)
        # capture common fields
        text = str(data).lower()
        assert "500" in text or data.get("quantity") == 500
        assert "bangalore" in text.lower()


# ---------------- MISSIONS CRUD + PIPELINE ----------------
@pytest.fixture(scope="session")
def mission_id(auth_headers):
    spec = {
        "title": "TEST Ergonomic Chairs 500",
        "category": "office_furniture",
        "quantity": 500,
        "budget": 500000,
        "currency": "INR",
        "delivery_location": "Bangalore",
        "deadline_days": 10,
        "description": "TEST mission - 500 ergonomic office chairs",
    }
    r = requests.post(f"{API}/missions", headers=auth_headers, json=spec, timeout=30)
    assert r.status_code in (200, 201), r.text
    data = r.json()
    mid = data.get("id") or data.get("_id") or data.get("mission_id")
    assert mid, f"no id in {data}"
    return mid


class TestMissionsCRUD:
    def test_list_missions(self, auth_headers, mission_id):
        r = requests.get(f"{API}/missions", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        ms = r.json()
        assert isinstance(ms, list)
        assert any(m.get("id") == mission_id for m in ms)

    def test_get_mission(self, auth_headers, mission_id):
        r = requests.get(f"{API}/missions/{mission_id}", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert r.json().get("id") == mission_id

    def test_patch_mission(self, auth_headers, mission_id):
        r = requests.patch(f"{API}/missions/{mission_id}", headers=auth_headers, json={"title": "TEST Chairs Updated"}, timeout=15)
        assert r.status_code in (200, 204)
        r2 = requests.get(f"{API}/missions/{mission_id}", headers=auth_headers, timeout=15)
        assert r2.json().get("title") == "TEST Chairs Updated"


# ---------------- DISCOVERY ----------------
class TestDiscovery:
    def test_run_discovery_and_poll(self, auth_headers, mission_id):
        r = requests.post(f"{API}/missions/{mission_id}/discover", headers=auth_headers, timeout=30)
        assert r.status_code in (200, 202), r.text

        # Poll for vendors up to 90 seconds
        vendors = []
        deadline = time.time() + 90
        while time.time() < deadline:
            vr = requests.get(f"{API}/missions/{mission_id}/vendors", headers=auth_headers, timeout=15)
            if vr.status_code == 200:
                vendors = vr.json()
                if isinstance(vendors, list) and len(vendors) > 0:
                    break
            time.sleep(5)
        assert isinstance(vendors, list) and len(vendors) > 0, f"no vendors after 90s: got {vendors}"
        v0 = vendors[0]
        assert "id" in v0 or "_id" in v0 or "name" in v0

    def test_activity_trail(self, auth_headers, mission_id):
        r = requests.get(f"{API}/missions/{mission_id}/activity", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        acts = r.json()
        assert isinstance(acts, list)


# ---------------- NEGOTIATION ----------------
@pytest.fixture(scope="session")
def negotiated_vendor(auth_headers, mission_id):
    # Fetch vendors after discovery
    vr = requests.get(f"{API}/missions/{mission_id}/vendors", headers=auth_headers, timeout=15)
    assert vr.status_code == 200
    vendors = vr.json()
    if not vendors:
        pytest.skip("No vendors available for negotiation")
    return vendors[0]


class TestNegotiation:
    def test_negotiate_vendor(self, auth_headers, mission_id, negotiated_vendor):
        vid = negotiated_vendor.get("id") or negotiated_vendor.get("_id")
        r = requests.post(f"{API}/missions/{mission_id}/vendors/{vid}/negotiate",
                          headers=auth_headers, json={"rounds": 2}, timeout=180)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, dict)

    def test_list_negotiations(self, auth_headers, mission_id):
        r = requests.get(f"{API}/missions/{mission_id}/negotiations", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------------- OFFERS ----------------
class TestOffers:
    def test_list_offers(self, auth_headers, mission_id):
        r = requests.get(f"{API}/missions/{mission_id}/offers", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        offers = r.json()
        assert isinstance(offers, list)
        # verify landed cost breakdown exists on at least one offer if present
        if offers:
            o = offers[0]
            keys = str(o).lower()
            assert "landed" in keys or "total" in keys or "price" in keys


# ---------------- COMPARE ----------------
class TestCompare:
    def test_compare(self, auth_headers, mission_id):
        r = requests.post(f"{API}/missions/{mission_id}/compare", headers=auth_headers, timeout=120)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, dict)


# ---------------- APPROVAL ----------------
class TestApproval:
    def test_approve_action(self, auth_headers, mission_id):
        # Fetch offers
        r = requests.get(f"{API}/missions/{mission_id}/offers", headers=auth_headers, timeout=15)
        offers = r.json() if r.status_code == 200 else []
        if not offers:
            pytest.skip("No offers to approve")
        oid = offers[0].get("id") or offers[0].get("_id")
        ap = requests.post(f"{API}/missions/{mission_id}/approve",
                           headers=auth_headers, json={"action": "APPROVE", "offer_id": oid}, timeout=30)
        assert ap.status_code == 200, ap.text


# ---------------- DASHBOARD ----------------
class TestDashboard:
    def test_stats(self, auth_headers):
        r = requests.get(f"{API}/dashboard/stats", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        for key in ["active_missions", "completed_missions", "vendors_discovered"]:
            assert key in data, f"missing {key} in {data}"


# ---------------- VOICE ----------------
class TestVoice:
    def test_voice_status(self, auth_headers):
        r = requests.get(f"{API}/voice/status", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("configured") is False
        assert data.get("provider") == "openai_realtime"


# ---------------- BILLING ----------------
class TestBilling:
    def test_plans(self, auth_headers):
        r = requests.get(f"{API}/billing/plans", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        plans = r.json()
        assert isinstance(plans, list)
        assert len(plans) >= 3

    def test_subscription(self, auth_headers):
        r = requests.get(f"{API}/billing/subscription", headers=auth_headers, timeout=15)
        assert r.status_code == 200


# ---------------- CLEANUP ----------------
def test_zz_cleanup_mission(auth_headers, mission_id):
    r = requests.delete(f"{API}/missions/{mission_id}", headers=auth_headers, timeout=15)
    assert r.status_code in (200, 204)

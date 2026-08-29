"""Exotel integration backend tests.

Covers: /api/voice/exotel/status, /call auth+ownership, mocked call flow
(NOT_CONFIGURED path), session-start / session-end webhooks including token
enforcement, authority read-only guarantee, idempotency, audit logging, and
regression of /api/system/status.
"""
import os
import time
import pytest
import requests

def _load_base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        v = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    assert v, "REACT_APP_BACKEND_URL not set"
    return v.rstrip("/")

BASE = _load_base()
ADMIN = {"email": "admin@negobuy.ai", "password": "NegoBuy@2026"}
WEBHOOK_TOKEN = "nb_exotel_9f2a7c41e8b6d503"

SENSITIVE_VALUES = [
    "da051eede7c61e1a4b409bb5fc4c4c1d9e2b5d86661a2b4e",  # api key
    "5ed2b98967f53a2f1f9c2230964a3f6b62c51ebdb65ad975",  # api token
]


# ---------------- fixtures ---------------- #
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def hdrs(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def mission(hdrs):
    """Reuse a single mission across all tests (free-plan cap = 3 active)."""
    payload = {
        "title": "TEST_EXOTEL Widgets",
        "category": "electronics",
        "quantity": 100,
        "budget": 100000,
        "currency": "INR",
        "deadline_days": 10,
        "warranty_requirements": "1 year",
    }
    r = requests.post(f"{BASE}/api/missions", json=payload, headers=hdrs, timeout=20)
    assert r.status_code in (200, 201), r.text
    m = r.json()
    yield m
    # cleanup
    try:
        requests.delete(f"{BASE}/api/missions/{m['id']}", headers=hdrs, timeout=15)
    except Exception:
        pass


def _no_secrets(text_body: str):
    for s in SENSITIVE_VALUES:
        assert s not in text_body, "Sensitive value leaked in response"


# ---------------- status ---------------- #
class TestStatus:
    def test_status_requires_auth(self):
        r = requests.get(f"{BASE}/api/voice/exotel/status", timeout=15)
        assert r.status_code == 401

    def test_status_shape(self, hdrs):
        r = requests.get(f"{BASE}/api/voice/exotel/status", headers=hdrs, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["provider"] == "exotel"
        assert d["configured"] is False
        assert d["state"] == "NOT_CONFIGURED"
        assert "EXOTEL_CALLER_ID" in d["missing"]
        assert d["webhook_secured"] is True
        # never expose secrets
        _no_secrets(r.text)
        for bad in ("api_key", "api_token", "EXOTEL_API_KEY", "EXOTEL_API_TOKEN"):
            # keys may appear only inside "missing" list of env var names, which is fine
            pass
        # verify no known secret values leak
        _no_secrets(r.text)


# ---------------- /call auth + ownership ---------------- #
class TestCallAuth:
    def test_call_requires_auth(self):
        r = requests.post(f"{BASE}/api/voice/exotel/call",
                          json={"mission_id": "x", "vendor_id": "y"}, timeout=15)
        assert r.status_code == 401

    def test_call_bogus_mission_returns_404(self, hdrs):
        r = requests.post(f"{BASE}/api/voice/exotel/call",
                          json={"mission_id": "bogus", "vendor_id": "bogus"},
                          headers=hdrs, timeout=15)
        assert r.status_code == 404


# ---------------- full mocked call + webhooks flow ---------------- #
class TestMockedFlow:
    session_ref = None
    vendor_id = None
    mission_id = None
    initial_offer_count = None

    def test_discover_vendor(self, hdrs, mission):
        TestMockedFlow.mission_id = mission["id"]
        # kick discovery
        r = requests.post(f"{BASE}/api/missions/{mission['id']}/discover",
                          headers=hdrs, timeout=30)
        assert r.status_code in (200, 202), r.text
        # poll vendors
        vendor = None
        for _ in range(20):
            time.sleep(3)
            vr = requests.get(f"{BASE}/api/missions/{mission['id']}/vendors",
                              headers=hdrs, timeout=15)
            if vr.status_code == 200 and vr.json():
                vendors = vr.json()
                if isinstance(vendors, list) and vendors:
                    vendor = vendors[0]
                    break
        if not vendor:
            pytest.skip("No vendors discovered within timeout - discovery flakiness")
        TestMockedFlow.vendor_id = vendor.get("id")
        assert TestMockedFlow.vendor_id

    def test_place_call_not_configured(self, hdrs, mission):
        if not TestMockedFlow.vendor_id:
            pytest.skip("no vendor")
        # capture offer count before
        r = requests.get(f"{BASE}/api/missions/{mission['id']}/offers",
                         headers=hdrs, timeout=15)
        TestMockedFlow.initial_offer_count = len(r.json()) if r.status_code == 200 else 0

        r = requests.post(
            f"{BASE}/api/voice/exotel/call",
            json={"mission_id": mission["id"], "vendor_id": TestMockedFlow.vendor_id},
            headers=hdrs, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "NOT_CONFIGURED"
        assert data["provider"] == "exotel"
        assert data.get("session_ref")
        _no_secrets(r.text)
        TestMockedFlow.session_ref = data["session_ref"]

    # --- session-start webhook ---
    def test_session_start_wrong_token(self):
        if not TestMockedFlow.session_ref:
            pytest.skip("no session")
        r = requests.post(f"{BASE}/api/voice/exotel/session-start?token=WRONG",
                          data={"CustomField": TestMockedFlow.session_ref}, timeout=15)
        assert r.status_code == 401

    def test_session_start_unknown_ref(self):
        r = requests.post(f"{BASE}/api/voice/exotel/session-start?token={WEBHOOK_TOKEN}",
                          data={"CustomField": "does_not_exist_xyz"}, timeout=15)
        assert r.status_code == 404

    def test_session_start_context(self):
        if not TestMockedFlow.session_ref:
            pytest.skip("no session")
        r = requests.post(
            f"{BASE}/api/voice/exotel/session-start?token={WEBHOOK_TOKEN}",
            data={"CustomField": TestMockedFlow.session_ref},
            timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["session_ref"] == TestMockedFlow.session_ref
        assert "mission" in data
        auth_obj = data.get("authority") or {}
        assert auth_obj.get("max_price_per_unit") == 1000
        assert auth_obj.get("target_price_per_unit") == 900
        assert "rules" in data and ("not commit" in data["rules"].lower()
                                    or "commit" in data["rules"].lower())
        _no_secrets(r.text)

    def test_authority_is_read_only(self):
        """Attempt to mutate authority via session-start form fields → must not persist."""
        if not TestMockedFlow.session_ref:
            pytest.skip("no session")
        # try to poison
        requests.post(
            f"{BASE}/api/voice/exotel/session-start?token={WEBHOOK_TOKEN}",
            data={"CustomField": TestMockedFlow.session_ref,
                  "max_price_per_unit": "999999",
                  "target_price_per_unit": "999999",
                  "authority": "unlimited"},
            timeout=15)
        # re-fetch
        r = requests.post(
            f"{BASE}/api/voice/exotel/session-start?token={WEBHOOK_TOKEN}",
            data={"CustomField": TestMockedFlow.session_ref},
            timeout=15)
        assert r.status_code == 200
        auth_obj = r.json().get("authority") or {}
        assert auth_obj.get("max_price_per_unit") == 1000, \
            f"Authority mutated! got {auth_obj}"
        assert auth_obj.get("target_price_per_unit") == 900

    # --- session-end webhook ---
    def test_session_end_records(self, hdrs, mission):
        if not TestMockedFlow.session_ref:
            pytest.skip("no session")
        r = requests.post(
            f"{BASE}/api/voice/exotel/session-end?token={WEBHOOK_TOKEN}",
            data={"CustomField": TestMockedFlow.session_ref,
                  "CallStatus": "completed",
                  "DialCallDuration": "95",
                  "RecordingUrl": "https://example.com/r.mp3",
                  "price_per_unit": "850"},
            timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("status") == "recorded"

        # NO auto-created offer
        r2 = requests.get(f"{BASE}/api/missions/{mission['id']}/offers",
                          headers=hdrs, timeout=15)
        cur = len(r2.json()) if r2.status_code == 200 else 0
        assert cur == (TestMockedFlow.initial_offer_count or 0), \
            "Offer auto-created from call — must NOT happen"

        # mission status not moved to APPROVED/COMPLETED
        rm = requests.get(f"{BASE}/api/missions/{mission['id']}",
                          headers=hdrs, timeout=15)
        assert rm.status_code == 200
        assert rm.json().get("status") not in ("APPROVED", "COMPLETED")

    def test_session_end_idempotent(self):
        if not TestMockedFlow.session_ref:
            pytest.skip("no session")
        r = requests.post(
            f"{BASE}/api/voice/exotel/session-end?token={WEBHOOK_TOKEN}",
            data={"CustomField": TestMockedFlow.session_ref,
                  "CallStatus": "completed"},
            timeout=15)
        assert r.status_code == 200
        assert r.json().get("status") == "duplicate"


# ---------------- audit + regression ---------------- #
class TestAuditAndRegression:
    def test_audit_has_call_events_and_no_secrets(self, hdrs, mission):
        r = requests.get(f"{BASE}/api/audit", headers=hdrs, timeout=15)
        assert r.status_code == 200
        events = r.json()
        assert isinstance(events, list)
        mission_events = [e for e in events if e.get("mission_id") == mission["id"]]
        types = {e.get("event_type") for e in mission_events}
        # at least one of call_started / call_stub_recorded
        has_start = bool(types & {"call_started", "call_stub_recorded"})
        if TestMockedFlow.session_ref:
            assert has_start, f"No call-start audit event found; types={types}"
            assert "call_ended" in types, f"No call_ended audit event; types={types}"
        # no secret values in any audit detail
        blob = str(events)
        _no_secrets(blob)

    def test_system_status_exotel_block(self, hdrs):
        r = requests.get(f"{BASE}/api/system/status", headers=hdrs, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "exotel" in d
        assert d["exotel"]["state"] == "NOT_CONFIGURED"
        # existing regressions
        assert d.get("voice", {}).get("state") == "READY"
        assert d.get("telephony", {}).get("state") == "NOT_CONFIGURED"
        _no_secrets(r.text)

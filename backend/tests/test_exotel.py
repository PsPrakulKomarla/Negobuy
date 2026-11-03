"""Exotel integration backend tests (READY / real-call mode).

Covers:
- GET /api/voice/exotel/status: READY, verified true, no secrets.
- Auth + ownership on /call and /session.
- ONE real outbound call to +919008136500. Trial account may accept OR reject —
  both are pass as long as endpoint responds honestly, session is stored,
  and no secrets leak.
- Session tracking (org-scoped, 404 on bogus).
- No auto-commit: offer count unchanged, mission not APPROVED/COMPLETED.
- Webhook path (mocked): session-end idempotent; session-start authority read-only.
- Audit: call_started + call_ended events, no secret leaks.
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
TEST_TO_NUMBER = "9008136500"
EXPECTED_E164 = "+919008136500"

# Live secret values loaded from backend/.env so we can assert they never leak.
def _load_secret_values():
    vals = []
    try:
        with open("/app/backend/.env") as f:
            for line in f:
                for k in ("EXOTEL_API_KEY", "EXOTEL_API_TOKEN", "EXOTEL_ACCOUNT_SID"):
                    if line.startswith(k + "="):
                        v = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if v:
                            vals.append(v)
    except Exception:
        pass
    return vals


SENSITIVE_VALUES = _load_secret_values()


def _no_secrets(text_body: str):
    for s in SENSITIVE_VALUES:
        # Account SID is often echoed in subdomain-agnostic identifiers; but our
        # /status returns subdomain only, and /call response is sanitized. Assert
        # that the concrete api_key / api_token never appear.
        assert s not in text_body, "Sensitive credential value leaked in response"


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
    payload = {
        "title": "TEST_EXOTEL Chairs",
        "category": "Furniture",
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
    try:
        requests.delete(f"{BASE}/api/missions/{m['id']}", headers=hdrs, timeout=15)
    except Exception:
        pass


# ---------------- status ---------------- #
class TestStatus:
    def test_status_requires_auth(self):
        r = requests.get(f"{BASE}/api/voice/exotel/status", timeout=15)
        assert r.status_code == 401

    def test_status_ready_and_no_secrets(self, hdrs):
        r = requests.get(f"{BASE}/api/voice/exotel/status", headers=hdrs, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["provider"] == "exotel"
        assert d["configured"] is True
        assert d["state"] == "READY"
        assert d.get("verified") is True
        assert d.get("webhook_secured") is True
        # keys of secret env vars must not be echoed with their values
        for bad_key in ("api_key", "api_token", "authtoken", "auth_token"):
            assert bad_key not in {k.lower() for k in d.keys()}
        _no_secrets(r.text)


# ---------------- /call auth + ownership ---------------- #
class TestCallAuth:
    def test_call_requires_auth(self):
        r = requests.post(f"{BASE}/api/voice/exotel/call",
                          json={"mission_id": "x", "vendor_id": "y",
                                "to_number": TEST_TO_NUMBER}, timeout=15)
        assert r.status_code == 401

    def test_call_bogus_mission_returns_404(self, hdrs):
        r = requests.post(f"{BASE}/api/voice/exotel/call",
                          json={"mission_id": "bogus", "vendor_id": "bogus",
                                "to_number": TEST_TO_NUMBER},
                          headers=hdrs, timeout=15)
        assert r.status_code == 404


# ---------------- real call + tracking + safety ---------------- #
class TestRealCallFlow:
    session_ref = None
    vendor_id = None
    initial_offer_count = None
    initial_status = None

    def test_discover_vendor(self, hdrs, mission):
        r = requests.post(f"{BASE}/api/missions/{mission['id']}/discover",
                          headers=hdrs, timeout=30)
        assert r.status_code in (200, 202), r.text
        vendor = None
        for _ in range(24):
            time.sleep(3)
            vr = requests.get(f"{BASE}/api/missions/{mission['id']}/vendors",
                              headers=hdrs, timeout=15)
            if vr.status_code == 200 and isinstance(vr.json(), list) and vr.json():
                vendor = vr.json()[0]
                break
        if not vendor:
            pytest.skip("Discovery flakiness: no vendor within ~72s")
        TestRealCallFlow.vendor_id = vendor.get("id")
        assert TestRealCallFlow.vendor_id

    def test_place_real_call_once(self, hdrs, mission):
        if not TestRealCallFlow.vendor_id:
            pytest.skip("no vendor")
        # capture initial state
        r0 = requests.get(f"{BASE}/api/missions/{mission['id']}/offers",
                          headers=hdrs, timeout=15)
        TestRealCallFlow.initial_offer_count = len(r0.json()) if r0.status_code == 200 else 0
        rm0 = requests.get(f"{BASE}/api/missions/{mission['id']}",
                           headers=hdrs, timeout=15)
        TestRealCallFlow.initial_status = rm0.json().get("status") if rm0.status_code == 200 else None

        # ONE real call
        r = requests.post(
            f"{BASE}/api/voice/exotel/call",
            json={"mission_id": mission["id"],
                  "vendor_id": TestRealCallFlow.vendor_id,
                  "to_number": TEST_TO_NUMBER},
            headers=hdrs, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        # Both accepted and rejected outcomes are OK — as long as honest
        assert data.get("provider") == "exotel"
        assert data.get("session_ref")
        assert data.get("status") in ("calling", "connected", "failed", "initiating")
        # never leak credentials in response
        _no_secrets(r.text)
        # http_status must be surfaced (int) when Exotel responded
        assert "http_status" in data
        TestRealCallFlow.session_ref = data["session_ref"]
        print(f"Real call outcome: status={data.get('status')} accepted={data.get('accepted')} "
              f"http_status={data.get('http_status')} call_sid={data.get('provider_call_sid')}")

    def test_session_tracked_and_org_scoped(self, hdrs):
        if not TestRealCallFlow.session_ref:
            pytest.skip("no session")
        # authorized read
        r = requests.get(f"{BASE}/api/voice/exotel/session/{TestRealCallFlow.session_ref}",
                         headers=hdrs, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["session_ref"] == TestRealCallFlow.session_ref
        assert d.get("provider") == "exotel"
        # E.164 normalization applied
        assert d.get("to") == EXPECTED_E164
        # authority present but computed by backend
        auth_obj = d.get("authority") or {}
        assert auth_obj.get("max_price_per_unit") == 1000
        _no_secrets(r.text)
        # unauthenticated read must not work
        r2 = requests.get(f"{BASE}/api/voice/exotel/session/{TestRealCallFlow.session_ref}",
                          timeout=15)
        assert r2.status_code == 401

    def test_session_bogus_ref_404(self, hdrs):
        r = requests.get(f"{BASE}/api/voice/exotel/session/does_not_exist_xyz",
                         headers=hdrs, timeout=15)
        assert r.status_code == 404

    def test_no_auto_commit_after_call(self, hdrs, mission):
        if not TestRealCallFlow.session_ref:
            pytest.skip("no session")
        r = requests.get(f"{BASE}/api/missions/{mission['id']}/offers",
                         headers=hdrs, timeout=15)
        cur = len(r.json()) if r.status_code == 200 else 0
        assert cur == (TestRealCallFlow.initial_offer_count or 0), \
            "Offer auto-created from call — must NOT happen"
        rm = requests.get(f"{BASE}/api/missions/{mission['id']}",
                          headers=hdrs, timeout=15)
        assert rm.status_code == 200
        assert rm.json().get("status") not in ("APPROVED", "COMPLETED")


# ---------------- webhook path (mocked) ---------------- #
class TestWebhooks:
    def test_session_end_wrong_token(self):
        r = requests.post(f"{BASE}/api/voice/exotel/session-end?token=WRONG",
                          data={"CustomField": "x"}, timeout=15)
        assert r.status_code == 401

    def test_session_end_and_duplicate(self, hdrs):
        if not TestRealCallFlow.session_ref:
            pytest.skip("no session")
        # first terminal
        r = requests.post(
            f"{BASE}/api/voice/exotel/session-end?token={WEBHOOK_TOKEN}",
            data={"CustomField": TestRealCallFlow.session_ref,
                  "CallStatus": "completed",
                  "DialCallDuration": "42"},
            timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("status") == "recorded"
        # session reflects terminal
        rs = requests.get(f"{BASE}/api/voice/exotel/session/{TestRealCallFlow.session_ref}",
                          headers=hdrs, timeout=15)
        assert rs.status_code == 200
        ds = rs.json()
        assert ds.get("status") == "completed"
        assert str(ds.get("duration")) == "42"
        # duplicate
        r2 = requests.post(
            f"{BASE}/api/voice/exotel/session-end?token={WEBHOOK_TOKEN}",
            data={"CustomField": TestRealCallFlow.session_ref,
                  "CallStatus": "completed",
                  "DialCallDuration": "42"},
            timeout=15)
        assert r2.status_code == 200
        assert r2.json().get("status") == "duplicate"

    def test_session_start_authority_read_only(self):
        if not TestRealCallFlow.session_ref:
            pytest.skip("no session")
        # baseline
        r0 = requests.post(
            f"{BASE}/api/voice/exotel/session-start?token={WEBHOOK_TOKEN}",
            data={"CustomField": TestRealCallFlow.session_ref}, timeout=15)
        assert r0.status_code == 200, r0.text
        auth0 = r0.json().get("authority") or {}
        assert auth0.get("max_price_per_unit") == 1000
        # try to poison
        requests.post(
            f"{BASE}/api/voice/exotel/session-start?token={WEBHOOK_TOKEN}",
            data={"CustomField": TestRealCallFlow.session_ref,
                  "max_price_per_unit": "999999"}, timeout=15)
        # re-fetch
        r1 = requests.post(
            f"{BASE}/api/voice/exotel/session-start?token={WEBHOOK_TOKEN}",
            data={"CustomField": TestRealCallFlow.session_ref}, timeout=15)
        auth1 = r1.json().get("authority") or {}
        assert auth1.get("max_price_per_unit") == 1000, \
            f"Authority mutated! got {auth1}"


# ---------------- audit ---------------- #
class TestAudit:
    def test_audit_call_events_and_no_secrets(self, hdrs, mission):
        r = requests.get(f"{BASE}/api/audit", headers=hdrs, timeout=15)
        assert r.status_code == 200
        events = r.json()
        assert isinstance(events, list)
        mission_events = [e for e in events if e.get("mission_id") == mission["id"]]
        types = {e.get("event_type") for e in mission_events}
        if TestRealCallFlow.session_ref:
            assert types & {"call_started", "call_stub_recorded"}, f"types={types}"
            assert "call_ended" in types, f"types={types}"
        _no_secrets(str(events))

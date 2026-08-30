"""Tests for the NegoBuy Call Center (/api/voice/console) feature."""
import os
import re
import time
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

MISSION_ID = "b983bb2f74bd44f29685978e16251d93"
VENDOR_ID = "3a7c1a1bc7fd486599d696c7674c2177"
MISSION_2 = "4502b5e0ebe84e909b72eca85927dc4c"
VENDOR_2 = "27e789fa0784487697f81f7f3af6ec42"
TEST_NUMBER = "+919876500011"


def _creds():
    content = Path("/app/memory/test_credentials.md").read_text(encoding="utf-8")
    email = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?Email(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    pwd = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?Password(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    return {"email": email.group(1), "password": pwd.group(1)}


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    c = _creds()
    r = s.post(f"{API}/auth/login", json=c, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    token = r.json().get("access_token")
    assert token, "no access_token in login response"
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def _objective(**over):
    body = {
        "mission_id": MISSION_ID, "vendor_id": VENDOR_ID, "to_number": TEST_NUMBER,
        "supplier_name": "TEST_Tiles Vendor", "product": "Kajaria vitrified tiles 600x600",
        "quantity": 500, "current_price": 62.0, "target_price": 52.0,
        "max_authorized_price": 56.0, "delivery_location": "Pune, MH",
        "delivery_deadline_days": 12, "warranty_requirements": "2 year manufacturer warranty",
        "payment_preferences": "50% advance, 50% on delivery",
        "negotiation_priorities": ["price", "delivery"],
        "special_instructions": "TEST_ automated QA run. Do not commit.",
        "currency": "INR", "test_mode": True,
    }
    body.update(over)
    return body


# --------------------------- config endpoint ---------------------------
class TestCallConfig:
    def test_login_ok(self, client):
        r = client.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 200
        assert r.json().get("email") == _creds()["email"]

    def test_create_config(self, client, request):
        r = client.post(f"{API}/voice/console/config", json=_objective(), timeout=60)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert "_id" not in d
        assert d["status"] == "CONFIGURED"
        assert d["approved"] is False
        assert d["call_sid"] is None
        auth = d["authority"]
        assert auth["target_price_per_unit"] == 52.0
        assert auth["max_price_per_unit"] == 56.0
        assert auth["quantity"] == 500
        assert auth["currency"] == "INR"
        assert isinstance(d["not_authorized"], list) and len(d["not_authorized"]) >= 3
        assert any("maximum authorized" in x for x in d["not_authorized"])
        ds = d["disclosure_script"]
        assert "AI" in ds and "recorded" in ds.lower()
        assert d["objective"]["target_price"] == 52.0
        assert d["transcript"] == [] and d["analysis"] is None
        request.config.cache.set("cfg_ref", d["session_ref"])

    def test_config_requires_number(self, client):
        r = client.post(f"{API}/voice/console/config", json=_objective(to_number=""), timeout=60)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"

    def test_config_org_isolation(self, client):
        r = client.post(f"{API}/voice/console/config",
                        json=_objective(mission_id="00000000000000000000000000000000"), timeout=60)
        assert r.status_code == 404
        assert "Mission not found" in r.text

    def test_config_bad_vendor(self, client):
        r = client.post(f"{API}/voice/console/config",
                        json=_objective(vendor_id="deadbeef"), timeout=60)
        assert r.status_code == 404
        assert "Vendor not found" in r.text

    def test_config_requires_auth(self):
        r = requests.post(f"{API}/voice/console/config", json=_objective(), timeout=30)
        assert r.status_code in (401, 403)

    def test_disclosure_off(self, client):
        r = client.post(f"{API}/voice/console/config",
                        json=_objective(disclose_ai=False, recording_notice=False), timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert d["disclosure_script"] == ""
        assert d["recording"]["state"] == "RECORDING_NOT_SUPPORTED"


# --------------------------- approval + simulation ---------------------------
class TestSimulation:
    ref = None
    result = None

    @pytest.fixture(scope="class", autouse=True)
    def run_sim(self, client):
        r = client.post(f"{API}/voice/console/config", json=_objective(), timeout=60)
        assert r.status_code == 200, r.text[:300]
        TestSimulation.ref = r.json()["session_ref"]
        t0 = time.time()
        ar = client.post(f"{API}/voice/console/approve/{TestSimulation.ref}", timeout=240)
        assert ar.status_code == 200, f"approve failed {ar.status_code}: {ar.text[:500]}"
        TestSimulation.result = ar.json()
        print(f"simulation took {time.time()-t0:.1f}s")

    def test_status_and_approval(self):
        d = self.result
        assert d["status"] == "SIMULATED_COMPLETE", d.get("status")
        assert d["approved"] is True
        assert d["approval"]["approved_by"]
        assert d["simulation"] is True
        assert isinstance(d["duration"], int) and d["duration"] > 0

    def test_transcript(self):
        tr = self.result["transcript"]
        assert isinstance(tr, list) and len(tr) >= 4
        speakers = {t["speaker"] for t in tr}
        assert speakers <= {"AI", "SUPPLIER", "SYSTEM"}
        assert {"AI", "SUPPLIER", "SYSTEM"} <= speakers
        for t in tr:
            assert re.match(r"^\d{2}:\d{2}$", t["timestamp"]), t
            assert t["text"].strip()
        assert self.result["transcript_status"] == "AVAILABLE"

    def test_analysis(self):
        an = self.result["analysis"]
        assert an, "analysis missing"
        assert an.get("summary"), an
        assert an.get("negotiation_result")
        assert "price" in an
        terms = an.get("terms")
        assert isinstance(terms, list) and len(terms) >= 1
        allowed = {"CONFIRMED", "PROPOSED", "UNCLEAR", "REQUIRES_HUMAN_APPROVAL"}
        for t in terms:
            assert t.get("status") in allowed, t
        assert an.get("self_review")
        assert an.get("recommended_next_action")
        assert isinstance(an.get("requires_human_approval"), bool)

    def test_authority_clamp(self):
        an = self.result["analysis"]
        price = (an.get("price") or {}).get("final_discussed")
        mx = self.result["authority"]["max_price_per_unit"]
        if price not in (None, ""):
            try:
                over = float(price) > float(mx)
            except Exception:
                over = False
            if over:
                assert an.get("within_authority") is False, an
                assert an.get("requires_human_approval") is True, an
        print("final_discussed:", price, "max:", mx,
              "within_authority:", an.get("within_authority"))

    def test_no_order_auto_created(self, client):
        r = client.get(f"{API}/missions/{MISSION_ID}", timeout=60)
        assert r.status_code == 200
        m = r.json()
        assert m.get("status") not in ("ORDERED", "PURCHASED"), m.get("status")
        for path in (f"{API}/orders", f"{API}/purchases"):
            rr = client.get(path, timeout=30)
            if rr.status_code == 200 and isinstance(rr.json(), list):
                bad = [o for o in rr.json() if o.get("call_ref") == self.ref]
                assert not bad, f"order auto-created at {path}: {bad}"

    def test_offer_flagged_not_purchase(self, client):
        r = client.get(f"{API}/missions/{MISSION_ID}/offers", timeout=60)
        if r.status_code != 200:
            pytest.skip(f"offers endpoint {r.status_code}")
        offers = r.json()
        offers = offers if isinstance(offers, list) else offers.get("offers", [])
        vc = [o for o in offers if o.get("source") == "voice_call"]
        for o in vc:
            assert "within_authority" in o
            if o.get("within_authority") is False:
                assert o.get("status") == "OUT_OF_AUTHORITY"

    def test_double_approve_rejected(self, client):
        r = client.post(f"{API}/voice/console/approve/{self.ref}", timeout=60)
        assert r.status_code == 400, r.text[:300]

    def test_analyze_existing_transcript(self, client):
        r = client.post(f"{API}/voice/console/analyze/{self.ref}", timeout=180)
        assert r.status_code == 200, r.text[:400]
        an = r.json()
        assert an.get("summary")
        assert isinstance(an.get("terms"), list)

    def test_analyze_without_transcript(self, client):
        c = client.post(f"{API}/voice/console/config", json=_objective(), timeout=60)
        ref = c.json()["session_ref"]
        r = client.post(f"{API}/voice/console/analyze/{ref}", timeout=60)
        assert r.status_code == 400, r.text[:300]

    def test_session_fetch(self, client):
        r = client.get(f"{API}/voice/console/session/{self.ref}", timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert d["session_ref"] == self.ref
        assert len(d["transcript"]) >= 4
        assert "_id" not in d

    def test_session_not_found(self, client):
        r = client.get(f"{API}/voice/console/session/nope123", timeout=30)
        assert r.status_code == 404

    def test_history(self, client):
        r = client.get(f"{API}/voice/console/history", params={"mission_id": MISSION_ID}, timeout=60)
        assert r.status_code == 200
        docs = r.json()
        assert isinstance(docs, list) and docs
        assert all(d["mission_id"] == MISSION_ID for d in docs)
        mine = [d for d in docs if d["session_ref"] == self.ref]
        assert mine, "completed call missing from history"
        d = mine[0]
        assert "key_outcome" in d and d["key_outcome"]
        assert d["recording_state"] in (
            "RECORDING_REQUESTED", "RECORDING_ACTIVE", "RECORDING_AVAILABLE",
            "RECORDING_FAILED", "RECORDING_NOT_SUPPORTED")
        assert d["transcript_status"] == "AVAILABLE"
        assert "transcript" not in d

    # --------------------------- outcome gate ---------------------------
    def test_outcome_invalid(self, client):
        r = client.post(f"{API}/voice/console/outcome/{self.ref}",
                        json={"decision": "BUY_NOW"}, timeout=30)
        assert r.status_code == 400

    def test_outcome_approve_then_reject(self, client):
        r = client.post(f"{API}/voice/console/outcome/{self.ref}",
                        json={"decision": "APPROVE_NEXT", "note": "TEST_ok"}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["outcome"]["decision"] == "APPROVE_NEXT"
        assert d["outcome"]["note"] == "TEST_ok"
        assert d["outcome"]["by"]
        # persisted?
        g = client.get(f"{API}/voice/console/session/{self.ref}", timeout=30).json()
        assert g["outcome"]["decision"] == "APPROVE_NEXT"

        r2 = client.post(f"{API}/voice/console/outcome/{self.ref}",
                         json={"decision": "REJECT", "note": "TEST_reject"}, timeout=60)
        assert r2.status_code == 200
        assert r2.json()["outcome"]["decision"] == "REJECT"

    def test_outcome_does_not_create_order(self, client):
        for path in (f"{API}/orders", f"{API}/purchases"):
            rr = client.get(path, timeout=30)
            if rr.status_code == 200 and isinstance(rr.json(), list):
                assert not [o for o in rr.json() if o.get("call_ref") == self.ref]


# --------------------------- live mode honesty ---------------------------
class TestLiveMode:
    def test_live_call_fails_honestly(self, client):
        r = client.post(f"{API}/voice/console/config",
                        json=_objective(test_mode=False), timeout=60)
        assert r.status_code == 200
        ref = r.json()["session_ref"]
        a = client.post(f"{API}/voice/console/approve/{ref}", timeout=120)
        assert a.status_code == 200, a.text[:400]
        d = a.json()
        print("LIVE approve response:", d)
        assert d["status"] in ("failed", "NOT_CONFIGURED"), d
        s = client.get(f"{API}/voice/console/session/{ref}", timeout=30).json()
        assert s["status"] in ("failed", "NOT_CONFIGURED")
        assert not s.get("transcript")
        assert s.get("analysis") in (None, {})


# --------------------------- webhook security ---------------------------
class TestWebhookSecurity:
    def test_status_callback_no_token(self):
        r = requests.post(f"{API}/voice/console/status-callback",
                          data={"CallSid": "x", "CallStatus": "completed"}, timeout=30)
        assert r.status_code == 401, f"{r.status_code}: {r.text[:200]}"

    def test_status_callback_bad_token(self):
        r = requests.post(f"{API}/voice/console/status-callback?token=wrong",
                          data={"CallSid": "x"}, timeout=30)
        assert r.status_code == 401

    def test_voice_start_no_token(self):
        r = requests.post(f"{API}/voice/console/voice-start",
                          data={"CallSid": "x"}, timeout=30)
        assert r.status_code == 401

    def test_transcript_push_no_token(self):
        r = requests.post(f"{API}/voice/console/transcript/abc",
                          json={"speaker": "AI", "text": "hi"}, timeout=30)
        assert r.status_code == 401

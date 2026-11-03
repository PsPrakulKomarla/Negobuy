"""Tests for the Direct Business Negotiation feature (/api/direct-negotiation)
plus a light regression of the hardened Call Center guards."""
import os
import re
import time
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
backend_env = dotenv_values("/app/backend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"
WEBHOOK_TOKEN = backend_env.get("EXOTEL_WEBHOOK_TOKEN")

STATE = {}


def _creds():
    content = Path("/app/memory/test_credentials.md").read_text(encoding="utf-8")
    email = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?Email(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    pwd = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?Password(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    if not email or not pwd:
        pytest.skip("credentials missing")
    return {"email": email.group(1), "password": pwd.group(1)}


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json=_creds(), timeout=60)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    token = r.json().get("access_token")
    assert token
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="session")
def other_org_client():
    """A user in a different organization (for isolation checks)."""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    email = f"TEST_dn_{uuid.uuid4().hex[:8]}@qamail.com"
    r = s.post(f"{API}/auth/register", json={
        "email": email, "password": "QaTest@2026", "name": "TEST_DN Other",
        "organization_name": "TEST_DN Other Co"}, timeout=60)
    if r.status_code not in (200, 201):
        pytest.skip(f"cannot register second org: {r.status_code} {r.text[:200]}")
    token = r.json().get("access_token")
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def _prepare_body(**over):
    body = {
        "business_name": "TEST_Sharma Tiles & Sanitary",
        "contact_name": "Rakesh Sharma",
        "phone_number": "9876500022",
        "business_description": "Local tiles distributor",
        "what_to_buy": "500 boxes of 600x600 vitrified floor tiles, glossy white",
        "product": "Vitrified floor tiles 600x600 glossy white",
        "quantity": 500,
        "target_price": 420.0,
        "max_authorized_price": 450.0,
        "currency": "INR",
        "delivery_location": "Pune, Maharashtra",
        "delivery_deadline_days": 10,
        "warranty_requirements": "1 year replacement for manufacturing defects",
        "other_instructions": "TEST_ automated QA run. Do not commit any purchase.",
    }
    body.update(over)
    return body


# --------------------------- 1. PREPARE ---------------------------
class TestPrepare:
    def test_auth_ok(self, client):
        r = client.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 200
        assert r.json().get("email") == _creds()["email"]

    def test_prepare_rejects_inverted_authority(self, client):
        r = client.post(f"{API}/direct-negotiation/prepare",
                        json=_prepare_body(target_price=600.0, max_authorized_price=450.0),
                        timeout=90)
        assert r.status_code == 400, r.text[:300]
        assert "maximum authorized" in r.json().get("detail", "").lower()

    def test_prepare_success(self, client):
        r = client.post(f"{API}/direct-negotiation/prepare", json=_prepare_body(), timeout=180)
        assert r.status_code == 200, r.text[:500]
        d = r.json()
        assert "_id" not in d
        STATE["mission_id"] = d["mission_id"]
        STATE["vendor_id"] = d["vendor_id"]

        # mission
        m = d["mission"]
        assert m["source"] == "direct_negotiation"
        assert m["organization_id"]
        assert m["quantity"] == 500
        assert m["currency"] == "INR"
        assert m["status"] == "REQUIREMENT_REVIEW"

        # business vendor
        b = d["business"]
        assert b["name"] == "TEST_Sharma Tiles & Sanitary"
        assert b["mission_id"] == d["mission_id"]
        assert b["whatsapp_number"]
        assert b["contact_phones"] and b["contact_phones"][0].startswith("+91")

        # requirement intelligence
        req = d["requirement"]
        assert isinstance(req, dict) and req, "requirement empty"

        # plan
        p = d["plan"]
        for k in ("primary_objective", "key_questions", "delivery_questions",
                  "payment_questions", "risks", "opening_line"):
            assert k in p, f"plan missing {k}"
        assert isinstance(p["key_questions"], list) and len(p["key_questions"]) >= 1
        assert isinstance(p["opening_line"], str) and len(p["opening_line"]) > 10

        # frozen authority
        a = d["authority"]
        assert a["target_price_per_unit"] == 420.0
        assert a["max_price_per_unit"] == 450.0
        assert a["quantity"] == 500

        # honest provider statuses
        pr = d["providers"]
        assert pr["whatsapp_fallback"]["state"] == "NOT_CONFIGURED"
        assert pr["call"]["provider"] == "exotel"
        assert pr["transcript"]["state"] in ("READY", "NOT_CONFIGURED")

    def test_thread_created_shared(self, client):
        r = client.get(f"{API}/direct-negotiation/{STATE['mission_id']}", timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["thread"] is not None, "shared negotiation thread not created"
        assert d["thread"]["mission_id"] == STATE["mission_id"]
        assert d["thread"]["vendor_id"] == STATE["vendor_id"]
        assert d["business"]["id"] == STATE["vendor_id"]
        assert d["calls"] == [] and d["offers"] == []

    def test_list_direct_missions(self, client):
        r = client.get(f"{API}/direct-negotiation", timeout=60)
        assert r.status_code == 200, r.text[:300]
        docs = r.json()
        assert isinstance(docs, list)
        ids = [x["id"] for x in docs]
        assert STATE["mission_id"] in ids
        assert all(x.get("source") == "direct_negotiation" for x in docs)

    def test_org_isolation_404(self, other_org_client):
        r = other_org_client.get(f"{API}/direct-negotiation/{STATE['mission_id']}", timeout=60)
        assert r.status_code == 404, r.text[:300]
        r2 = other_org_client.get(f"{API}/direct-negotiation/{STATE['mission_id']}/timeline",
                                  timeout=60)
        assert r2.status_code == 404


# --------------------------- 2. CALL VIA CALL CENTER ---------------------------
class TestApprovedCall:
    def test_config_and_approve_simulated_call(self, client):
        cfg = client.post(f"{API}/voice/console/config", json={
            "mission_id": STATE["mission_id"], "vendor_id": STATE["vendor_id"],
            "to_number": "9876500022", "supplier_name": "TEST_Sharma Tiles & Sanitary",
            "product": "Vitrified floor tiles 600x600", "quantity": 500,
            "current_price": 480.0, "target_price": 420.0, "max_authorized_price": 450.0,
            "delivery_location": "Pune, Maharashtra", "delivery_deadline_days": 10,
            "currency": "INR", "test_mode": True}, timeout=90)
        assert cfg.status_code == 200, cfg.text[:400]
        ref = cfg.json()["session_ref"]
        STATE["call_ref"] = ref
        assert cfg.json()["approved"] is False

        ap = client.post(f"{API}/voice/console/approve/{ref}", timeout=120)
        assert ap.status_code == 200, ap.text[:400]

        deadline = time.time() + 180
        status = None
        while time.time() < deadline:
            s = client.get(f"{API}/voice/console/session/{ref}", timeout=60)
            assert s.status_code == 200
            doc = s.json()
            status = doc.get("status")
            if status in ("SIMULATED_COMPLETE", "COMPLETED", "FAILED", "NOT_CONFIGURED"):
                break
            time.sleep(5)
        assert status == "SIMULATED_COMPLETE", f"unexpected call status {status}"
        assert len(doc.get("transcript") or []) >= 3
        assert doc.get("analysis"), "no analysis on simulated call"

    def test_thread_has_phone_event(self, client):
        r = client.get(f"{API}/direct-negotiation/{STATE['mission_id']}", timeout=60)
        assert r.status_code == 200
        thread = r.json()["thread"]
        events = thread.get("events") or []
        phone_events = [e for e in events if e.get("channel") == "phone"]
        assert phone_events, f"no phone event in shared thread; channels={[e.get('channel') for e in events]}"
        assert any(e.get("role") in ("system", "buyer_ai", "supplier") for e in phone_events)


# --------------------------- 3. WHATSAPP FALLBACK ---------------------------
class TestFallback:
    def test_fallback_rejects_non_eligible_call(self, client):
        r = client.post(f"{API}/direct-negotiation/{STATE['mission_id']}/fallback",
                        json={"call_ref": STATE["call_ref"], "simulate": True}, timeout=60)
        assert r.status_code == 400, r.text[:300]
        assert "fallback-eligible" in r.json().get("detail", "")

    def test_fallback_simulate_false_not_configured(self, client):
        r = client.post(f"{API}/direct-negotiation/{STATE['mission_id']}/fallback",
                        json={"simulate": False}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["status"] == "NOT_CONFIGURED"
        assert "not configured" in d["message"].lower()

    def test_fallback_simulated(self, client):
        r = client.post(f"{API}/direct-negotiation/{STATE['mission_id']}/fallback",
                        json={"simulate": True}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["status"] == "sent"
        assert d["delivery"]["state"] == "SIMULATED"
        assert d["delivery"]["simulated"] is True
        assert d["delivery"]["ok"] is False
        msg = d["message"]
        assert msg["kind"] == "fallback" and msg["direction"] == "outbound"
        assert msg["channel"] == "whatsapp" and msg["text"]
        assert "_id" not in msg

    def test_fallback_second_call_409(self, client):
        r = client.post(f"{API}/direct-negotiation/{STATE['mission_id']}/fallback",
                        json={"simulate": True}, timeout=60)
        assert r.status_code == 409, r.text[:300]

    def test_fallback_stored_once_and_in_thread(self, client):
        r = client.get(f"{API}/direct-negotiation/{STATE['mission_id']}", timeout=60)
        d = r.json()
        fb = [m for m in d["messages"] if m.get("kind") == "fallback"]
        assert len(fb) == 1
        wa_events = [e for e in (d["thread"].get("events") or [])
                     if e.get("channel") == "whatsapp"]
        assert wa_events, "fallback not appended to shared thread"

    def test_fallback_audited(self, client):
        r = client.get(f"{API}/direct-negotiation/{STATE['mission_id']}/timeline", timeout=60)
        assert r.status_code == 200
        types = [i["type"] for i in r.json()["timeline"]]
        assert "whatsapp_fallback" in types


# --------------------------- 4. SHARED-MEMORY WHATSAPP REPLY ---------------------------
class TestWhatsAppReply:
    def test_reply_enforces_authority(self, client):
        r = client.post(f"{API}/direct-negotiation/{STATE['mission_id']}/whatsapp-reply",
                        json={"text": "Sorry I missed your call. I can do 460 per box for 500 "
                                      "boxes, 7 days delivery", "simulate": True}, timeout=180)
        assert r.status_code == 200, r.text[:500]
        d = r.json()
        assert isinstance(d.get("reply"), str) and len(d["reply"]) > 5
        offer = d.get("current_offer") or {}
        assert offer, "no current_offer extracted from supplier reply"
        assert float(offer.get("unit_price")) == 460.0, offer
        assert d["within_authority"] is False, d
        assert d["delivery"]["state"] == "SIMULATED"

    def test_reply_messages_stored(self, client):
        r = client.get(f"{API}/direct-negotiation/{STATE['mission_id']}", timeout=60)
        msgs = r.json()["messages"]
        inbound = [m for m in msgs if m.get("direction") == "inbound"]
        outbound = [m for m in msgs if m.get("direction") == "outbound"]
        assert any("460" in (m.get("text") or "") for m in inbound)
        assert len(outbound) >= 2  # fallback + AI reply

    def test_reply_empty_text_400(self, client):
        r = client.post(f"{API}/direct-negotiation/{STATE['mission_id']}/whatsapp-reply",
                        json={"text": "   "}, timeout=60)
        assert r.status_code == 400


# --------------------------- 5. TIMELINE ---------------------------
class TestTimeline:
    def test_unified_timeline(self, client):
        r = client.get(f"{API}/direct-negotiation/{STATE['mission_id']}/timeline", timeout=60)
        assert r.status_code == 200
        items = r.json()["timeline"]
        assert len(items) >= 6
        types = [i["type"] for i in items]
        for expected in ("mission_created", "negotiation_plan_created", "call_approved",
                         "whatsapp_fallback", "whatsapp_reply"):
            assert expected in types, f"{expected} missing from timeline: {types}"
        titles = [i["title"] for i in items]
        assert "Mission created" in titles
        assert "AI prepared negotiation plan" in titles
        ats = [i["at"] for i in items]
        assert ats == sorted(ats), "timeline not chronological"


# --------------------------- 6. FINAL REPORT ---------------------------
class TestReport:
    def test_generate_report(self, client):
        r = client.post(f"{API}/direct-negotiation/{STATE['mission_id']}/generate-report",
                        timeout=240)
        assert r.status_code == 200, r.text[:500]
        a = r.json()
        assert isinstance(a.get("summary"), str) and a["summary"]
        terms = a.get("terms")
        assert isinstance(terms, list) and terms
        allowed = {"CONFIRMED", "PROPOSED", "UNCLEAR", "REQUIRES_HUMAN_APPROVAL"}
        for t in terms:
            assert t.get("status") in allowed, t
        assert "within_authority" in a
        assert a.get("self_review") is not None

    def test_report_persisted(self, client):
        r = client.get(f"{API}/direct-negotiation/{STATE['mission_id']}", timeout=60)
        assert r.json().get("report"), "report not persisted on mission"

    def test_report_400_without_conversation(self, client):
        p = client.post(f"{API}/direct-negotiation/prepare",
                        json=_prepare_body(business_name="TEST_Empty Traders"), timeout=180)
        assert p.status_code == 200, p.text[:300]
        mid = p.json()["mission_id"]
        STATE["empty_mission"] = mid
        r = client.post(f"{API}/direct-negotiation/{mid}/generate-report", timeout=120)
        assert r.status_code == 400, r.text[:300]
        assert "No conversation" in r.json().get("detail", "")


# --------------------------- 7. HUMAN APPROVAL GATE ---------------------------
class TestDecision:
    def test_invalid_action_400(self, client):
        r = client.post(f"{API}/direct-negotiation/{STATE['mission_id']}/decision",
                        json={"action": "BUY_NOW"}, timeout=60)
        assert r.status_code == 400

    def test_approve_next(self, client):
        r = client.post(f"{API}/direct-negotiation/{STATE['mission_id']}/decision",
                        json={"action": "APPROVE_NEXT", "note": "TEST_ proceed"}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["ok"] is True
        assert d["decision"]["action"] == "APPROVE_NEXT"
        full = client.get(f"{API}/direct-negotiation/{STATE['mission_id']}", timeout=60).json()
        assert full["decision"]["action"] == "APPROVE_NEXT"
        tl = client.get(f"{API}/direct-negotiation/{STATE['mission_id']}/timeline",
                        timeout=60).json()["timeline"]
        assert "human_approved" in [i["type"] for i in tl]

    def test_no_purchase_or_order_created(self, client):
        from pymongo import MongoClient
        mongo_url = backend_env.get("MONGO_URL")
        db_name = backend_env.get("DB_NAME")
        assert mongo_url and db_name
        db = MongoClient(mongo_url)[db_name]
        for coll in ("purchases", "orders", "purchase_orders"):
            n = db[coll].count_documents({"mission_id": {"$in": [STATE["mission_id"],
                                                                STATE.get("empty_mission")]}})
            assert n == 0, f"{coll} has {n} docs for the direct negotiation mission"
        m = db.missions.find_one({"id": STATE["mission_id"]})
        assert m["status"] in ("REQUIREMENT_REVIEW", "NEGOTIATING"), m["status"]


# --------------------------- 8. CALL CENTER HARDENING REGRESSION ---------------------------
class TestCallCenterHardening:
    def _cfg(self, **over):
        body = {"mission_id": STATE["mission_id"], "vendor_id": STATE["vendor_id"],
                "to_number": "9876500022", "product": "tiles", "quantity": 500,
                "target_price": 420.0, "max_authorized_price": 450.0, "test_mode": True}
        body.update(over)
        return body

    def test_config_inverted_authority_400(self, client):
        r = client.post(f"{API}/voice/console/config",
                        json=self._cfg(target_price=500.0, max_authorized_price=450.0), timeout=60)
        assert r.status_code == 400, r.text[:300]

    def test_config_negative_price_400(self, client):
        r = client.post(f"{API}/voice/console/config",
                        json=self._cfg(target_price=-10.0), timeout=60)
        assert r.status_code == 400, r.text[:300]
        r2 = client.post(f"{API}/voice/console/config",
                         json=self._cfg(current_price=-5.0), timeout=60)
        assert r2.status_code == 400, r2.text[:300]

    def test_webhooks_require_token(self, client):
        r = requests.post(f"{API}/voice/console/voice-start",
                          data={"CallSid": "x", "CustomField": "nope"}, timeout=60)
        assert r.status_code == 401, r.text[:200]
        r2 = requests.post(f"{API}/voice/console/status-callback",
                           data={"CallSid": "x", "CustomField": "nope"}, timeout=60)
        assert r2.status_code == 401, r2.text[:200]

    def test_webhooks_reject_unapproved_session(self, client):
        if not WEBHOOK_TOKEN:
            pytest.skip("EXOTEL_WEBHOOK_TOKEN missing")
        cfg = client.post(f"{API}/voice/console/config", json=self._cfg(), timeout=60)
        assert cfg.status_code == 200, cfg.text[:300]
        ref = cfg.json()["session_ref"]
        assert cfg.json()["approved"] is False

        r = requests.post(f"{API}/voice/console/voice-start?token={WEBHOOK_TOKEN}",
                          data={"CallSid": "TEST_SID_1", "CustomField": ref}, timeout=60)
        assert r.status_code == 409, f"voice-start on unapproved: {r.status_code} {r.text[:200]}"
        r2 = requests.post(f"{API}/voice/console/status-callback?token={WEBHOOK_TOKEN}",
                           data={"CallSid": "TEST_SID_1", "CustomField": ref,
                                 "Status": "completed"}, timeout=60)
        assert r2.status_code == 409, f"status-callback on unapproved: {r2.status_code} {r2.text[:200]}"

        # session must remain CONFIGURED / unapproved
        s = client.get(f"{API}/voice/console/session/{ref}", timeout=60).json()
        assert s["status"] == "CONFIGURED" and s["approved"] is False

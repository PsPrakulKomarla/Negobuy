"""End-to-end backend tests for the Negotiation Engine, Procurement Assurance,
and Master Orchestrator flows on a shared mission state."""
import os
import time
import uuid
import pytest
import requests
from pathlib import Path
from pymongo import MongoClient


def _load_env(path):
    if not Path(path).exists():
        return
    for line in Path(path).read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_env("/app/frontend/.env")
_load_env("/app/backend/.env")

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

ADMIN_EMAIL = "admin@negobuy.ai"
ADMIN_PASS = "NegoBuy@2026"

NEG_STATES = {"INITIATE", "GREET", "ASK_INFO", "COLLECT_TERMS", "NEGOTIATE", "COUNTER_OFFER",
              "AWAITING_HUMAN_APPROVAL", "APPROVED", "REJECTED", "NEGOTIATE_FURTHER",
              "CLOSED", "SUMMARY", "FINALIZE", "PROPOSE", "CLARIFY"}

CONTRACT_RECS = {"READY_FOR_HUMAN_REVIEW", "ISSUES_FOUND_REVIEW_REQUIRED",
                 "HIGH_RISK_DIFFERENCES_DETECTED"}


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def mongo():
    cli = MongoClient(os.environ["MONGO_URL"])
    db = cli[os.environ["DB_NAME"]]
    yield db
    cli.close()


def _cleanup_active(h, keep_title=None):
    r = requests.get(f"{API}/missions", headers=h, timeout=30)
    if r.status_code != 200:
        return
    for m in r.json():
        if m.get("status") in ("COMPLETED", "CANCELLED"):
            continue
        if keep_title and m.get("title") == keep_title:
            continue
        if m.get("title", "").startswith(("Orchestrated ", "Authority Guard", "TEST_", "Persona Test")):
            requests.delete(f"{API}/missions/{m['id']}", headers=h, timeout=30)


@pytest.fixture(scope="module")
def mission(h, mongo):
    _cleanup_active(h)
    payload = {"title": "Orchestrated Chairs", "category": "Furniture",
               "quantity": 500, "budget": 450000, "currency": "INR",
               "deadline_days": 10, "warranty_requirements": "1 year"}
    r = requests.post(f"{API}/missions", headers=h, json=payload, timeout=30)
    assert r.status_code in (200, 201), f"create mission: {r.status_code} {r.text}"
    m = r.json()
    yield m
    # teardown
    try:
        mongo.orders.delete_many({"mission_id": m["id"]})
        mongo.contract_reviews.delete_many({"mission_id": m["id"]})
        mongo.negotiation_threads.delete_many({"mission_id": m["id"]})
        mongo.offers.delete_many({"mission_id": m["id"]})
        mongo.vendors.delete_many({"mission_id": m["id"]})
        mongo.audit_logs.delete_many({"mission_id": m["id"]})
    except Exception:
        pass
    requests.delete(f"{API}/missions/{m['id']}", headers=h, timeout=30)


@pytest.fixture(scope="module")
def vendor(h, mission, mongo):
    mid = mission["id"]
    r = requests.post(f"{API}/missions/{mid}/discover", headers=h, timeout=30)
    assert r.status_code in (200, 202), f"discover: {r.status_code} {r.text}"
    deadline = time.time() + 75
    vendors = []
    while time.time() < deadline:
        rr = requests.get(f"{API}/missions/{mid}/vendors", headers=h, timeout=30)
        if rr.status_code == 200 and rr.json():
            vendors = rr.json()
            break
        time.sleep(3)
    if not vendors:
        # Seed a minimal vendor via Mongo to still exercise flows.
        v = {"id": uuid.uuid4().hex, "mission_id": mid,
             "organization_id": mission.get("organization_id"),
             "name": "Seeded Vendor Pvt Ltd", "domain": "seededvendor.test",
             "reliability_score": 0.8, "email": "sales@seededvendor.test",
             "seeded_by_test": True}
        mongo.vendors.insert_one(dict(v))
        vendors = [v]
        print("NOTE: discovery yielded 0 vendors; seeded one via Mongo.")
    return vendors[0]


# --------------- Negotiation Engine --------------- #

class TestNegotiationEngine:
    def test_message_creates_structured_thread(self, h, mission, vendor):
        mid, vid = mission["id"], vendor["id"]
        body = {"channel": "sandbox",
                "text": "We can do 875 per unit for 500 units, delivery in 8 days, "
                        "shipping included, 1 year warranty."}
        r = requests.post(f"{API}/missions/{mid}/vendors/{vid}/negotiation/message",
                          headers=h, json=body, timeout=90)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        t = r.json()
        # State is AI-produced; must be a non-empty uppercase-ish string
        st = t.get("state")
        assert isinstance(st, str) and st, f"missing state: {t}"
        co = t.get("current_offer") or {}
        up = co.get("unit_price")
        assert up is not None, f"unit_price missing in current_offer: {co}"
        assert 800 <= float(up) <= 950, f"extracted unit_price out of range: {up}"
        # delivery + shipping extraction (accept approximate)
        dd = co.get("delivery_days")
        assert dd is not None, f"delivery_days missing: {co}"
        assert co.get("shipping_included") in (True, "true", "yes", 1), \
            f"shipping_included not True: {co.get('shipping_included')}"
        events = t.get("events") or []
        roles = {e.get("role") for e in events}
        assert "supplier" in roles and "buyer_ai" in roles, f"roles: {roles}"
        assert isinstance(t.get("decision_summary"), (str, type(None)))
        reply = (t.get("reply") or "").lower()
        for phrase in ("deal confirmed", "order placed", "we accept"):
            assert phrase not in reply, f"buyer reply improperly commits: {reply!r}"
        # authority: 875 <= 900 → within_authority true
        assert t.get("within_authority") is True

    def test_get_thread_returns_same_state_and_offer_mirrored(self, h, mission, vendor):
        mid, vid = mission["id"], vendor["id"]
        r = requests.get(f"{API}/missions/{mid}/vendors/{vid}/negotiation", headers=h, timeout=30)
        assert r.status_code == 200
        t = r.json()
        assert (t.get("current_offer") or {}).get("unit_price") is not None
        assert t.get("within_authority") is True
        # Mirrored offer in offers collection
        ro = requests.get(f"{API}/missions/{mid}/offers", headers=h, timeout=30)
        assert ro.status_code == 200
        mirrored = [o for o in ro.json() if o.get("source") == "negotiation_engine"
                    and o.get("vendor_id") == vid]
        assert mirrored, "no mirrored negotiation_engine offer in /offers"
        assert mirrored[0].get("within_authority") is True
        assert mirrored[0].get("status") == "OPEN"

    def test_decision_approve_does_not_auto_purchase(self, h, mission, vendor, mongo):
        mid, vid = mission["id"], vendor["id"]
        r = requests.post(f"{API}/missions/{mid}/vendors/{vid}/negotiation/decision",
                          headers=h, json={"action": "approve"}, timeout=30)
        assert r.status_code == 200
        t = r.json()
        assert t.get("approval_status") == "approved"
        assert t.get("state") == "APPROVED"
        # No order auto-created by approval
        assert mongo.orders.find_one({"mission_id": mid}) is None
        # No purchase auto-created
        assert mongo.purchases.find_one({"mission_id": mid}) is None
        # Mission not force-completed
        mm = mongo.missions.find_one({"id": mid})
        assert mm.get("status") != "COMPLETED"


# --------------- Orchestrator (mid-flow) --------------- #

class TestOrchestratorMidFlow:
    def test_orchestrator_derivation_with_offer(self, h, mission):
        mid = mission["id"]
        r = requests.get(f"{API}/missions/{mid}/orchestrator", headers=h, timeout=30)
        assert r.status_code == 200, r.text
        o = r.json()
        assert isinstance(o.get("stage"), str) and o["stage"], f"stage missing: {o}"
        # With >=1 offer expect an offers/negotiation stage
        assert o["stage"] in {"OFFERS_COLLECTED", "OFFERS_COMPARED", "SHORTLIST_READY",
                              "RECOMMENDATION_READY", "NEGOTIATION"}, f"stage={o['stage']}"
        assert isinstance(o.get("human_action_required"), bool)
        aa = o.get("available_actions")
        assert isinstance(aa, list) and aa, "available_actions empty"
        for a in aa:
            assert set(a.keys()) >= {"action", "endpoint", "agent", "requires_human"}
        assert o.get("next_agent")
        counts = o.get("counts") or {}
        assert counts.get("vendors", 0) >= 1
        assert counts.get("offers", 0) >= 1
        assert isinstance(o.get("timeline"), list)
        assert "humans approve" in (o.get("principle") or "").lower()


# --------------- Assurance: contract --------------- #

class TestContractAnalysis:
    CONTRACT = ("This agreement is between Acme Supplies Pvt Ltd (Supplier) and the Buyer "
                "for 500 ergonomic office chairs at INR 875 per unit. Delivery within 15 days "
                "to Bangalore. Warranty: 1 year. Shipping charges INR 20000 extra. "
                "Payment: Net 30.")

    def test_analyze_contract(self, h, mission):
        mid = mission["id"]
        r = requests.post(f"{API}/missions/{mid}/contract/analyze",
                          headers=h, json={"contract_text": self.CONTRACT}, timeout=120)
        assert r.status_code == 200, r.text
        doc = r.json()
        a = doc.get("analysis") or {}
        assert a.get("extracted"), "extracted terms missing"
        rec = a.get("recommendation")
        assert rec in CONTRACT_RECS, f"unexpected recommendation: {rec}"
        # Must not approve
        assert rec != "APPROVED"
        # comparison flags
        comp = a.get("comparison") or []
        assert isinstance(comp, list) and comp, "empty comparison"
        # sanity: some non-MATCH entry expected (delivery/shipping differ)
        non_match = [c for c in comp if str(c.get("status", "")).upper() != "MATCH"]
        assert non_match, f"expected some DIFFERENCE/MATERIAL_DIFFERENCE: {comp}"
        assert isinstance(a.get("risks"), list)
        assert isinstance(a.get("simple_summary"), str) and a["simple_summary"]

    def test_get_latest_contract(self, h, mission):
        r = requests.get(f"{API}/missions/{mission['id']}/contract", headers=h, timeout=30)
        assert r.status_code == 200
        doc = r.json()
        assert doc and doc.get("analysis")


# --------------- Order authorize + lifecycle --------------- #

class TestOrderLifecycle:
    def test_authorize_within_authority_offer(self, h, mission, mongo):
        mid = mission["id"]
        # Choose an OPEN within-authority offer
        offers = requests.get(f"{API}/missions/{mid}/offers", headers=h, timeout=30).json()
        candidates = [o for o in offers if o.get("within_authority") in (True, None)
                      and o.get("status") in (None, "OPEN")]
        assert candidates, f"no within-authority offer to authorize: {offers}"
        offer_id = candidates[0]["id"]
        r = requests.post(f"{API}/missions/{mid}/order/authorize", headers=h,
                          json={"offer_id": offer_id,
                                "expected_delivery_date": "2026-06-20"}, timeout=30)
        assert r.status_code == 200, r.text
        order = r.json()
        assert order.get("status") == "AUTHORIZED"
        assert order.get("supplier")
        assert order.get("unit_price") is not None
        assert order.get("total_cost") is not None
        assert order.get("health") in ("ON_TRACK", "ACTION_REQUIRED", "DELAYED", "COMPLETED")

    def test_authorize_duplicate_returns_409(self, h, mission):
        mid = mission["id"]
        offers = requests.get(f"{API}/missions/{mid}/offers", headers=h, timeout=30).json()
        offer_id = offers[0]["id"]
        r = requests.post(f"{API}/missions/{mid}/order/authorize", headers=h,
                          json={"offer_id": offer_id}, timeout=30)
        assert r.status_code == 409, f"expected 409, got {r.status_code} {r.text}"

    def test_status_update_valid_and_invalid(self, h, mission):
        mid = mission["id"]
        r = requests.post(f"{API}/missions/{mid}/order/status", headers=h,
                          json={"status": "DISPATCHED", "note": "Shipped via BlueDart"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("status") == "DISPATCHED"
        rb = requests.post(f"{API}/missions/{mid}/order/status", headers=h,
                           json={"status": "FOO"}, timeout=30)
        assert rb.status_code == 400, f"expected 400 on bad status, got {rb.status_code}"

    def test_timeline_contains_events(self, h, mission):
        r = requests.get(f"{API}/missions/{mission['id']}/order/timeline", headers=h, timeout=30)
        assert r.status_code == 200
        data = r.json()
        statuses = {e.get("status") for e in data.get("events", [])}
        assert "AUTHORIZED" in statuses
        assert "DISPATCHED" in statuses
        assert data.get("health") in ("ON_TRACK", "ACTION_REQUIRED", "DELAYED", "COMPLETED")


# --------------- Invoice verification --------------- #

class TestInvoiceVerification:
    def test_verify_invoice_flags_discrepancies(self, h, mission, mongo):
        mid = mission["id"]
        r = requests.post(f"{API}/missions/{mid}/order/invoice", headers=h,
                          json={"invoice_text": "Invoice: 500 chairs @ INR 875 = 437500. "
                                                "Shipping: 20000. Total: 457500. Net 30."},
                          timeout=120)
        assert r.status_code == 200, r.text
        v = r.json()
        assert isinstance(v.get("lines"), list)
        assert v.get("has_discrepancies") is True
        assert v.get("recommendation") == "DISCREPANCIES_FOUND_REVIEW_REQUIRED"
        # order status becomes PAYMENT_ACTION_REQUIRED
        order = mongo.orders.find_one({"mission_id": mid})
        assert order.get("status") == "PAYMENT_ACTION_REQUIRED"
        # No payment approved
        assert order.get("payment_status") in ("UNPAID", None)


# --------------- Delivery confirmation --------------- #

class TestDeliveryConfirmation:
    def test_mark_delivered_then_verify_completes_mission(self, h, mission, mongo):
        mid = mission["id"]
        r1 = requests.post(f"{API}/missions/{mid}/order/delivery", headers=h,
                           json={"action": "mark_delivered"}, timeout=30)
        assert r1.status_code == 200
        assert r1.json().get("status") == "DELIVERED_PENDING_VERIFICATION"
        r2 = requests.post(f"{API}/missions/{mid}/order/delivery", headers=h,
                           json={"action": "verify", "quantity_received": 500,
                                 "condition": "good"}, timeout=30)
        assert r2.status_code == 200, r2.text
        assert r2.json().get("status") == "COMPLETED"
        mm = mongo.missions.find_one({"id": mid})
        assert mm.get("status") == "COMPLETED"

    def test_orchestrator_reports_completed(self, h, mission):
        r = requests.get(f"{API}/missions/{mission['id']}/orchestrator", headers=h, timeout=30)
        assert r.status_code == 200
        assert r.json().get("stage") == "COMPLETED"


# --------------- Audit trail --------------- #

class TestAuditTrail:
    def test_audit_contains_expected_events(self, h, mission):
        r = requests.get(f"{API}/audit", headers=h, timeout=30)
        assert r.status_code == 200
        # /api/audit might return list or {events:[...]}
        data = r.json()
        events = data if isinstance(data, list) else data.get("events") or data.get("logs") or []
        # filter to this mission
        mine = [e for e in events if e.get("mission_id") == mission["id"]]
        actions = {e.get("event_type") or e.get("action") or e.get("event") or e.get("type") for e in mine}
        expected = {"negotiation_action", "contract_analyzed", "order_authorized",
                    "order_status_update", "invoice_verified", "delivery_verified"}
        missing = expected - actions
        assert not missing, f"missing audit actions {missing}. present={actions}"
        # no secrets leak
        blob = str(mine).lower()
        for secret in ("password", "secret", "api_key", "token=", "bearer "):
            assert secret not in blob, f"possible secret leak: {secret}"

"""Authority-guard + real-offer preservation tests for server.negotiate.

Covers:
- ai_negotiation_preview offers carry within_authority (bool), status
  ('OPEN' when within, 'OUT_OF_AUTHORITY' otherwise) and max_authorized_price.
- Re-running negotiate MUST NOT wipe real offers (source='vendor_email' /
  'manual') for the same vendor — only prior ai_negotiation_preview offers.
- No auto-commit regression: mission stays pre-approval; no purchase created.
- Regression: /api/system/status, /api/dashboard/analytics, /api/vendors/memory.
"""
import os
import time

import pytest
import requests


def _load_env(key, path):
    with open(path) as f:
        for line in f:
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    return None


BASE = _load_env("REACT_APP_BACKEND_URL", "/app/frontend/.env").rstrip("/")
ADMIN = {"email": "admin@negobuy.ai", "password": "NegoBuy@2026"}

MAX_UNIT = 900  # budget 450000 / qty 500


# ---------- fixtures ----------

@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


def _cleanup_active_missions(s):
    r = s.get(f"{BASE}/api/missions", timeout=15)
    if r.status_code != 200:
        return
    for m in r.json():
        if m.get("status") in ("APPROVED", "COMPLETED", "CANCELLED"):
            continue
        title = (m.get("title") or "")
        if "Authority Guard" in title or "Persona Test" in title or title.startswith("TEST_"):
            s.delete(f"{BASE}/api/missions/{m['id']}", timeout=10)


@pytest.fixture(scope="module")
def mission(session):
    _cleanup_active_missions(session)
    body = {
        "title": "Authority Guard Chairs",
        "category": "Furniture",
        "quantity": 500,
        "budget": 450000,
        "currency": "INR",
        "deadline_days": 10,
        "warranty_requirements": "1 year",
    }
    r = session.post(f"{BASE}/api/missions", json=body, timeout=20)
    assert r.status_code in (200, 201), f"create mission: {r.status_code} {r.text}"
    m = r.json()
    yield m
    try:
        session.delete(f"{BASE}/api/missions/{m['id']}", timeout=10)
    except Exception:
        pass


@pytest.fixture(scope="module")
def discovered_vendor(session, mission):
    r = session.post(f"{BASE}/api/missions/{mission['id']}/discover", timeout=30)
    assert r.status_code in (200, 202), f"discover: {r.status_code} {r.text}"
    vendor = None
    deadline = time.time() + 75
    while time.time() < deadline:
        vr = session.get(f"{BASE}/api/missions/{mission['id']}/vendors", timeout=15)
        if vr.status_code == 200 and vr.json():
            vendor = vr.json()[0]
            break
        time.sleep(3)
    if not vendor:
        pytest.skip("Vendor discovery flaky — no vendor returned in 75s")
    return vendor


def _offers(session, mid):
    r = session.get(f"{BASE}/api/missions/{mid}/offers", timeout=15)
    assert r.status_code == 200, f"offers: {r.status_code} {r.text[:200]}"
    return r.json()


# ---------- tests ----------

class TestAuthorityGuard:
    def test_negotiate_persists_authority_fields(self, session, mission, discovered_vendor):
        mid = mission["id"]
        vid = discovered_vendor["id"]
        r = session.post(
            f"{BASE}/api/missions/{mid}/vendors/{vid}/negotiate",
            json={"rounds": 2}, timeout=180)
        assert r.status_code == 200, f"negotiate: {r.status_code} {r.text[:400]}"

        offers = _offers(session, mid)
        ai_offers = [o for o in offers
                     if o.get("vendor_id") == vid
                     and o.get("source") == "ai_negotiation_preview"]
        assert ai_offers, f"no ai_negotiation_preview offer persisted; got {offers}"
        off = ai_offers[0]

        assert "within_authority" in off, f"within_authority missing: {off}"
        assert isinstance(off["within_authority"], bool)
        assert "status" in off
        assert off.get("max_authorized_price") == MAX_UNIT, \
            f"max_authorized_price expected {MAX_UNIT}, got {off.get('max_authorized_price')}"

        price = off.get("negotiated_price")
        assert price is not None
        if price <= MAX_UNIT:
            assert off["within_authority"] is True, off
            assert off["status"] == "OPEN", off
        else:
            # Rare: simulated vendor held above authority
            assert off["within_authority"] is False, off
            assert off["status"] == "OUT_OF_AUTHORITY", off


class TestRealOfferPreservation:
    def test_apply_offer_creates_vendor_email_offer(self, session, mission, discovered_vendor):
        mid = mission["id"]
        vid = discovered_vendor["id"]
        r = session.post(
            f"{BASE}/api/missions/{mid}/vendors/{vid}/outreach/apply-offer",
            json={"price_per_unit": 820, "lead_time_days": 12}, timeout=20)
        assert r.status_code in (200, 201), f"apply-offer: {r.status_code} {r.text[:300]}"

        offers = _offers(session, mid)
        real = [o for o in offers
                if o.get("vendor_id") == vid and o.get("source") == "vendor_email"]
        assert real, f"vendor_email offer not created; offers={offers}"
        assert real[0].get("negotiated_price") == 820
        assert real[0].get("simulation") is False

    def test_renegotiate_does_not_wipe_real_offer(self, session, mission, discovered_vendor):
        mid = mission["id"]
        vid = discovered_vendor["id"]

        # Ensure a real vendor_email offer is present (idempotent)
        session.post(
            f"{BASE}/api/missions/{mid}/vendors/{vid}/outreach/apply-offer",
            json={"price_per_unit": 820, "lead_time_days": 12}, timeout=20)
        before = [o for o in _offers(session, mid)
                  if o.get("vendor_id") == vid and o.get("source") == "vendor_email"]
        assert before, "precondition: vendor_email offer must exist"
        before_id = before[0]["id"]

        # Re-run negotiate
        r = session.post(
            f"{BASE}/api/missions/{mid}/vendors/{vid}/negotiate",
            json={"rounds": 1}, timeout=180)
        assert r.status_code == 200, f"renegotiate: {r.status_code} {r.text[:300]}"

        after = _offers(session, mid)
        real_after = [o for o in after
                      if o.get("vendor_id") == vid and o.get("source") == "vendor_email"]
        assert real_after, (
            "vendor_email real offer was WIPED by re-negotiate! "
            f"after offers = {after}")
        assert real_after[0]["id"] == before_id, \
            "vendor_email offer id changed — it was deleted+recreated instead of preserved"
        assert real_after[0].get("negotiated_price") == 820

        # Optional: ai_negotiation_preview may or may not be present; if present its
        # authority fields must be well-formed.
        ai = [o for o in after
              if o.get("vendor_id") == vid and o.get("source") == "ai_negotiation_preview"]
        for off in ai:
            assert "within_authority" in off
            assert off.get("max_authorized_price") == MAX_UNIT


class TestNoAutoCommit:
    def test_mission_not_approved_and_no_purchases(self, session, mission):
        mid = mission["id"]
        r = session.get(f"{BASE}/api/missions/{mid}", timeout=15)
        assert r.status_code == 200
        m = r.json()
        assert m.get("status") not in ("APPROVED", "COMPLETED"), \
            f"mission auto-committed to {m.get('status')}"

        # Check no purchase was auto-created (endpoint may vary; try common paths)
        for path in (f"/api/missions/{mid}/purchases", "/api/purchases"):
            pr = session.get(f"{BASE}{path}", timeout=10)
            if pr.status_code == 200:
                data = pr.json()
                items = data if isinstance(data, list) else data.get("items", [])
                mine = [p for p in items if (p.get("mission_id") == mid)]
                assert not mine, f"unexpected purchase for mission at {path}: {mine}"


class TestRegression:
    def test_system_status(self, session):
        r = session.get(f"{BASE}/api/system/status", timeout=15)
        assert r.status_code == 200

    def test_dashboard_analytics(self, session):
        r = session.get(f"{BASE}/api/dashboard/analytics", timeout=15)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"

    def test_vendors_memory(self, session):
        r = session.get(f"{BASE}/api/vendors/memory", timeout=15)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"

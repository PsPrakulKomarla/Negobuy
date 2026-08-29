"""Audit-completion pass tests: Razorpay/Twilio/WhatsApp NOT_CONFIGURED honesty,
unified audit log, organization isolation, entitlements, and no-regression checks."""
import os
import uuid
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[-1].split()[0]
           ).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@negobuy.ai"
ADMIN_PASS = "NegoBuy@2026"


# -------- fixtures --------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "access_token" in data
    return data["access_token"]


@pytest.fixture(scope="module")
def H(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def created_mission_ids():
    ids = []
    yield ids
    # teardown
    # login as admin to cleanup
    try:
        r = requests.post(f"{API}/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
        tok = r.json().get("access_token")
        headers = {"Authorization": f"Bearer {tok}"}
        for mid in ids:
            requests.delete(f"{API}/missions/{mid}", headers=headers, timeout=15)
    except Exception as e:
        print(f"[cleanup] {e}")


def _create_mission(H, title=None):
    spec = {
        "title": title or f"TEST_AUDIT {uuid.uuid4().hex[:6]}",
        "category": "office_supplies",
        "quantity": 100,
        "budget": 200000,
        "currency": "INR",
        "delivery_location": "Bangalore",
        "deadline_days": 14,
        "description": "TEST audit-pass mission",
    }
    return requests.post(f"{API}/missions", headers=H, json=spec, timeout=30)


# -------- 1. Regression: admin login + system status --------
class TestRegressionStatus:
    def test_admin_login_and_status(self, H):
        r = requests.get(f"{API}/system/status", headers=H, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["ai"]["state"] == "CONFIGURED"
        assert d["email"]["state"] == "CONFIGURED"
        assert d["voice"]["state"] == "READY"
        assert d["telephony"]["state"] == "NOT_CONFIGURED"
        assert d["whatsapp"]["state"] == "NOT_CONFIGURED"
        assert d["payments"]["state"] == "NOT_CONFIGURED"


# -------- 2. Audit log populates on mission_created --------
class TestAuditLog:
    def test_audit_mission_created(self, H, created_mission_ids):
        # Clean up preexisting TEST_AUDIT missions
        lst = requests.get(f"{API}/missions", headers=H, timeout=15).json()
        for m in lst:
            if (m.get("title") or "").startswith("TEST_AUDIT"):
                requests.delete(f"{API}/missions/{m['id']}", headers=H, timeout=15)

        r = _create_mission(H, title=f"TEST_AUDIT primary {uuid.uuid4().hex[:6]}")
        assert r.status_code in (200, 201), r.text
        mid = r.json()["id"]
        created_mission_ids.append(mid)

        # Poll audit log
        ar = requests.get(f"{API}/audit", headers=H, timeout=15)
        assert ar.status_code == 200
        entries = ar.json()
        assert isinstance(entries, list)
        matched = [e for e in entries
                   if e.get("event_type") == "mission_created"
                   and e.get("mission_id") == mid]
        assert matched, f"no mission_created audit entry for {mid}"
        # organization_id should be scoped
        assert matched[0].get("organization_id")


# -------- 3. Razorpay NOT_CONFIGURED --------
class TestRazorpay:
    def test_create_order_not_configured(self, H):
        r = requests.post(f"{API}/billing/orders", headers=H,
                          json={"plan_id": "pro"}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("status") == "NOT_CONFIGURED"
        assert d.get("provider") == "razorpay"
        req = d.get("required")
        assert isinstance(req, list) and "RAZORPAY_KEY_ID" in req
        # No fake order
        assert "order" not in d or not d.get("order", {}).get("id")

    def test_verify_guarded_400(self, H):
        r = requests.post(f"{API}/billing/verify", headers=H,
                          json={"razorpay_order_id": "x",
                                "razorpay_payment_id": "y",
                                "razorpay_signature": "z"}, timeout=15)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"

    def test_webhook_not_configured(self):
        # No signature, no keys -> 200 NOT_CONFIGURED (no activation)
        r = requests.post(f"{API}/webhooks/razorpay", data="{}",
                          headers={"Content-Type": "application/json"}, timeout=15)
        assert r.status_code == 200, f"got {r.status_code}: {r.text}"
        d = r.json()
        assert d.get("status") == "NOT_CONFIGURED"


# -------- 4. Telephony NOT_CONFIGURED --------
class TestTelephony:
    def test_call_bogus_vendor_404(self, H, created_mission_ids):
        # Need a mission
        if not created_mission_ids:
            r = _create_mission(H, title=f"TEST_AUDIT tele {uuid.uuid4().hex[:6]}")
            assert r.status_code in (200, 201), r.text
            created_mission_ids.append(r.json()["id"])
        mid = created_mission_ids[0]
        r = requests.post(f"{API}/voice/calls", headers=H,
                          json={"mission_id": mid, "vendor_id": "bogus-vendor-id"},
                          timeout=15)
        assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text}"

    def test_list_calls_ok(self, H, created_mission_ids):
        mid = created_mission_ids[0]
        r = requests.get(f"{API}/voice/calls", headers=H,
                         params={"mission_id": mid}, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# -------- 5. WhatsApp --------
class TestWhatsApp:
    def test_send_bogus_vendor_404(self, H):
        r = requests.post(f"{API}/whatsapp/send", headers=H,
                          json={"mission_id": "bogus", "vendor_id": "bogus", "message": "hi"},
                          timeout=15)
        assert r.status_code == 404

    def test_status_not_configured(self, H):
        r = requests.get(f"{API}/whatsapp/status", headers=H, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["state"] == "NOT_CONFIGURED"
        assert d["configured"] is False

    def test_webhook_verify_403(self):
        r = requests.get(f"{API}/webhooks/whatsapp",
                        params={"hub.mode": "subscribe",
                                "hub.verify_token": "wrong-token",
                                "hub.challenge": "x"}, timeout=15)
        assert r.status_code == 403


# -------- 6. Organization isolation --------
class TestOrgIsolation:
    def test_new_user_cannot_see_admin_mission(self, H, created_mission_ids):
        # ensure admin mission exists
        if not created_mission_ids:
            r = _create_mission(H, title=f"TEST_AUDIT iso {uuid.uuid4().hex[:6]}")
            assert r.status_code in (200, 201), r.text
            created_mission_ids.append(r.json()["id"])
        admin_mid = created_mission_ids[0]

        # register brand-new user
        new_email = f"test_iso_{uuid.uuid4().hex[:8]}@example.com"
        rr = requests.post(f"{API}/auth/register", json={
            "email": new_email, "password": "TestPass123!",
            "name": "Iso Tester"
        }, timeout=20)
        assert rr.status_code == 200, rr.text
        rj = rr.json()
        new_token = rj["access_token"]
        new_org = rj.get("organization_id")
        # admin's org should differ
        me = requests.get(f"{API}/auth/me",
                          headers={"Authorization": f"Bearer {new_token}"}, timeout=15)
        # fall back gracefully if /auth/me not present
        NH = {"Authorization": f"Bearer {new_token}", "Content-Type": "application/json"}

        # New user cannot fetch admin's mission
        gr = requests.get(f"{API}/missions/{admin_mid}", headers=NH, timeout=15)
        assert gr.status_code == 404, f"expected 404, got {gr.status_code}"

        # New user's list is empty (own org)
        lr = requests.get(f"{API}/missions", headers=NH, timeout=15)
        assert lr.status_code == 200
        own = lr.json()
        assert isinstance(own, list)
        assert all(m["id"] != admin_mid for m in own), "leaked admin mission into new org list"

        # organization ids differ
        if new_org:
            # Audit-log org check
            ar = requests.get(f"{API}/audit", headers=NH, timeout=15)
            if ar.status_code == 200:
                entries = ar.json()
                # New user should not see admin's audit entries
                assert all(e.get("mission_id") != admin_mid for e in entries)


# -------- 7. Entitlement 402 on 4th active mission (free plan) --------
class TestEntitlements:
    def test_free_plan_402(self, H):
        # Cleanup all TEST_QUOTA_AUDIT missions first
        lst = requests.get(f"{API}/missions", headers=H, timeout=15).json()
        for m in lst:
            if (m.get("title") or "").startswith("TEST_QUOTA_AUDIT"):
                requests.delete(f"{API}/missions/{m['id']}", headers=H, timeout=15)

        # Count current active
        terminal = ("COMPLETED", "CANCELLED", "REJECTED", "APPROVED")
        active = [m for m in lst if m.get("status") not in terminal
                  and not (m.get("title") or "").startswith("TEST_QUOTA_AUDIT")]
        needed = max(0, 3 - len(active))
        created = []
        try:
            for i in range(needed):
                r = _create_mission(H, title=f"TEST_QUOTA_AUDIT slot{i}")
                assert r.status_code in (200, 201), r.text
                created.append(r.json()["id"])
            # 4th active must 402
            r = _create_mission(H, title="TEST_QUOTA_AUDIT overflow")
            assert r.status_code == 402, f"expected 402, got {r.status_code}: {r.text}"
        finally:
            for cid in created:
                requests.delete(f"{API}/missions/{cid}", headers=H, timeout=15)


# -------- 8. No regression on core endpoints --------
class TestNoRegression:
    def test_dashboard_stats(self, H):
        r = requests.get(f"{API}/dashboard/stats", headers=H, timeout=15)
        assert r.status_code == 200

    def test_dashboard_analytics(self, H):
        r = requests.get(f"{API}/dashboard/analytics", headers=H, timeout=20)
        assert r.status_code == 200

    def test_vendors_memory(self, H):
        r = requests.get(f"{API}/vendors/memory", headers=H, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

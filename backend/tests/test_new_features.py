"""NegoBuy - New feature tests: system status, entitlements, outreach, vendor memory,
analytics, PDF report, voice, team invites, whatsapp."""
import os
import time
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
    assert "access_token" in data and data.get("email") == ADMIN_EMAIL
    return data["access_token"]


@pytest.fixture(scope="module")
def H(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


def _create_mission(H, title=None):
    spec = {
        "title": title or f"TEST Mission {uuid.uuid4().hex[:6]}",
        "category": "office_supplies",
        "quantity": 100,
        "budget": 200000,
        "currency": "INR",
        "delivery_location": "Bangalore",
        "deadline_days": 14,
        "description": "TEST mission",
    }
    r = requests.post(f"{API}/missions", headers=H, json=spec, timeout=30)
    return r


@pytest.fixture(scope="module")
def mission_id(H):
    # Clean up old TEST missions first to avoid quota issues
    lst = requests.get(f"{API}/missions", headers=H, timeout=15).json()
    for m in lst:
        if isinstance(m, dict) and (m.get("title") or "").startswith("TEST "):
            requests.delete(f"{API}/missions/{m['id']}", headers=H, timeout=15)
    r = _create_mission(H, title="TEST Primary Mission")
    assert r.status_code in (200, 201), r.text
    mid = r.json()["id"]
    yield mid
    requests.delete(f"{API}/missions/{mid}", headers=H, timeout=15)


@pytest.fixture(scope="module")
def vendor_id(H, mission_id):
    # Kick off discovery and poll
    r = requests.post(f"{API}/missions/{mission_id}/discover", headers=H, timeout=30)
    assert r.status_code in (200, 202)
    vendors = []
    deadline = time.time() + 60
    while time.time() < deadline:
        vr = requests.get(f"{API}/missions/{mission_id}/vendors", headers=H, timeout=15)
        if vr.status_code == 200:
            vendors = vr.json()
            if vendors:
                break
        time.sleep(4)
    if not vendors:
        # Fallback: seed a synthetic vendor directly into Mongo so the outreach/negotiation
        # suite still runs even if keyless Tavily returns 0. This is a test-only insertion.
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        async def _seed():
            c = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = c[os.environ["DB_NAME"]]
            # Look up mission for org
            m = await db.missions.find_one({"id": mission_id})
            vid = uuid.uuid4().hex
            await db.vendors.insert_one({
                "id": vid, "mission_id": mission_id,
                "organization_id": m["organization_id"],
                "name": "TEST Vendor Co.", "domain": "test-vendor.example.com",
                "url": "https://test-vendor.example.com",
                "snippet": "Test synthetic vendor for automation",
                "contact_emails": ["sales@test-vendor.example.com"],
                "contact_phones": [], "reliability_score": 70, "weighted_score": 75,
                "scores": {"category_match": 80, "geographic_suitability": 70,
                           "credibility": 70, "evidence_quality": 80},
            })
            c.close()
            return vid
        vid = asyncio.get_event_loop().run_until_complete(_seed())
        return vid
    return vendors[0]["id"]


# -------- Auth --------
class TestAuth:
    def test_admin_login(self, admin_token):
        assert admin_token and isinstance(admin_token, str)


# -------- System status --------
class TestSystemStatus:
    def test_status(self, H):
        r = requests.get(f"{API}/system/status", headers=H, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["ai"]["state"] == "CONFIGURED"
        assert d["email"]["state"] == "CONFIGURED"
        assert d["voice"]["state"] == "READY"
        assert d["telephony"]["state"] == "NOT_CONFIGURED"
        assert d["whatsapp"]["state"] == "NOT_CONFIGURED"
        assert d["payments"]["state"] == "NOT_CONFIGURED"


# -------- Entitlements (free plan, active limit 3) --------
class TestEntitlements:
    def test_free_plan_402_on_fourth_active(self, H):
        # Cleanup TEST_QUOTA missions
        lst = requests.get(f"{API}/missions", headers=H, timeout=15).json()
        for m in lst:
            if (m.get("title") or "").startswith("TEST_QUOTA"):
                requests.delete(f"{API}/missions/{m['id']}", headers=H, timeout=15)
        # Count current active
        active_terminal = ("COMPLETED", "CANCELLED", "REJECTED", "APPROVED")
        active = [m for m in lst if m["status"] not in active_terminal
                  and not (m.get("title") or "").startswith("TEST_QUOTA")]
        # Fill remaining slots up to limit=3
        created = []
        needed = max(0, 3 - len(active))
        for i in range(needed):
            r = _create_mission(H, title=f"TEST_QUOTA slot{i}")
            assert r.status_code in (200, 201), r.text
            created.append(r.json()["id"])
        # Now 4th should 402
        r = _create_mission(H, title="TEST_QUOTA overflow")
        try:
            assert r.status_code == 402, f"expected 402, got {r.status_code}: {r.text}"
            body = r.json()
            msg = str(body).lower()
            assert "plan" in msg or "upgrade" in msg or "limit" in msg
        finally:
            for cid in created:
                requests.delete(f"{API}/missions/{cid}", headers=H, timeout=15)


# -------- Discovery / Negotiation / Vendor memory --------
class TestDiscoveryNegotiation:
    def test_discovery_returns_vendors_or_no_500(self, H, mission_id):
        vr = requests.get(f"{API}/missions/{mission_id}/vendors", headers=H, timeout=15)
        assert vr.status_code == 200
        assert isinstance(vr.json(), list)

    def test_negotiate(self, H, mission_id, vendor_id):
        r = requests.post(f"{API}/missions/{mission_id}/vendors/{vendor_id}/negotiate",
                          headers=H, json={"rounds": 2}, timeout=180)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d, dict)
        assert "events" in d and len(d["events"]) > 0
        # offer usually created; not strict
        offers = requests.get(f"{API}/missions/{mission_id}/offers", headers=H, timeout=15).json()
        assert isinstance(offers, list)

    def test_vendor_memory(self, H, mission_id, vendor_id):
        # Ensure negotiation has run at least once
        r = requests.get(f"{API}/vendors/memory", headers=H, timeout=15)
        assert r.status_code == 200
        mem = r.json()
        assert isinstance(mem, list)
        assert len(mem) >= 1
        m0 = mem[0]
        assert "negotiations_count" in m0
        assert "best_price" in m0


# -------- Dashboard analytics --------
class TestAnalytics:
    def test_analytics_keys(self, H):
        r = requests.get(f"{API}/dashboard/analytics", headers=H, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ["savings_over_time", "status_breakdown", "top_vendors",
                  "total_savings", "vendors_remembered"]:
            assert k in d, f"missing {k}"


# -------- Outreach: compose / strategy / contact --------
class TestOutreachAI:
    def test_compose(self, H, mission_id, vendor_id):
        r = requests.post(f"{API}/missions/{mission_id}/vendors/{vendor_id}/outreach/compose",
                          headers=H, json={"tone": "professional"}, timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("subject") and d.get("body_text")

    def test_strategy(self, H, mission_id, vendor_id):
        r = requests.post(f"{API}/missions/{mission_id}/vendors/{vendor_id}/outreach/strategy",
                          headers=H, timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        text = str(d).lower()
        # Accept any of these keys
        assert any(k in d for k in ("subject_approach", "opening_hook", "value_props")) or \
               any(k in text for k in ("subject", "opening", "value"))

    def test_contact(self, H, mission_id, vendor_id):
        r = requests.post(f"{API}/missions/{mission_id}/vendors/{vendor_id}/outreach/contact",
                          headers=H, timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "suggested_email" in d or "recommended_subject" in d or "email" in str(d).lower()


# -------- Outreach: send / reply parse / apply offer / thread summary --------
class TestOutreachFlow:
    def test_send_records_attempt(self, H, mission_id, vendor_id):
        payload = {"to_email": "test@example.com", "subject": "TEST Outreach",
                   "body_text": "Hello, requesting a quote for 100 units."}
        r = requests.post(f"{API}/missions/{mission_id}/vendors/{vendor_id}/outreach/send",
                          headers=H, json=payload, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "result" in d and "message" in d
        # Verify attempt recorded in thread
        tr = requests.get(f"{API}/missions/{mission_id}/vendors/{vendor_id}/outreach",
                          headers=H, timeout=15).json()
        msgs = tr.get("messages", [])
        assert any(m.get("direction") == "outbound" and m.get("subject") == "TEST Outreach" for m in msgs)

    def test_reply_parse(self, H, mission_id, vendor_id):
        body = {"subject": "Re: Quote",
                "body": "We can offer INR 850 per unit, MOQ 100, lead time 14 days, Net 30, FOB."}
        r = requests.post(f"{API}/missions/{mission_id}/vendors/{vendor_id}/outreach/reply",
                          headers=H, json=body, timeout=90)
        assert r.status_code == 200, r.text
        parsed = r.json().get("parsed", {})
        assert parsed.get("price_per_unit") is not None
        # allow some flexibility (LLM)
        assert 700 <= float(parsed["price_per_unit"]) <= 1000
        assert parsed.get("lead_time_days") in (14, "14") or str(parsed.get("lead_time_days")) == "14"
        assert parsed.get("payment_terms")
        assert parsed.get("shipping_terms")

    def test_apply_offer(self, H, mission_id, vendor_id):
        r = requests.post(f"{API}/missions/{mission_id}/vendors/{vendor_id}/outreach/apply-offer",
                          headers=H, json={"price_per_unit": 850, "lead_time_days": 14}, timeout=30)
        assert r.status_code == 200, r.text
        offer = r.json()
        assert offer.get("simulation") is False
        assert offer.get("negotiated_price") == 850
        # Verify via list
        offers = requests.get(f"{API}/missions/{mission_id}/offers", headers=H, timeout=15).json()
        assert any(o["id"] == offer["id"] for o in offers)

    def test_thread_summary(self, H, mission_id, vendor_id):
        r = requests.post(f"{API}/missions/{mission_id}/vendors/{vendor_id}/outreach/summary",
                          headers=H, timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("summary")
        assert "next_action" in d
        assert "vendor_sentiment" in d


# -------- PDF report --------
class TestReport:
    def test_pdf(self, H, mission_id):
        r = requests.get(f"{API}/missions/{mission_id}/report", headers=H, timeout=30)
        assert r.status_code == 200, r.text[:200]
        assert "application/pdf" in r.headers.get("content-type", "")
        assert r.content[:4] == b"%PDF"


# -------- Voice --------
class TestVoice:
    def test_status_and_usage(self, H):
        r = requests.get(f"{API}/voice/status", headers=H, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["configured"] is True
        assert d["state"] == "READY"
        # remaining minutes should be numeric
        before = d["minutes"]["remaining"]
        assert before is not None
        r2 = requests.post(f"{API}/voice/usage", headers=H, json={"seconds": 120}, timeout=15)
        assert r2.status_code == 200
        after = r2.json()["remaining"]
        # 120 sec = 2 min consumed
        assert round(before - after, 2) == 2.0, f"before={before}, after={after}"


# -------- Team invites --------
class TestTeam:
    def test_full_invite_flow(self, H, admin_token):
        # Members
        r = requests.get(f"{API}/team/members", headers=H, timeout=15)
        assert r.status_code == 200
        members = r.json()
        assert any(m.get("email") == ADMIN_EMAIL for m in members)

        # Invite
        new_email = f"test_invitee_{uuid.uuid4().hex[:6]}@example.com"
        r = requests.post(f"{API}/team/invite", headers=H,
                          json={"email": new_email, "role": "buyer"}, timeout=20)
        assert r.status_code == 200, r.text
        inv = r.json()
        assert inv.get("accept_link") and "token=" in inv["accept_link"]
        token = inv["accept_link"].split("token=")[-1]

        # Public info
        info = requests.get(f"{API}/team/invite/{token}", timeout=15)
        assert info.status_code == 200
        d = info.json()
        assert d["email"] == new_email
        assert d["role"] == "buyer"

        # Accept
        ac = requests.post(f"{API}/team/accept",
                          json={"token": token, "name": "TEST User", "password": "test123"},
                          timeout=20)
        assert ac.status_code == 200, ac.text
        aj = ac.json()
        assert aj.get("access_token")
        new_uid = aj.get("id")
        assert new_uid

        # Admin: PATCH role
        pr = requests.patch(f"{API}/team/members/{new_uid}", headers=H,
                           json={"role": "viewer"}, timeout=15)
        assert pr.status_code == 200, pr.text

        # Admin: DELETE
        dr = requests.delete(f"{API}/team/members/{new_uid}", headers=H, timeout=15)
        assert dr.status_code in (200, 204), dr.text


# -------- WhatsApp --------
class TestWhatsApp:
    def test_status_not_configured(self, H):
        r = requests.get(f"{API}/whatsapp/status", headers=H, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["state"] == "NOT_CONFIGURED"
        assert d["configured"] is False

    def test_webhook_verify_403(self):
        r = requests.get(f"{API}/webhooks/whatsapp",
                        params={"hub.mode": "subscribe", "hub.verify_token": "wrong",
                                "hub.challenge": "x"}, timeout=15)
        assert r.status_code == 403

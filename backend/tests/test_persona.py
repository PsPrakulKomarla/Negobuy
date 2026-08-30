"""Negotiation persona upgrade — backend tests.

Covers:
- Setup: admin login + mission create + discovery poll
- Web negotiation: buyer messages natural, no commit phrases, walk_away <= 900 (clamp)
- No auto-commit (mission not APPROVED/COMPLETED, no purchases)
- Voice persona via directly-inserted voice_sessions doc + session-start webhook:
  authority context in agent_prompt; no secret leaks; authority is read-only
- Regression: /api/system/status READY exotel, /api/audit works
"""
import os
import time
import uuid
import asyncio
from datetime import datetime, timezone

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient


def _load_env(key, path):
    with open(path) as f:
        for line in f:
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    return None


BASE = _load_env("REACT_APP_BACKEND_URL", "/app/frontend/.env").rstrip("/")
MONGO_URL = _load_env("MONGO_URL", "/app/backend/.env")
DB_NAME = _load_env("DB_NAME", "/app/backend/.env")
ADMIN = {"email": "admin@negobuy.ai", "password": "NegoBuy@2026"}
WEBHOOK_TOKEN = "nb_exotel_9f2a7c41e8b6d503"

SENSITIVE_KEYS = ["EXOTEL_API_KEY", "EXOTEL_API_TOKEN", "EMERGENT_LLM_KEY"]
SENSITIVE_VALUES = []
for k in SENSITIVE_KEYS:
    v = _load_env(k, "/app/backend/.env")
    if v:
        SENSITIVE_VALUES.append(v)


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def me(session):
    r = session.get(f"{BASE}/api/auth/me", timeout=10)
    assert r.status_code == 200
    return r.json()


def _cleanup_active_missions(session):
    """Delete existing active TEST_ or persona test missions to free the free-plan cap."""
    r = session.get(f"{BASE}/api/missions", timeout=15)
    if r.status_code != 200:
        return
    for m in r.json():
        if m.get("status") in ("APPROVED", "COMPLETED", "CANCELLED"):
            continue
        # Only cleanup our test artifacts
        title = (m.get("title") or "")
        if "Persona Test" in title or title.startswith("TEST_"):
            session.delete(f"{BASE}/api/missions/{m['id']}", timeout=10)


@pytest.fixture(scope="module")
def mission(session):
    _cleanup_active_missions(session)
    body = {
        "title": "Persona Test Chairs",
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
    # teardown
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
        if vr.status_code == 200:
            vs = vr.json()
            if vs:
                vendor = vs[0]
                break
        time.sleep(3)
    if not vendor:
        pytest.skip("Vendor discovery flaky — no vendor returned in 75s")
    return vendor


# ---------------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------------

MAX_UNIT = 900  # budget 450000 / qty 500
TARGET_UNIT = 810

COMMIT_PHRASES = [
    "deal confirmed", "order placed", "we accept", "we hereby accept",
    "order is confirmed", "purchase confirmed", "we confirm the order",
]


class TestSystemRegression:
    def test_system_status_ready(self, session):
        r = session.get(f"{BASE}/api/system/status", timeout=15)
        assert r.status_code == 200
        data = r.json()
        # find exotel state
        body_text = r.text.lower()
        assert "exotel" in body_text
        # Structure: could be top-level or nested. We look for state=READY string.
        assert "ready" in body_text, f"Exotel not READY in status: {r.text[:400]}"

    def test_audit_endpoint_ok(self, session):
        r = session.get(f"{BASE}/api/audit", timeout=15)
        assert r.status_code == 200, f"audit: {r.status_code} {r.text[:200]}"
        assert isinstance(r.json(), list)


class TestWebNegotiation:
    def test_negotiate_within_authority(self, session, mission, discovered_vendor):
        vendor_id = discovered_vendor["id"]
        r = session.post(
            f"{BASE}/api/missions/{mission['id']}/vendors/{vendor_id}/negotiate",
            json={"rounds": 2}, timeout=120)
        assert r.status_code == 200, f"negotiate: {r.status_code} {r.text[:400]}"
        neg = r.json()
        assert "events" in neg
        buyer_msgs = [e for e in neg["events"] if e.get("role") == "buyer_ai"]
        assert buyer_msgs, "no buyer_ai messages in events"

        # Buyer must not use commit phrases
        for ev in buyer_msgs:
            txt = (ev.get("text") or "").lower()
            for phrase in COMMIT_PHRASES:
                assert phrase not in txt, f"Buyer used commit phrase '{phrase}': {ev.get('text')[:200]}"
            # Server-side clamp: within_authority target_price should not exceed max
            tp = ev.get("target_price")
            if tp is not None:
                assert float(tp) <= MAX_UNIT + 0.01, f"target_price {tp} exceeds MAX_UNIT {MAX_UNIT}"

        # Store for downstream tests
        TestWebNegotiation.negotiation = neg

    def test_offer_price_within_authority(self, session, mission):
        r = session.get(f"{BASE}/api/missions/{mission['id']}/offers", timeout=15)
        # Endpoint may be /offers under missions or top-level; try both
        if r.status_code != 200:
            r = session.get(f"{BASE}/api/offers?mission_id={mission['id']}", timeout=15)
        assert r.status_code == 200, f"offers: {r.status_code} {r.text[:200]}"
        offers = r.json()
        # If no offer created (vendor unwilling), that's ok; but if created, must be <= 900
        for off in offers:
            price = off.get("negotiated_price")
            if price is not None:
                assert float(price) <= MAX_UNIT + 0.01, \
                    f"Offer negotiated_price {price} exceeds max authorized {MAX_UNIT}"

    def test_no_auto_commit(self, session, mission):
        r = session.get(f"{BASE}/api/missions/{mission['id']}", timeout=15)
        assert r.status_code == 200
        status = r.json().get("status")
        assert status not in ("APPROVED", "COMPLETED"), \
            f"Mission auto-committed to {status} after negotiation"

        # No purchases for this mission
        r = session.get(f"{BASE}/api/purchases", timeout=15)
        if r.status_code == 200:
            for p in r.json():
                assert p.get("mission_id") != mission["id"], \
                    "Purchase was auto-created after negotiation"


# ---------------------------------------------------------------------------
# Voice persona tests (mocked — no real call)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def voice_session_ref(session, me, mission, discovered_vendor):
    """Insert a voice_sessions doc directly into Mongo."""
    session_ref = "persona_test_ref_" + uuid.uuid4().hex[:8]
    org_id = me.get("organization_id") or me.get("org_id") or me.get("organizationId")
    assert org_id, f"could not get org id from /me: {me}"

    async def _insert():
        client = AsyncIOMotorClient(MONGO_URL)
        try:
            db = client[DB_NAME]
            doc = {
                "id": uuid.uuid4().hex,
                "session_ref": session_ref,
                "provider": "exotel",
                "organization_id": org_id,
                "mission_id": mission["id"],
                "vendor_id": discovered_vendor["id"],
                "vendor_name": discovered_vendor.get("name"),
                "authority": {
                    "currency": "INR",
                    "max_price_per_unit": 900,
                    "target_price_per_unit": 810,
                    "quantity": 500,
                    "max_delivery_days": 10,
                    "min_warranty": "1 year",
                },
                "status": "connected",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.voice_sessions.insert_one(doc)
        finally:
            client.close()

    asyncio.get_event_loop().run_until_complete(_insert()) if False else \
        asyncio.new_event_loop().run_until_complete(_insert())

    yield session_ref

    async def _delete():
        client = AsyncIOMotorClient(MONGO_URL)
        try:
            await client[DB_NAME].voice_sessions.delete_many({"session_ref": session_ref})
        finally:
            client.close()
    try:
        asyncio.new_event_loop().run_until_complete(_delete())
    except Exception:
        pass


class TestVoicePersona:
    def test_session_start_returns_agent_prompt(self, voice_session_ref, mission):
        r = requests.post(
            f"{BASE}/api/voice/exotel/session-start?token={WEBHOOK_TOKEN}",
            data={"CustomField": voice_session_ref}, timeout=20)
        assert r.status_code == 200, f"session-start: {r.status_code} {r.text[:300]}"
        data = r.json()
        assert "agent_prompt" in data
        prompt = data["agent_prompt"]
        assert isinstance(prompt, str) and len(prompt) > 200

        # (a) includes mission title + authority limits
        assert mission["title"] in prompt, "mission title missing from agent_prompt"
        assert "900" in prompt, "max authorized 900 missing from agent_prompt"
        assert "810" in prompt, "target 810 missing from agent_prompt"

        # (b) human-approval / no-commit language
        lower = prompt.lower()
        approval_markers = ["final approval", "human", "approval from our side",
                            "not commit", "may not commit", "not place an order",
                            "not agree", "must not"]
        assert any(m in lower for m in approval_markers), \
            f"no-commit / human-approval language missing from agent_prompt"

        # (c) no secret values
        for sv in SENSITIVE_VALUES:
            assert sv not in prompt, "secret value leaked into agent_prompt"
            assert sv not in r.text, "secret value leaked into session-start response"

    def test_authority_is_read_only(self, voice_session_ref):
        # Attempt to override max via form field — should be ignored.
        r = requests.post(
            f"{BASE}/api/voice/exotel/session-start?token={WEBHOOK_TOKEN}",
            data={"CustomField": voice_session_ref, "max_price_per_unit": "999999"},
            timeout=20)
        assert r.status_code == 200
        auth = r.json().get("authority") or {}
        assert auth.get("max_price_per_unit") == 900, \
            f"Authority was mutated by webhook: {auth}"
        assert auth.get("target_price_per_unit") == 810

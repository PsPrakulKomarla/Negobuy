"""Webhook behaviour with the CORRECT token: voice-start must return read-only agent context
and status-callback must persist state without mutating authority or creating a purchase."""
import os
import re
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

BE = dotenv_values("/app/backend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE}/api"
TOKEN = BE.get("EXOTEL_WEBHOOK_TOKEN")
MISSION_ID = "b983bb2f74bd44f29685978e16251d93"
VENDOR_ID = "3a7c1a1bc7fd486599d696c7674c2177"


@pytest.fixture(scope="module")
def client():
    c = Path("/app/memory/test_credentials.md").read_text(encoding="utf-8")
    email = re.search(r'(?im)^\s*[-*]\s*Email\s*:\s*`([^`]+)`', c).group(1)
    pwd = re.search(r'(?im)^\s*[-*]\s*Password\s*:\s*`([^`]+)`', c).group(1)
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=60)
    r.raise_for_status()
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


@pytest.fixture(scope="module")
def cfg(client):
    body = {"mission_id": MISSION_ID, "vendor_id": VENDOR_ID, "to_number": "+919876500033",
            "supplier_name": "TEST_Webhook Vendor", "product": "TEST_ tiles", "quantity": 100,
            "target_price": 50, "max_authorized_price": 55, "currency": "INR",
            "test_mode": True}
    r = client.post(f"{API}/voice/console/config", json=body, timeout=60)
    assert r.status_code == 200, r.text[:300]
    return r.json()


def test_voice_start_with_token(cfg):
    if not TOKEN:
        pytest.skip("EXOTEL_WEBHOOK_TOKEN not set")
    r = requests.post(f"{API}/voice/console/voice-start?token={TOKEN}",
                      data={"CustomField": cfg["session_ref"], "CallSid": "TEST_SID_1"},
                      timeout=60)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d["session_ref"] == cfg["session_ref"]
    assert "AI procurement assistant" in d["disclosure"]
    assert d["authority"]["max_price_per_unit"] == 55
    assert d["agent_prompt"]
    assert "never exceed" in d["rules"]


def test_voice_start_unknown_session():
    if not TOKEN:
        pytest.skip("EXOTEL_WEBHOOK_TOKEN not set")
    r = requests.post(f"{API}/voice/console/voice-start?token={TOKEN}",
                      data={"CustomField": "does-not-exist"}, timeout=30)
    assert r.status_code == 404


def test_status_callback_cannot_mutate_authority(client, cfg):
    if not TOKEN:
        pytest.skip("EXOTEL_WEBHOOK_TOKEN not set")
    ref = cfg["session_ref"]
    r = requests.post(
        f"{API}/voice/console/status-callback?token={TOKEN}",
        data={"CustomField": ref, "CallStatus": "completed", "DialCallDuration": "42",
              "max_authorized_price": "99999", "authority": "hacked"}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d["status"] == "recorded"
    after = client.get(f"{API}/voice/console/session/{ref}", timeout=30).json()
    assert after["authority"]["max_price_per_unit"] == 55, after["authority"]
    assert after["duration"] == 42
    assert after["status"] == "completed"
    # no fabricated transcript / analysis
    assert not after.get("transcript")
    assert after.get("analysis") in (None, {})
    # duplicate delivery is idempotent
    r2 = requests.post(f"{API}/voice/console/status-callback?token={TOKEN}",
                       data={"CustomField": ref, "CallStatus": "completed"}, timeout=30)
    assert r2.json().get("status") == "duplicate", r2.text[:200]


def test_transcript_push_with_token(client, cfg):
    if not TOKEN:
        pytest.skip("EXOTEL_WEBHOOK_TOKEN not set")
    ref = cfg["session_ref"]
    r = requests.post(f"{API}/voice/console/transcript/{ref}?token={TOKEN}",
                      json={"speaker": "supplier", "text": "TEST_ pushed line",
                            "timestamp": "00:05", "confidence": 0.9}, timeout=30)
    assert r.status_code == 200 and r.json()["ok"] is True
    d = client.get(f"{API}/voice/console/session/{ref}", timeout=30).json()
    assert d["transcript"][-1]["speaker"] == "SUPPLIER"
    assert d["transcript"][-1]["text"] == "TEST_ pushed line"
    assert d["transcript_status"] == "AVAILABLE"
    # unknown speaker is coerced to SYSTEM
    requests.post(f"{API}/voice/console/transcript/{ref}?token={TOKEN}",
                  json={"speaker": "HACKER", "text": "TEST_ x"}, timeout=30)
    d2 = client.get(f"{API}/voice/console/session/{ref}", timeout=30).json()
    assert d2["transcript"][-1]["speaker"] == "SYSTEM"


def test_transcript_push_unknown_session():
    if not TOKEN:
        pytest.skip("EXOTEL_WEBHOOK_TOKEN not set")
    r = requests.post(f"{API}/voice/console/transcript/nope?token={TOKEN}",
                      json={"speaker": "AI", "text": "x"}, timeout=30)
    assert r.status_code == 404

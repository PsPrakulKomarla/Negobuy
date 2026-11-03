"""Fallback eligibility: a provider-confirmed no-answer/failed call IS fallback-eligible."""
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

frontend_env = dotenv_values("/app/frontend/.env")
backend_env = dotenv_values("/app/backend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or frontend_env.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"


def _creds():
    c = Path("/app/memory/test_credentials.md").read_text(encoding="utf-8")
    return {"email": re.search(r'(?im)^\s*[-*]\s*Email\s*:\s*`?([^`\s]+)', c).group(1),
            "password": re.search(r'(?im)^\s*[-*]\s*Password\s*:\s*`?([^`\s]+)', c).group(1)}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json=_creds(), timeout=60)
    if r.status_code != 200:
        pytest.fail(f"login failed: {r.status_code}")
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


@pytest.fixture(scope="module")
def db():
    return MongoClient(backend_env["MONGO_URL"])[backend_env["DB_NAME"]]


def test_no_answer_call_is_fallback_eligible(client, db):
    p = client.post(f"{API}/direct-negotiation/prepare", json={
        "business_name": "TEST_NoAnswer Traders", "phone_number": "9876500033",
        "what_to_buy": "200 units of PVC pipes 4 inch", "product": "PVC pipes 4 inch",
        "quantity": 200, "target_price": 300.0, "max_authorized_price": 330.0,
        "currency": "INR", "delivery_location": "Nashik", "delivery_deadline_days": 7,
        "other_instructions": "TEST_ QA"}, timeout=180)
    assert p.status_code == 200, p.text[:300]
    mid = p.json()["mission_id"]

    ref = uuid.uuid4().hex
    db.voice_calls.insert_one({
        "id": uuid.uuid4().hex, "session_ref": ref, "organization_id": p.json()["mission"]["organization_id"],
        "mission_id": mid, "vendor_id": p.json()["vendor_id"], "status": "no-answer",
        "approved": True, "transcript": [],
        "created_at": datetime.now(timezone.utc).isoformat()})
    try:
        r = client.post(f"{API}/direct-negotiation/{mid}/fallback",
                        json={"call_ref": ref, "simulate": True}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["delivery"]["state"] == "SIMULATED"
    finally:
        db.voice_calls.delete_one({"session_ref": ref})

"""Communication Hub (multi-channel AI messaging negotiation) tests."""
import os
import re
import time
import uuid
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
WEBHOOK_SECRET = backend_env.get("TELEGRAM_WEBHOOK_SECRET")
MISSION_ID = "4502b5e0ebe84e909b72eca85927dc4c"
VENDOR_ID = "27e789fa0784487697f81f7f3af6ec42"
ENGINE_TIMEOUT = 180


def _creds():
    content = Path("/app/memory/test_credentials.md").read_text(encoding="utf-8")
    email = re.search(r'(?im)^\s*[-*]?\s*(?:\*\*)?Email(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    pwd = re.search(r'(?im)^\s*[-*]?\s*(?:\*\*)?Password(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    if not email or not pwd:
        pytest.skip("credentials missing")
    return email.group(1), pwd.group(1)


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    email, pwd = _creds()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    token = r.json().get("access_token") or r.json().get("token")
    assert token
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="session")
def db():
    mc = MongoClient(backend_env["MONGO_URL"])
    return mc[backend_env["DB_NAME"]]


def _tg_update(chat_id, text, update_id=None):
    return {"update_id": update_id or int(time.time() * 1000) % 10**9,
            "message": {"message_id": 1, "from": {"id": 42, "is_bot": False,
                                                  "first_name": "TEST_Supplier"},
                        "chat": {"id": chat_id}, "text": text}}


# --- Provider status ------------------------------------------------------- #
class TestStatus:
    def test_status_all_not_configured(self, client):
        r = client.get(f"{API}/communication/status", timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        chans = {p["channel"]: p["state"] for p in data["providers"]}
        assert chans == {"telegram": "NOT_CONFIGURED", "whatsapp": "NOT_CONFIGURED",
                         "instagram": "NOT_CONFIGURED"}, chans
        body = r.text.lower()
        for leak in ["token", "gsk_", "secret", "api_key"]:
            assert leak not in body, f"possible secret leak: {leak}"

    def test_status_requires_auth(self):
        r = requests.get(f"{API}/communication/status", timeout=60)
        assert r.status_code in (401, 403), r.status_code


# --- Start negotiation ---------------------------------------------------- #
class TestStart:
    def test_start_telegram_not_configured(self, client, db):
        recipient = f"555777{uuid.uuid4().hex[:4]}"
        r = client.post(f"{API}/communication/negotiations/start",
                        json={"mission_id": MISSION_ID, "vendor_id": VENDOR_ID,
                              "channel": "telegram", "recipient": recipient},
                        timeout=ENGINE_TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["provider_state"] == "NOT_CONFIGURED"
        assert d["delivery"]["status"] == "NOT_CONFIGURED"
        assert d["delivery"]["ok"] is False
        assert d["outreach"] and len(d["outreach"]) > 10
        conv_id = d["conversation_id"]
        detail = client.get(f"{API}/communication/negotiations/{conv_id}", timeout=60)
        assert detail.status_code == 200
        msgs = detail.json()["messages"]
        assert any(m["direction"] == "OUTBOUND" and m["delivery_status"] == "NOT_CONFIGURED"
                   for m in msgs), msgs

    def test_start_bogus_mission_404(self, client):
        r = client.post(f"{API}/communication/negotiations/start",
                        json={"mission_id": "nope" + uuid.uuid4().hex, "vendor_id": VENDOR_ID,
                              "channel": "telegram", "recipient": "555999"}, timeout=90)
        assert r.status_code == 404, r.text

    def test_start_empty_recipient_400(self, client):
        r = client.post(f"{API}/communication/negotiations/start",
                        json={"mission_id": MISSION_ID, "vendor_id": VENDOR_ID,
                              "channel": "telegram", "recipient": "   "}, timeout=90)
        assert r.status_code == 400, r.text

    def test_start_unsupported_channel_400(self, client):
        r = client.post(f"{API}/communication/negotiations/start",
                        json={"mission_id": MISSION_ID, "vendor_id": VENDOR_ID,
                              "channel": "signal", "recipient": "555999"}, timeout=90)
        assert r.status_code == 400, r.text


# --- Inbound webhook ------------------------------------------------------ #
class TestWebhook:
    def test_wrong_secret_401(self):
        r = requests.post(f"{API}/communication/telegram/webhook",
                          json=_tg_update("999", "hi"),
                          headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"}, timeout=60)
        assert r.status_code == 401, r.text

    def test_bot_message_ignored(self):
        upd = _tg_update("999", "hi")
        upd["message"]["from"]["is_bot"] = True
        r = requests.post(f"{API}/communication/telegram/webhook", json=upd,
                          headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET}, timeout=60)
        assert r.status_code == 200 and r.json()["status"] == "ignored", r.text

    def test_non_text_update_ignored(self):
        upd = {"update_id": 1234567, "message": {"message_id": 2, "from": {"id": 1, "is_bot": False},
                                                "chat": {"id": "999"},
                                                "photo": [{"file_id": "x"}]}}
        r = requests.post(f"{API}/communication/telegram/webhook", json=upd,
                          headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET}, timeout=60)
        assert r.status_code == 200 and r.json()["status"] == "ignored", r.text

    def test_unknown_chat_no_conversation(self, db):
        chat = f"unknown{uuid.uuid4().hex[:8]}"
        before = db.messages.count_documents({})
        r = requests.post(f"{API}/communication/telegram/webhook",
                          json=_tg_update(chat, "quote please"),
                          headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET}, timeout=60)
        assert r.status_code == 200 and r.json()["status"] == "no_conversation", r.text
        assert db.messages.count_documents({}) == before

    def test_inbound_runs_shared_engine_and_idempotency(self, client, db):
        recipient = f"tg{uuid.uuid4().hex[:8]}"
        start = client.post(f"{API}/communication/negotiations/start",
                            json={"mission_id": MISSION_ID, "vendor_id": VENDOR_ID,
                                  "channel": "telegram", "recipient": recipient},
                            timeout=ENGINE_TIMEOUT)
        assert start.status_code == 200, start.text
        conv_id = start.json()["conversation_id"]

        upd = _tg_update(recipient,
                         "We can do 780 per unit for the full quantity, 10 days delivery",
                         update_id=int(uuid.uuid4().int % 10**9))
        orders_before = sum(db[c].count_documents({}) for c in ("orders", "purchases",
                                                               "purchase_orders"))
        r = requests.post(f"{API}/communication/telegram/webhook", json=upd,
                          headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET},
                          timeout=ENGINE_TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "handled", d
        assert d["comm_state"] in ("NEGOTIATING", "BUYER_APPROVAL_REQUIRED",
                                  "REQUIREMENTS_DISCUSSION"), d

        detail = client.get(f"{API}/communication/negotiations/{conv_id}", timeout=60).json()
        msgs = detail["messages"]
        assert any(m["direction"] == "INBOUND" for m in msgs)
        assert len([m for m in msgs if m["direction"] == "OUTBOUND"]) >= 2, msgs
        assert detail["latest_quote"] in (780, 780.0), detail["latest_quote"]
        assert detail["stage"] == d["comm_state"]

        # no purchase created
        orders_after = sum(db[c].count_documents({}) for c in ("orders", "purchases",
                                                               "purchase_orders"))
        assert orders_after == orders_before, "communication endpoint created a purchase/order"

        # idempotency: same update_id again
        n_before = len(msgs)
        r2 = requests.post(f"{API}/communication/telegram/webhook", json=upd,
                           headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET},
                           timeout=ENGINE_TIMEOUT)
        assert r2.status_code == 200 and r2.json()["status"] == "duplicate", r2.text
        msgs2 = client.get(f"{API}/communication/negotiations/{conv_id}",
                           timeout=60).json()["messages"]
        assert len(msgs2) == n_before, "duplicate webhook created extra messages"


# --- Authority safety ----------------------------------------------------- #
class TestAuthority:
    def test_above_max_quote_requires_buyer_approval(self, client, db):
        recipient = f"tgmax{uuid.uuid4().hex[:8]}"
        start = client.post(f"{API}/communication/negotiations/start",
                            json={"mission_id": MISSION_ID, "vendor_id": VENDOR_ID,
                                  "channel": "telegram", "recipient": recipient},
                            timeout=ENGINE_TIMEOUT)
        assert start.status_code == 200, start.text
        conv_id = start.json()["conversation_id"]
        r = requests.post(
            f"{API}/communication/telegram/webhook",
            json=_tg_update(recipient,
                            "Our final price is 1500 per unit, we cannot go lower at all.",
                            update_id=int(uuid.uuid4().int % 10**9)),
            headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET}, timeout=ENGINE_TIMEOUT)
        assert r.status_code == 200, r.text
        detail = client.get(f"{API}/communication/negotiations/{conv_id}", timeout=60).json()
        assert detail["latest_quote"] and float(detail["latest_quote"]) > float(
            detail["max_authority"]), detail
        assert detail["stage"] == "BUYER_APPROVAL_REQUIRED", detail["stage"]
        assert detail["within_authority"] is False, detail
        assert detail["approval_required"] is True
        reply = [m for m in detail["messages"] if m["direction"] == "OUTBOUND"][-1]["content"]
        assert "1500" not in reply or "accept" not in reply.lower(), reply
        return conv_id

    def test_approve_accept_records_decision_no_purchase(self, client, db):
        conv_id = self.test_above_max_quote_requires_buyer_approval(client, db)
        before = sum(db[c].count_documents({}) for c in ("orders", "purchases",
                                                        "purchase_orders"))
        r = client.post(f"{API}/communication/negotiations/{conv_id}/approve",
                        json={"action": "ACCEPT", "note": "TEST_ok"}, timeout=90)
        assert r.status_code == 200, r.text
        assert r.json()["comm_state"] == "APPROVED"
        conv = db.conversations.find_one({"id": conv_id})
        assert conv["comm_state"] == "APPROVED"
        assert conv["human_decision"]["action"] == "ACCEPT"
        after = sum(db[c].count_documents({}) for c in ("orders", "purchases", "purchase_orders"))
        assert after == before, "ACCEPT created a purchase"

    @pytest.mark.parametrize("action,state", [("REJECT", "REJECTED"), ("COUNTER", "NEGOTIATING"),
                                             ("CLARIFY", "REQUIREMENTS_DISCUSSION")])
    def test_other_actions(self, client, action, state):
        convs = client.get(f"{API}/communication/negotiations", timeout=60).json()
        conv_id = convs[0]["id"]
        r = client.post(f"{API}/communication/negotiations/{conv_id}/approve",
                        json={"action": action}, timeout=90)
        assert r.status_code == 200, r.text
        assert r.json()["comm_state"] == state

    def test_invalid_action_400(self, client):
        convs = client.get(f"{API}/communication/negotiations", timeout=60).json()
        r = client.post(f"{API}/communication/negotiations/{convs[0]['id']}/approve",
                        json={"action": "BUY_NOW"}, timeout=60)
        assert r.status_code == 400, r.text


# --- Reads / isolation ---------------------------------------------------- #
class TestReads:
    def test_list_conversations(self, client):
        r = client.get(f"{API}/communication/negotiations", timeout=60)
        assert r.status_code == 200
        convs = r.json()
        assert isinstance(convs, list) and convs
        for c in convs:
            assert "_id" not in c
            assert {"id", "channel", "comm_state", "recipient"} <= set(c)

    def test_detail_fields(self, client):
        convs = client.get(f"{API}/communication/negotiations", timeout=60).json()
        d = client.get(f"{API}/communication/negotiations/{convs[0]['id']}", timeout=60).json()
        for k in ("stage", "target_price", "latest_quote", "max_authority", "savings_gap",
                  "approval_required", "messages"):
            assert k in d, k

    def test_detail_unknown_id_404(self, client):
        r = client.get(f"{API}/communication/negotiations/{uuid.uuid4().hex}", timeout=60)
        assert r.status_code == 404

    def test_org_isolation(self, client):
        """A user from another org must not read admin-org conversations."""
        convs = client.get(f"{API}/communication/negotiations", timeout=60).json()
        conv_id = convs[0]["id"]
        s = requests.Session()
        email = f"TEST_other_{uuid.uuid4().hex[:6]}@example.com"
        reg = s.post(f"{API}/auth/register", json={
            "email": email, "password": "Test@12345", "name": "TEST Other",
            "organization_name": f"TEST_Org_{uuid.uuid4().hex[:6]}"}, timeout=60)
        if reg.status_code not in (200, 201):
            pytest.skip(f"register unavailable: {reg.status_code} {reg.text[:200]}")
        tok = reg.json().get("access_token") or reg.json().get("token")
        s.headers.update({"Authorization": f"Bearer {tok}"})
        r = s.get(f"{API}/communication/negotiations/{conv_id}", timeout=60)
        assert r.status_code == 404, r.status_code
        r2 = s.post(f"{API}/communication/negotiations/{conv_id}/approve",
                    json={"action": "ACCEPT"}, timeout=60)
        assert r2.status_code == 404, r2.status_code
        r3 = s.post(f"{API}/communication/negotiations/start",
                    json={"mission_id": MISSION_ID, "vendor_id": VENDOR_ID,
                          "channel": "telegram", "recipient": "555000"}, timeout=90)
        assert r3.status_code == 404, r3.status_code


# --- Regression ----------------------------------------------------------- #
class TestRegression:
    def test_direct_negotiation_prepare(self, client):
        body = {
            "business_name": "TEST_Comm Regression Tiles", "contact_name": "Rakesh Sharma",
            "phone_number": "9876500022", "business_description": "Local tiles distributor",
            "what_to_buy": "500 boxes of 600x600 vitrified floor tiles, glossy white",
            "product": "Vitrified floor tiles 600x600 glossy white", "quantity": 500,
            "target_price": 420.0, "max_authorized_price": 450.0, "currency": "INR",
            "delivery_location": "Pune, Maharashtra", "delivery_deadline_days": 10,
            "warranty_requirements": "1 year replacement",
            "other_instructions": "TEST_ automated QA run. Do not commit any purchase.",
        }
        r = client.post(f"{API}/direct-negotiation/prepare", json=body, timeout=ENGINE_TIMEOUT)
        assert r.status_code == 200, r.text[:400]
        assert r.json()

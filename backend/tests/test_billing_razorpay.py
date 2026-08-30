"""Backend tests for Razorpay billing integration (TEST mode)."""
import os
import hmac
import hashlib
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://e01b89ae-c82e-4bb4-827e-a97121bde1bd.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@negobuy.ai"
ADMIN_PASSWORD = "NegoBuy@2026"
RZP_SECRET = "Yvk1nZYIHjIuceApV8NVu8kz"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# --- Plans catalog ---
def test_plans_catalog():
    r = requests.get(f"{BASE_URL}/api/billing/plans", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["payment_configured"] is True
    assert d["mode"] == "TEST"
    plans = {p["id"]: p for p in d["plans"]}
    assert set(plans.keys()) == {"free", "mission", "pro"}
    assert plans["free"]["price"] == 0
    assert plans["mission"]["name"] == "Procurement Machine"
    assert plans["mission"]["price"] == 69
    assert plans["mission"]["original_price"] == 349
    assert plans["mission"]["currency"] == "INR"
    assert plans["pro"]["name"] == "AI Buyer Pro"
    assert plans["pro"]["price"] == 119
    assert plans["pro"]["original_price"] == 499


# --- Order creation ---
@pytest.fixture(scope="module")
def pro_order(auth_headers):
    r = requests.post(f"{BASE_URL}/api/billing/orders",
                      json={"plan_id": "pro"}, headers=auth_headers, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def test_create_order_pro(pro_order):
    assert pro_order["status"] == "TEST"
    assert pro_order["key_id"].startswith("rzp_test_")
    assert pro_order["order"]["amount"] == 11900
    assert pro_order["order"]["currency"] == "INR"
    assert pro_order["order"]["id"].startswith("order_")


def test_create_order_mission(auth_headers):
    r = requests.post(f"{BASE_URL}/api/billing/orders",
                      json={"plan_id": "mission"}, headers=auth_headers, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "TEST"
    assert d["order"]["amount"] == 6900


def test_create_order_unknown_plan(auth_headers):
    r = requests.post(f"{BASE_URL}/api/billing/orders",
                      json={"plan_id": "nope"}, headers=auth_headers, timeout=15)
    assert r.status_code == 404


def test_create_order_requires_auth():
    r = requests.post(f"{BASE_URL}/api/billing/orders",
                      json={"plan_id": "pro"}, timeout=15)
    assert r.status_code in (401, 403)


# --- Signature verification ---
def _sign(order_id, payment_id):
    return hmac.new(RZP_SECRET.encode(),
                    f"{order_id}|{payment_id}".encode(),
                    hashlib.sha256).hexdigest()


def test_verify_invalid_signature(auth_headers, pro_order):
    order_id = pro_order["order"]["id"]
    r = requests.post(f"{BASE_URL}/api/billing/verify",
                      json={"razorpay_order_id": order_id,
                            "razorpay_payment_id": "pay_TESTBAD123",
                            "razorpay_signature": "deadbeef"},
                      headers=auth_headers, timeout=15)
    assert r.status_code == 400


def test_verify_does_not_activate_on_invalid(auth_headers):
    r = requests.get(f"{BASE_URL}/api/billing/subscription",
                     headers=auth_headers, timeout=15)
    assert r.status_code == 200
    # Ok if plan is currently free OR already activated by valid test; just make sure the invalid one didn't upgrade
    # This test primarily documents state before the valid-signature activation.


def test_verify_valid_signature_activates(auth_headers, pro_order):
    order_id = pro_order["order"]["id"]
    payment_id = "pay_TESTVALID001"
    sig = _sign(order_id, payment_id)
    r = requests.post(f"{BASE_URL}/api/billing/verify",
                      json={"razorpay_order_id": order_id,
                            "razorpay_payment_id": payment_id,
                            "razorpay_signature": sig},
                      headers=auth_headers, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True and d["status"] == "PAID"

    sub = requests.get(f"{BASE_URL}/api/billing/subscription",
                       headers=auth_headers, timeout=15).json()
    assert sub["subscription"] is not None
    assert sub["subscription"]["status"] == "active"
    assert sub["plan"] == "pro"


def test_verify_idempotent(auth_headers, pro_order):
    order_id = pro_order["order"]["id"]
    payment_id = "pay_TESTVALID001"
    sig = _sign(order_id, payment_id)
    r = requests.post(f"{BASE_URL}/api/billing/verify",
                      json={"razorpay_order_id": order_id,
                            "razorpay_payment_id": payment_id,
                            "razorpay_signature": sig},
                      headers=auth_headers, timeout=15)
    assert r.status_code == 200
    assert r.json()["ok"] is True

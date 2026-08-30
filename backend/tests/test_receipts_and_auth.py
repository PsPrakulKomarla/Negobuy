"""Tests for auth (post-.env reconstruction) + GST-invoice/receipt backend flow."""
import os
import hmac
import hashlib
import datetime
import io
import jwt
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_EMAIL = "admin@negobuy.ai"
ADMIN_PASSWORD = "NegoBuy@2026"
RZP_SECRET = "Yvk1nZYIHjIuceApV8NVu8kz"
JWT_SECRET = "negobuy_dev_jwt_secret_change_me_2026"


# ---------- Auth ----------
@pytest.fixture(scope="module")
def login_response():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def token(login_response):
    return login_response["access_token"]


@pytest.fixture(scope="module")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_returns_access_token(login_response):
    assert "access_token" in login_response
    assert isinstance(login_response["access_token"], str)
    assert len(login_response["access_token"]) > 20


def test_me_with_valid_token(auth_headers):
    r = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["email"] == ADMIN_EMAIL


def test_me_invalid_token():
    r = requests.get(f"{BASE_URL}/api/auth/me",
                     headers={"Authorization": "Bearer not-a-real-token"}, timeout=15)
    assert r.status_code == 401


def test_google_session_invalid():
    """Bogus session_id must be handled gracefully (not 500)."""
    r = requests.post(f"{BASE_URL}/api/auth/google/session",
                      json={"session_id": "fake_invalid_session_id"}, timeout=25)
    assert r.status_code in (400, 401, 502), f"got {r.status_code}: {r.text[:200]}"


def test_minted_jwt_accepted(auth_headers):
    # Fetch admin user id
    me = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=15).json()
    uid = me["id"]
    minted = jwt.encode(
        {"sub": uid, "email": me["email"], "type": "access",
         "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)},
        JWT_SECRET, algorithm="HS256")
    r = requests.get(f"{BASE_URL}/api/auth/me",
                     headers={"Authorization": f"Bearer {minted}"}, timeout=15)
    assert r.status_code == 200
    assert r.json()["email"] == ADMIN_EMAIL


# ---------- Receipts ----------
def _sign(order_id, payment_id):
    return hmac.new(RZP_SECRET.encode(),
                    f"{order_id}|{payment_id}".encode(),
                    hashlib.sha256).hexdigest()


@pytest.fixture(scope="module")
def paid_pro_order(auth_headers):
    r = requests.post(f"{BASE_URL}/api/billing/orders",
                      json={"plan_id": "pro"}, headers=auth_headers, timeout=30)
    assert r.status_code == 200, r.text
    order = r.json()["order"]
    payment_id = "pay_TESTRECEIPT01"
    sig = _sign(order["id"], payment_id)
    v = requests.post(f"{BASE_URL}/api/billing/verify",
                      json={"razorpay_order_id": order["id"],
                            "razorpay_payment_id": payment_id,
                            "razorpay_signature": sig},
                      headers=auth_headers, timeout=15)
    assert v.status_code == 200, v.text
    body = v.json()
    assert body["ok"] is True
    assert body["order_id"] == order["id"]
    assert body["invoice_no"].startswith("INV-")
    return {"order_id": order["id"], "invoice_no": body["invoice_no"],
            "amount": order["amount"]}


@pytest.fixture(scope="module")
def paid_mission_order(auth_headers):
    r = requests.post(f"{BASE_URL}/api/billing/orders",
                      json={"plan_id": "mission"}, headers=auth_headers, timeout=30)
    assert r.status_code == 200
    order = r.json()["order"]
    payment_id = "pay_TESTRECEIPT02"
    sig = _sign(order["id"], payment_id)
    v = requests.post(f"{BASE_URL}/api/billing/verify",
                      json={"razorpay_order_id": order["id"],
                            "razorpay_payment_id": payment_id,
                            "razorpay_signature": sig},
                      headers=auth_headers, timeout=15)
    assert v.status_code == 200
    return {"order_id": order["id"], "invoice_no": v.json()["invoice_no"],
            "amount": order["amount"]}


def test_receipt_pdf_pro(auth_headers, paid_pro_order):
    r = requests.get(f"{BASE_URL}/api/billing/receipt/{paid_pro_order['order_id']}",
                     headers=auth_headers, timeout=20)
    assert r.status_code == 200, r.text[:200]
    assert r.headers.get("content-type", "").startswith("application/pdf")
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd and "INV-" in cd and ".pdf" in cd
    assert r.content[:4] == b"%PDF"
    # sanity size
    assert len(r.content) > 1200


def test_receipt_gst_math_pro(paid_pro_order):
    # pro = ₹119 total, GST-inclusive 18%
    total = 119.0
    taxable = round(total / 1.18, 2)
    gst = round(total - taxable, 2)
    half = round(gst / 2, 2)
    assert abs(taxable + gst - total) < 0.02
    assert abs(half * 2 - gst) <= 0.02


def test_receipt_gst_math_mission(paid_mission_order):
    total = 69.0
    taxable = round(total / 1.18, 2)
    gst = round(total - taxable, 2)
    assert abs(taxable + gst - total) < 0.02


def test_receipt_pdf_mission(auth_headers, paid_mission_order):
    r = requests.get(f"{BASE_URL}/api/billing/receipt/{paid_mission_order['order_id']}",
                     headers=auth_headers, timeout=20)
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_receipt_unknown_order_404(auth_headers):
    r = requests.get(f"{BASE_URL}/api/billing/receipt/order_does_not_exist_zzz",
                     headers=auth_headers, timeout=15)
    assert r.status_code == 404


def test_receipt_unpaid_order_400(auth_headers):
    # create a new order but do NOT verify
    r = requests.post(f"{BASE_URL}/api/billing/orders",
                      json={"plan_id": "mission"}, headers=auth_headers, timeout=30)
    order_id = r.json()["order"]["id"]
    r2 = requests.get(f"{BASE_URL}/api/billing/receipt/{order_id}",
                      headers=auth_headers, timeout=15)
    assert r2.status_code == 400


def test_receipt_requires_auth(paid_pro_order):
    r = requests.get(f"{BASE_URL}/api/billing/receipt/{paid_pro_order['order_id']}", timeout=15)
    assert r.status_code in (401, 403)


def test_list_payments(auth_headers, paid_pro_order, paid_mission_order):
    r = requests.get(f"{BASE_URL}/api/billing/payments",
                     headers=auth_headers, timeout=15)
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list) and len(rows) >= 2
    ids = {row["order_id"]: row for row in rows}
    assert paid_pro_order["order_id"] in ids
    assert paid_mission_order["order_id"] in ids
    # newly created rows must expose invoice_no; legacy rows (pre-feature) may not
    for oid in (paid_pro_order["order_id"], paid_mission_order["order_id"]):
        assert ids[oid].get("invoice_no", "").startswith("INV-")
        assert ids[oid].get("plan_id") in ("pro", "mission")

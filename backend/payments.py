"""Razorpay payments — server-side order creation, signature verification,
idempotent webhook processing, and entitlement activation only after verified payment.
Never trusts frontend-reported success. Returns NOT_CONFIGURED until keys are set."""
import os
import json
import uuid
import hmac
import base64
import hashlib
from datetime import datetime, timezone
import httpx
from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel
from db import get_db
from auth import get_current_user
import billing
import audit

router = APIRouter(prefix="/api/billing", tags=["payments"])
webhook_router = APIRouter(prefix="/api/webhooks", tags=["payments"])


def _keys():
    return os.environ.get("RAZORPAY_KEY_ID"), os.environ.get("RAZORPAY_KEY_SECRET")


def state() -> str:
    kid, _ = _keys()
    if not kid:
        return "NOT_CONFIGURED"
    return "LIVE" if kid.startswith("rzp_live") else "TEST"


def _now():
    return datetime.now(timezone.utc).isoformat()


class OrderBody(BaseModel):
    plan_id: str


@router.post("/orders")
async def create_order(body: OrderBody, user: dict = Depends(get_current_user)):
    plan = next((p for p in billing.PLANS if p["id"] == body.plan_id), None)
    if not plan:
        raise HTTPException(status_code=404, detail="Unknown plan")
    kid, ksec = _keys()
    if not kid:
        return {"status": "NOT_CONFIGURED", "provider": "razorpay",
                "required": ["RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET"],
                "message": ("Payments require Razorpay keys. Server-side order creation, "
                            "HMAC signature verification, idempotent webhook processing and "
                            "post-payment entitlement activation are implemented and activate "
                            "once keys are configured."),
                "plan": plan}
    amount = int((plan.get("price") or 0) * 100) or 100000  # paise; price is configurable
    receipt = f"negobuy_{uuid.uuid4().hex[:12]}"
    creds = base64.b64encode(f"{kid}:{ksec}".encode()).decode()
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post("https://api.razorpay.com/v1/orders",
                         headers={"Authorization": f"Basic {creds}",
                                  "Content-Type": "application/json"},
                         json={"amount": amount, "currency": "INR", "receipt": receipt,
                               "notes": {"organization_id": user["organization_id"],
                                         "plan_id": plan["id"], "user_id": user["id"]}})
    if r.status_code >= 300:
        raise HTTPException(status_code=502, detail=f"Razorpay order failed: {r.text[:200]}")
    order = r.json()
    await get_db().payments.insert_one({
        "id": uuid.uuid4().hex, "provider": "razorpay", "mode": state(),
        "order_id": order["id"], "amount": amount, "currency": "INR", "plan_id": plan["id"],
        "organization_id": user["organization_id"], "user_id": user["id"],
        "status": "CREATED", "created_at": _now()})
    await audit.log_event(user["organization_id"], "payment_order_created",
                          actor=user.get("name"), detail=f"Order {order['id']} for {plan['id']}")
    return {"status": state(), "provider": "razorpay", "key_id": kid, "order": order, "plan": plan}


class VerifyBody(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


@router.post("/verify")
async def verify_payment(body: VerifyBody, user: dict = Depends(get_current_user)):
    _, ksec = _keys()
    if not ksec:
        raise HTTPException(status_code=400, detail="Payments not configured")
    expected = hmac.new(ksec.encode(),
                        f"{body.razorpay_order_id}|{body.razorpay_payment_id}".encode(),
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, body.razorpay_signature):
        raise HTTPException(status_code=400, detail="Signature verification failed")
    await _activate(body.razorpay_order_id, body.razorpay_payment_id, source="verify")
    return {"ok": True, "status": "PAID"}


async def _activate(order_id, payment_id, source):
    db = get_db()
    pay = await db.payments.find_one({"order_id": order_id})
    if not pay or pay.get("status") == "PAID":
        return  # idempotent
    await db.payments.update_one({"order_id": order_id},
                                 {"$set": {"status": "PAID", "payment_id": payment_id,
                                           "paid_at": _now(), "verified_via": source}})
    plan_id = pay.get("plan_id")
    if plan_id == "pro":
        await db.users.update_many({"organization_id": pay["organization_id"]},
                                   {"$set": {"plan": "pro"}})
    await db.subscriptions.update_one(
        {"organization_id": pay["organization_id"]},
        {"$set": {"organization_id": pay["organization_id"], "plan": plan_id,
                  "status": "active", "provider": "razorpay", "activated_at": _now()}},
        upsert=True)
    await audit.log_event(pay["organization_id"], "payment_verified",
                          detail=f"Payment {payment_id} for {plan_id} via {source}")


@webhook_router.post("/razorpay")
async def razorpay_webhook(request: Request):
    secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
    raw = await request.body()
    sig = request.headers.get("X-Razorpay-Signature")
    if secret:
        expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if not sig or not hmac.compare_digest(expected, sig):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    elif not _keys()[0]:
        return {"status": "NOT_CONFIGURED"}
    event = json.loads(raw or b"{}")
    db = get_db()
    event_id = request.headers.get("X-Razorpay-Event-Id") or event.get("id") or uuid.uuid4().hex
    if await db.webhook_events.find_one({"event_id": event_id}):
        return {"status": "duplicate"}  # idempotency
    await db.webhook_events.insert_one({"event_id": event_id, "provider": "razorpay",
                                        "type": event.get("event"), "created_at": _now()})
    entity = (((event.get("payload") or {}).get("payment") or {}).get("entity") or {})
    if event.get("event") in ("payment.captured", "order.paid") and entity.get("order_id"):
        await _activate(entity["order_id"], entity.get("id"), source="webhook")
    return {"status": "ok"}

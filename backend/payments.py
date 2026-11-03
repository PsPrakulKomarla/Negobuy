"""Razorpay payments — server-side order creation, signature verification,
idempotent webhook processing, and entitlement activation only after verified payment.
Never trusts frontend-reported success. Returns NOT_CONFIGURED until keys are set."""
import os
import io
import json
import uuid
import hmac
import base64
import hashlib
from datetime import datetime, timezone
import httpx
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse
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


def _invoice_no(order_id: str) -> str:
    return f"INV-{datetime.now(timezone.utc).strftime('%Y%m')}-{order_id[-6:].upper()}"


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
    return {"ok": True, "status": "PAID", "order_id": body.razorpay_order_id,
            "invoice_no": _invoice_no(body.razorpay_order_id)}


async def _activate(order_id, payment_id, source):
    db = get_db()
    pay = await db.payments.find_one({"order_id": order_id})
    if not pay or pay.get("status") == "PAID":
        return  # idempotent
    inv_no = pay.get("invoice_no") or _invoice_no(order_id)
    await db.payments.update_one({"order_id": order_id},
                                 {"$set": {"status": "PAID", "payment_id": payment_id,
                                           "paid_at": _now(), "verified_via": source,
                                           "invoice_no": inv_no}})
    plan_id = pay.get("plan_id")
    if plan_id in ("pro", "mission"):
        await db.users.update_many({"organization_id": pay["organization_id"]},
                                   {"$set": {"plan": plan_id}})
    await db.subscriptions.update_one(
        {"organization_id": pay["organization_id"]},
        {"$set": {"organization_id": pay["organization_id"], "plan": plan_id,
                  "status": "active", "provider": "razorpay", "activated_at": _now()}},
        upsert=True)
    await audit.log_event(pay["organization_id"], "payment_verified",
                          detail=f"Payment {payment_id} for {plan_id} via {source}")


# --------------------------------------------------------------------------- #
# GST-style invoice / receipt (downloadable PDF)
# --------------------------------------------------------------------------- #
SELLER = {
    "name": "NegoBuy Technologies Pvt. Ltd.",
    "address": "3rd Floor, WeWork Prestige Central, Bengaluru, Karnataka 560001",
    "gstin": "29ABCDE1234F1Z5",
    "sac": "998314",
    "state": "Karnataka",
    "email": "billing@negobuy.ai",
}
GST_RATE = 0.18  # 18% (CGST 9% + SGST 9%), prices are GST-inclusive


def _gst_breakup(total_paise: int):
    total = round(total_paise / 100, 2)
    taxable = round(total / (1 + GST_RATE), 2)
    gst = round(total - taxable, 2)
    half = round(gst / 2, 2)
    return {"total": total, "taxable": taxable, "gst": gst,
            "cgst": half, "sgst": round(gst - half, 2)}


def _build_invoice_pdf(pay: dict, plan: dict, user: dict, inv_no: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    m = 18 * mm
    y = h - m
    g = _gst_breakup(int(pay.get("amount") or 0))

    def line(txt, size=10, dy=6, bold=False, x=m, color=(0.1, 0.1, 0.1)):
        nonlocal y
        c.setFillColorRGB(*color)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(x, y, txt)
        y -= (size + dy)

    # Header
    c.setFillColorRGB(0.06, 0.62, 0.42)
    c.rect(0, h - 14 * mm, w, 14 * mm, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(m, h - 9.5 * mm, "NegoBuy")
    c.setFont("Helvetica", 10)
    c.drawRightString(w - m, h - 9.5 * mm, "TAX INVOICE")
    y = h - 22 * mm

    line(SELLER["name"], size=12, bold=True)
    line(SELLER["address"], size=9)
    line(f"GSTIN: {SELLER['gstin']}   SAC: {SELLER['sac']}   State: {SELLER['state']}", size=9)
    line(f"Email: {SELLER['email']}", size=9, dy=12)

    # Invoice meta
    line(f"Invoice No: {inv_no}", size=10, bold=True)
    paid_at = (pay.get("paid_at") or _now())[:19].replace("T", " ")
    line(f"Invoice Date: {paid_at} UTC", size=10)
    line(f"Order ID: {pay.get('order_id')}", size=9)
    line(f"Payment ID: {pay.get('payment_id') or '-'}", size=9)
    line(f"Payment Status: PAID (Razorpay {pay.get('mode', 'TEST')})", size=9, dy=12,
         color=(0.06, 0.62, 0.42))

    # Bill to
    line("Bill To:", size=10, bold=True)
    line(user.get("name") or user.get("email"), size=10)
    if user.get("organization_name"):
        line(user["organization_name"], size=9)
    line(user.get("email"), size=9, dy=14)

    # Table header
    c.setFillColorRGB(0.93, 0.96, 0.94)
    c.rect(m, y - 4, w - 2 * m, 18, fill=1, stroke=0)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(m + 4, y, "Description")
    c.drawString(m + 300, y, "SAC")
    c.drawRightString(w - m - 4, y, "Amount (INR)")
    y -= 24

    desc = f"{plan.get('name', pay.get('plan_id'))} — subscription ({plan.get('interval', 'month')})"
    c.setFont("Helvetica", 9)
    c.drawString(m + 4, y, desc)
    c.drawString(m + 300, y, SELLER["sac"])
    c.drawRightString(w - m - 4, y, f"{g['taxable']:.2f}")
    y -= 20

    def row(label, val, bold=False):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 9)
        c.drawString(m + 200, y, label)
        c.drawRightString(w - m - 4, y, f"{val:.2f}")
        y -= 16

    row("Taxable Value", g["taxable"])
    row("CGST @ 9%", g["cgst"])
    row("SGST @ 9%", g["sgst"])
    c.line(m + 200, y + 6, w - m, y + 6)
    row("Total (incl. GST)", g["total"], bold=True)

    y -= 20
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawString(m, y, "This is a computer-generated invoice and does not require a signature.")
    y -= 12
    c.drawString(m, y, "Amounts shown are GST-inclusive. Reverse charge: No.")

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()


@router.get("/receipt/{order_id}")
async def receipt(order_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    pay = await db.payments.find_one(
        {"order_id": order_id, "organization_id": user["organization_id"]}, {"_id": 0})
    if not pay:
        raise HTTPException(status_code=404, detail="Payment not found")
    if pay.get("status") != "PAID":
        raise HTTPException(status_code=400, detail="Receipt available only after payment is verified")
    inv_no = pay.get("invoice_no") or _invoice_no(order_id)
    if not pay.get("invoice_no"):
        await db.payments.update_one({"order_id": order_id}, {"$set": {"invoice_no": inv_no}})
    plan = next((p for p in billing.PLANS if p["id"] == pay.get("plan_id")), {})
    pdf = _build_invoice_pdf(pay, plan, user, inv_no)
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{inv_no}.pdf"'})


@router.get("/payments")
async def list_payments(user: dict = Depends(get_current_user)):
    rows = await get_db().payments.find(
        {"organization_id": user["organization_id"], "status": "PAID"},
        {"_id": 0, "order_id": 1, "invoice_no": 1, "plan_id": 1, "amount": 1,
         "currency": 1, "paid_at": 1, "mode": 1}).sort("paid_at", -1).to_list(50)
    return rows


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

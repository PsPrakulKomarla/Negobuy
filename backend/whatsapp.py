"""WhatsApp channel — Meta WhatsApp Cloud API.
Shares the central AI agent + mission memory. Returns NOT_CONFIGURED when credentials absent.
No live messages are simulated."""
import os
import hmac
import hashlib
import uuid
from datetime import datetime, timezone
import httpx
from fastapi import APIRouter, Depends, Request, Response, HTTPException
from auth import get_current_user
from db import get_db
import ai_service
import orchestrator

router = APIRouter(prefix="/api/webhooks", tags=["whatsapp"])
status_router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

GRAPH = "https://graph.facebook.com/v21.0"


def wa_configured() -> bool:
    return bool(os.environ.get("WHATSAPP_ACCESS_TOKEN")
                and os.environ.get("WHATSAPP_PHONE_NUMBER_ID"))


def _now():
    return datetime.now(timezone.utc).isoformat()


@status_router.get("/status")
async def whatsapp_status(user: dict = Depends(get_current_user)):
    return {
        "configured": wa_configured(),
        "state": "READY" if wa_configured() else "NOT_CONFIGURED",
        "provider": "meta_cloud_api",
        "requires": ["WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID",
                     "WHATSAPP_VERIFY_TOKEN", "WHATSAPP_APP_SECRET"],
        "message": ("WhatsApp channel is ready." if wa_configured()
                    else "WhatsApp requires Meta Cloud API credentials to send/receive messages."),
    }


@router.get("/whatsapp")
async def verify(request: Request):
    """Meta webhook verification handshake."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    if mode == "subscribe" and token and token == os.environ.get("WHATSAPP_VERIFY_TOKEN"):
        return Response(content=challenge or "", media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


def _valid_signature(raw: bytes, signature: str | None) -> bool:
    secret = os.environ.get("WHATSAPP_APP_SECRET")
    if not secret:
        return True  # cannot validate without secret; allow but log
    if not signature or not signature.startswith("sha256="):
        return False
    digest = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature.split("=", 1)[1])


async def _send_whatsapp(to: str, text: str) -> dict:
    if not wa_configured():
        return {"ok": False, "error": "WHATSAPP_NOT_CONFIGURED"}
    url = f"{GRAPH}/{os.environ['WHATSAPP_PHONE_NUMBER_ID']}/messages"
    headers = {"Authorization": f"Bearer {os.environ['WHATSAPP_ACCESS_TOKEN']}",
               "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text",
               "text": {"body": text}}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, headers=headers, json=payload)
    return {"ok": r.status_code < 300, "status_code": r.status_code, "body": r.text[:400]}


@router.post("/whatsapp")
async def incoming(request: Request):
    """Receive WhatsApp messages, route to the central AI agent within authority limits."""
    raw = await request.body()
    if not _valid_signature(raw, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=401, detail="Invalid signature")
    if not wa_configured():
        return {"status": "NOT_CONFIGURED"}
    data = await request.json()
    db = get_db()
    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    from_number = msg.get("from")
                    text = (msg.get("text") or {}).get("body", "")
                    await db.messages.insert_one({
                        "id": uuid.uuid4().hex, "channel": "whatsapp", "direction": "inbound",
                        "from": from_number, "text": text, "created_at": _now()})
                    # Identify vendor + mission by stored phone (shared memory).
                    vendor = await db.vendors.find_one({"contact_phones": {"$regex": from_number[-8:]}})
                    if not vendor:
                        continue
                    mission = await db.missions.find_one({"id": vendor["mission_id"]}, {"_id": 0})
                    if not mission:
                        continue
                    qty = mission.get("quantity") or 1
                    budget = mission.get("budget") or 0
                    max_price = round(budget / qty, 2) if (budget and qty) else None
                    constraints = {"max_price": max_price,
                                   "target_price": round(max_price * 0.9, 2) if max_price else None,
                                   "min_warranty": mission.get("warranty_requirements"),
                                   "max_delivery_days": mission.get("deadline_days")}
                    history = [{"role": "vendor", "text": text}]
                    reply = await ai_service.negotiation_turn(
                        mission, vendor, constraints, history, f"wa-{vendor['id']}")
                    reply_text = reply.get("message", "")
                    send_result = await _send_whatsapp(from_number, reply_text)
                    await db.messages.insert_one({
                        "id": uuid.uuid4().hex, "channel": "whatsapp", "direction": "outbound",
                        "to": from_number, "text": reply_text, "delivery": send_result,
                        "mission_id": mission["id"], "vendor_id": vendor["id"], "created_at": _now()})
                    await orchestrator.log_action(
                        mission["id"], "WhatsApp Agent", f"WhatsApp exchange with {vendor['name']}",
                        f"Vendor: {text[:80]} | AI: {reply_text[:80]}")
    except Exception as e:
        print(f"[whatsapp] processing error: {e}")
    return {"status": "received"}

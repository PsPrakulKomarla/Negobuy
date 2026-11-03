"""Communication Hub — ONE shared negotiation engine across messaging channels.

Reuses: negotiation_engine.converse/get_thread (shared brain + authority), missions/vendors,
audit.log_event, MongoDB. Providers are pluggable behind CommunicationProvider so the engine
never touches Telegram/WhatsApp/Instagram APIs directly.
"""
import os
import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from db import get_db
from auth import get_current_user
import audit
import ai_service
import negotiation_engine
from communication.telegram_provider import TelegramProvider
from communication.whatsapp_provider import WhatsAppProvider
from communication.instagram_provider import InstagramProvider

log = logging.getLogger("communication")
router = APIRouter(prefix="/api/communication", tags=["communication"])

PROVIDERS = {"telegram": TelegramProvider(), "whatsapp": WhatsAppProvider(),
             "instagram": InstagramProvider()}


def _now():
    return datetime.now(timezone.utc).isoformat()


def get_provider(channel: str):
    p = PROVIDERS.get(channel)
    if not p:
        raise HTTPException(status_code=400, detail=f"Unsupported channel: {channel}")
    return p


def _comm_state(thread: dict, had_reply: bool, outbound_only=False) -> str:
    """Map the shared engine's state to the messaging state machine."""
    state = thread.get("state")
    offer = thread.get("current_offer") or {}
    if outbound_only:
        return "OUTREACH_SENT"
    if thread.get("approval_status") == "pending" or state == "AWAITING_HUMAN_APPROVAL":
        return "BUYER_APPROVAL_REQUIRED"
    if thread.get("within_authority") is False:
        return "BUYER_APPROVAL_REQUIRED"
    if offer.get("unit_price"):
        return "NEGOTIATING"
    if had_reply:
        return "REQUIREMENTS_DISCUSSION"
    return "AWAITING_REPLY"


async def _store_message(db, conv, direction, sender, recipient, text, provider_msg_id,
                         delivery_status, sender_name=None):
    doc = {
        "id": uuid.uuid4().hex, "message_id": uuid.uuid4().hex,
        "organization_id": conv["organization_id"], "mission_id": conv["mission_id"],
        "vendor_id": conv["vendor_id"], "negotiation_thread_id": conv["thread_id"],
        "conversation_id": conv["id"], "channel": conv["channel"], "direction": direction,
        "sender": sender, "sender_name": sender_name, "recipient": recipient,
        "content": text, "normalized_content": text,
        "provider_message_id": provider_msg_id, "delivery_status": delivery_status,
        "kind": "messaging", "created_at": _now(), "timestamp": _now(),
    }
    await db.messages.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def _refresh_conversation(db, conv, thread, comm_state):
    offer = thread.get("current_offer") or {}
    upd = {
        "comm_state": comm_state,
        "approval_required": comm_state == "BUYER_APPROVAL_REQUIRED",
        "latest_quote": offer.get("unit_price"),
        "within_authority": thread.get("within_authority", True),
        "last_activity": _now(), "updated_at": _now(),
    }
    await db.conversations.update_one({"id": conv["id"]}, {"$set": upd})


async def _dedup(db, event_id: str) -> bool:
    """True if this provider event was already processed (idempotency)."""
    if not event_id:
        return False
    try:
        await db.comm_events.insert_one({"_id": event_id, "at": _now()})
        return False
    except Exception:
        return True


# --------------------------------------------------------------------------- #
# Status
# --------------------------------------------------------------------------- #
@router.get("/status")
async def status(user: dict = Depends(get_current_user)):
    return {"providers": [p.status() for p in PROVIDERS.values()],
            "default_channel": "telegram"}


# --------------------------------------------------------------------------- #
# Start a negotiation (authenticated) — generates + sends the opening outreach
# --------------------------------------------------------------------------- #
class StartBody(BaseModel):
    mission_id: str
    vendor_id: str
    channel: str
    recipient: str
    initial_message: str | None = None


@router.post("/negotiations/start")
async def start(body: StartBody, user: dict = Depends(get_current_user)):
    db = get_db()
    org = user["organization_id"]
    provider = get_provider(body.channel)
    mission = await db.missions.find_one({"id": body.mission_id, "organization_id": org}, {"_id": 0})
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    vendor = await db.vendors.find_one({"id": body.vendor_id, "mission_id": body.mission_id},
                                       {"_id": 0})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    if not body.recipient.strip():
        raise HTTPException(status_code=400, detail="A recipient identifier is required")

    thread = await negotiation_engine.get_thread(db, body.mission_id, body.vendor_id, org,
                                                 vendor.get("name"))
    # Professional opening outreach (authority-safe; identifies as AI, no commitment).
    if body.initial_message:
        outreach = body.initial_message
    else:
        constraints = negotiation_engine._constraints(mission)
        turn = await ai_service.engine_turn(
            mission, vendor, constraints, "INITIATE", {}, [],
            "[SYSTEM] Draft a short, professional opening outreach introducing yourself as "
            "NegoBuy's AI procurement assistant and asking for pricing/availability. Do not make "
            "any commitment.", session_id=f"engine-{body.mission_id}-{body.vendor_id}")
        outreach = turn.get("reply") or (
            f"Hello, this is NegoBuy's AI procurement assistant reaching out on behalf of a buyer "
            f"interested in {mission.get('title')}. Could you share your best pricing and "
            f"availability?")

    conv = await db.conversations.find_one(
        {"channel": body.channel, "recipient": body.recipient, "mission_id": body.mission_id,
         "vendor_id": body.vendor_id}, {"_id": 0})
    if not conv:
        conv = {
            "id": uuid.uuid4().hex, "organization_id": org, "mission_id": body.mission_id,
            "vendor_id": body.vendor_id, "vendor_name": vendor.get("name"),
            "mission_title": mission.get("title"), "thread_id": thread["id"],
            "channel": body.channel, "recipient": body.recipient,
            "comm_state": "OUTREACH_SENT", "approval_required": False,
            "target_price": negotiation_engine._constraints(mission).get("target_price"),
            "max_authority": negotiation_engine._constraints(mission).get("max_price"),
            "currency": mission.get("currency"), "latest_quote": None,
            "last_message": outreach, "last_activity": _now(),
            "created_at": _now(), "updated_at": _now(),
        }
        await db.conversations.insert_one(dict(conv))

    send = await provider.send_message(body.recipient, provider.format_response(outreach))
    await _store_message(db, conv, "OUTBOUND", "NEGOBUY_AI", body.recipient, outreach,
                         send.get("provider_message_id"), send.get("status"))
    await db.conversations.update_one({"id": conv["id"]},
                                      {"$set": {"comm_state": "OUTREACH_SENT" if send.get("ok")
                                                else "OUTREACH_FAILED",
                                                "last_message": outreach, "last_activity": _now()}})
    await audit.log_event(org, "message_sent", mission_id=body.mission_id, actor=user.get("name"),
                          detail=f"[{body.channel}] outreach to {vendor.get('name')} "
                                 f"({send.get('status')})")
    conv.pop("_id", None)
    return {"conversation_id": conv["id"], "thread_id": thread["id"],
            "channel": body.channel, "delivery": send,
            "provider_state": provider.status()["state"], "outreach": outreach}


# --------------------------------------------------------------------------- #
# Inbound webhook pipeline (shared across providers)
# --------------------------------------------------------------------------- #
async def _handle_inbound(db, channel: str, payload: dict, headers: dict, params: dict):
    provider = get_provider(channel)
    if not provider.validate_webhook(headers, params, payload):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    norm = provider.normalize_message(payload)
    if not norm:
        return {"status": "ignored"}
    if await _dedup(db, norm["event_id"]):
        return {"status": "duplicate"}

    conv = await db.conversations.find_one(
        {"channel": channel, "recipient": norm["sender"]}, {"_id": 0})
    if not conv:
        # Unknown chat with no mission context — store nothing, never auto-negotiate blindly.
        log.info("inbound %s from unknown recipient — ignored", channel)
        return {"status": "no_conversation"}

    await _store_message(db, conv, "INBOUND", norm["sender"], "NEGOBUY_AI", norm["text"],
                         norm["event_id"], "RECEIVED", sender_name=norm.get("sender_name"))
    await audit.log_event(conv["organization_id"], "whatsapp_reply", mission_id=conv["mission_id"],
                          detail=f"[{channel}] {conv['vendor_name']}: {norm['text'][:80]}")

    mission = await db.missions.find_one({"id": conv["mission_id"]}, {"_id": 0})
    vendor = await db.vendors.find_one({"id": conv["vendor_id"]}, {"_id": 0}) or \
        {"id": conv["vendor_id"], "name": conv["vendor_name"]}

    # Shared negotiation engine (authority enforced inside; never exceeds max/commits).
    thread = await negotiation_engine.converse(
        db, mission, vendor, conv["organization_id"], channel, norm["text"])
    reply = thread.get("reply", "")

    send = await provider.send_message(conv["recipient"], provider.format_response(reply))
    await _store_message(db, conv, "OUTBOUND", "NEGOBUY_AI", conv["recipient"], reply,
                         send.get("provider_message_id"), send.get("status"))
    comm_state = _comm_state(thread, had_reply=True)
    await _refresh_conversation(db, conv, thread, comm_state)
    await db.conversations.update_one({"id": conv["id"]},
                                      {"$set": {"last_message": reply, "last_activity": _now()}})
    return {"status": "handled", "comm_state": comm_state,
            "approval_required": comm_state == "BUYER_APPROVAL_REQUIRED"}


async def _merged(request: Request):
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    return body, {k.lower(): v for k, v in request.headers.items()}, dict(request.query_params)


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    body, headers, params = await _merged(request)
    return await _handle_inbound(get_db(), "telegram", body, headers, params)


@router.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    body, headers, params = await _merged(request)
    return await _handle_inbound(get_db(), "whatsapp", body, headers, params)


@router.post("/instagram/webhook")
async def instagram_webhook(request: Request):
    body, headers, params = await _merged(request)
    return await _handle_inbound(get_db(), "instagram", body, headers, params)


# --------------------------------------------------------------------------- #
# Dashboard reads
# --------------------------------------------------------------------------- #
@router.get("/negotiations")
async def list_conversations(user: dict = Depends(get_current_user)):
    db = get_db()
    return await db.conversations.find(
        {"organization_id": user["organization_id"]}, {"_id": 0}).sort("last_activity", -1).to_list(100)


@router.get("/negotiations/{conv_id}")
async def conversation_detail(conv_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    conv = await db.conversations.find_one(
        {"id": conv_id, "organization_id": user["organization_id"]}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = await db.messages.find({"conversation_id": conv_id}, {"_id": 0}).sort(
        "created_at", 1).to_list(300)
    thread = await db.negotiation_threads.find_one(
        {"mission_id": conv["mission_id"], "vendor_id": conv["vendor_id"]}, {"_id": 0}) or {}
    offer = thread.get("current_offer") or {}
    quote = offer.get("unit_price")
    target = conv.get("target_price")
    savings = None
    try:
        if quote and target and float(quote) > 0:
            savings = round(float(quote) - float(target), 2)
    except Exception:
        pass
    return {
        "conversation": conv, "messages": messages,
        "stage": conv.get("comm_state"), "target_price": target,
        "latest_quote": quote, "max_authority": conv.get("max_authority"),
        "currency": conv.get("currency"), "savings_gap": savings,
        "delivery": offer.get("delivery_days"), "within_authority": thread.get("within_authority", True),
        "approval_required": conv.get("approval_required", False),
        "next_action": thread.get("next_action"),
        "decision_summary": thread.get("decision_summary"),
    }


# --------------------------------------------------------------------------- #
# Human approval — never auto-commits a purchase
# --------------------------------------------------------------------------- #
class ApprovalBody(BaseModel):
    action: str  # ACCEPT | COUNTER | REJECT | CLARIFY
    note: str | None = None


@router.post("/negotiations/{conv_id}/approve")
async def approve(conv_id: str, body: ApprovalBody, user: dict = Depends(get_current_user)):
    if body.action not in {"ACCEPT", "COUNTER", "REJECT", "CLARIFY"}:
        raise HTTPException(status_code=400, detail="Invalid action")
    db = get_db()
    conv = await db.conversations.find_one(
        {"id": conv_id, "organization_id": user["organization_id"]}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    new_state = {"ACCEPT": "APPROVED", "REJECT": "REJECTED",
                 "COUNTER": "NEGOTIATING", "CLARIFY": "REQUIREMENTS_DISCUSSION"}[body.action]
    await db.conversations.update_one(
        {"id": conv_id},
        {"$set": {"comm_state": new_state, "approval_required": False,
                  "human_decision": {"action": body.action, "note": body.note,
                                     "by": user.get("name"), "at": _now()},
                  "updated_at": _now()}})
    await db.negotiation_threads.update_one(
        {"mission_id": conv["mission_id"], "vendor_id": conv["vendor_id"]},
        {"$set": {"approval_status": "approved" if body.action == "ACCEPT" else "in_progress"}})
    await audit.log_event(user["organization_id"],
                          "human_approved" if body.action == "ACCEPT" else "negotiation_action",
                          mission_id=conv["mission_id"], actor=user.get("name"),
                          detail=f"[{conv['channel']}] approval decision: {body.action}"
                                 + (f" — {body.note}" if body.note else ""))
    # ACCEPT records intent only — it does NOT create an order/purchase.
    return {"ok": True, "comm_state": new_state}

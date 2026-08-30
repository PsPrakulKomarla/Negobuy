"""Telegram USERBOT (MTProto / Telethon) autonomous negotiation.

Logs in as a REAL Telegram user account (per organization) so it can DM a vendor by
@username directly — something the Bot API cannot do. Given a material spec, a target
price and a hard walk-away maximum, an AI (Claude Sonnet 5) chats autonomously with the
vendor to drive the price to target. It NEVER agrees above the authorized maximum.

No simulation: every message is really sent/received through the linked Telegram account.
"""
import os
import json
import uuid
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from telethon import TelegramClient, events
from telethon.errors import (
    FloodWaitError, PhoneCodeExpiredError, PhoneCodeInvalidError,
    SessionPasswordNeededError, UsernameInvalidError, UsernameNotOccupiedError,
    PhoneNumberInvalidError,
)
from telethon.sessions import StringSession
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.types import InputPhoneContact

from db import get_db
from auth import get_current_user
import audit

log = logging.getLogger("telegram-userbot")
router = APIRouter(prefix="/api/telegram", tags=["telegram-userbot"])

NEGOTIATION_MODEL = "claude-sonnet-5"
MAX_AI_TURNS = 30

# Per-process runtime state (single supervisor worker).
clients: dict = {}          # org_id -> TelegramClient
login_state: dict = {}      # org_id -> {phone, phone_code_hash, api_id, api_hash}
deal_locks: dict = {}       # deal_id -> asyncio.Lock


def _now():
    return datetime.now(timezone.utc).isoformat()


def _lock(deal_id: str) -> asyncio.Lock:
    if deal_id not in deal_locks:
        deal_locks[deal_id] = asyncio.Lock()
    return deal_locks[deal_id]


# --------------------------------------------------------------------------- #
# AI negotiation brain (Claude Sonnet 5 via Emergent universal key)
# --------------------------------------------------------------------------- #
def _system_prompt(deal: dict) -> str:
    cur = deal.get("currency") or "INR"
    return (
        "You are an expert procurement buyer negotiating DIRECTLY with a supplier over a "
        "Telegram chat. You are texting like a real person — short, natural, professional "
        "messages (1-3 sentences), no markdown, no bullet lists, no emojis unless natural.\n\n"
        f"WHAT YOU WANT TO BUY: {deal.get('quantity') or ''} {deal.get('unit') or ''} of "
        f"{deal.get('material')}. {('Extra notes: ' + deal['notes']) if deal.get('notes') else ''}\n\n"
        f"PRICING (currency {cur}):\n"
        f"- Your TARGET price (the goal to reach): {deal.get('target_price')}\n"
        f"- Your ABSOLUTE MAXIMUM (hard walk-away limit): {deal.get('max_price')}\n\n"
        "STRICT RULES:\n"
        f"1. NEVER agree to, confirm, or commit to any price above {deal.get('max_price')}. This is a hard limit.\n"
        "2. NEVER reveal your target price or your maximum to the vendor.\n"
        "3. Negotiate hard but politely to push the price down toward the target. Use tactics: "
        "ask for their best/final price, mention comparing other quotes, request bulk/loyalty discount, "
        "question high quotes.\n"
        "4. If the vendor quotes at or below your TARGET, accept and confirm the deal warmly.\n"
        "5. If the vendor lands between target and maximum and won't budge after real effort, you MAY accept "
        "to close the deal (but never above the maximum).\n"
        "6. If the vendor refuses to go to/under the maximum, is unresponsive, or clearly won't deal, give up politely.\n"
        "7. Track the latest concrete numeric price the vendor quoted for this material.\n\n"
        "Reply ONLY with strict minified JSON, no prose around it:\n"
        '{"message": "<exact text to send the vendor>", "quoted_price": <number or null>, '
        '"deal_reached": <true|false>, "give_up": <true|false>, "reasoning": "<short private note>"}'
    )


def _parse_json(raw: str) -> dict:
    t = (raw or "").strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if "```" in t[3:] else t.strip("`")
        if t.lstrip().startswith("json"):
            t = t.lstrip()[4:]
    s, e = t.find("{"), t.rfind("}")
    if s != -1 and e != -1:
        t = t[s:e + 1]
    return json.loads(t)


async def ai_negotiate(deal: dict, opening: bool = False) -> dict:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    key = os.environ["EMERGENT_LLM_KEY"]
    chat = LlmChat(api_key=key, session_id=f"tg-deal-{deal['id']}",
                   system_message=_system_prompt(deal)).with_model("anthropic", NEGOTIATION_MODEL)

    if opening:
        prompt = ("Send the FIRST outreach message to this vendor to open the negotiation. Introduce "
                  "your interest in the material and ask for their best price and availability. Do not "
                  "state any target/budget. Return the JSON.")
    else:
        lines = []
        for m in deal.get("transcript", []):
            who = "YOU" if m["role"] == "ai" else "VENDOR"
            lines.append(f"{who}: {m['text']}")
        prompt = ("Here is the conversation so far:\n\n" + "\n".join(lines) +
                  "\n\nDecide your next move and return the JSON. The 'message' is what you will send "
                  "the vendor next (leave it short/empty only if give_up or deal_reached warrants a closing line).")

    resp = await chat.send_message(UserMessage(text=prompt))
    text = resp if isinstance(resp, str) else str(resp)
    try:
        data = _parse_json(text)
    except Exception:
        data = {"message": text.strip()[:800], "quoted_price": None,
                "deal_reached": False, "give_up": False, "reasoning": "unparsed"}
    data.setdefault("message", "")
    data.setdefault("quoted_price", None)
    data.setdefault("deal_reached", False)
    data.setdefault("give_up", False)
    return data


def _within_max(price, max_price) -> bool:
    try:
        return float(price) <= float(max_price)
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Telethon client lifecycle
# --------------------------------------------------------------------------- #
async def _build_client(api_id: int, api_hash: str, session: str = "") -> TelegramClient:
    client = TelegramClient(StringSession(session), int(api_id), api_hash,
                            auto_reconnect=True, request_retries=3, connection_retries=3)
    await client.connect()
    return client


def _make_handler(org_id: str):
    async def handler(event):
        try:
            await _on_vendor_message(org_id, event)
        except Exception:
            log.exception("telegram handler error org=%s", org_id)
    return handler


async def _register_handler(org_id: str, client: TelegramClient):
    client.add_event_handler(_make_handler(org_id), events.NewMessage(incoming=True))
    asyncio.create_task(_keep_alive(org_id, client))


async def _keep_alive(org_id: str, client: TelegramClient):
    try:
        await client.run_until_disconnected()
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("telegram receiver stopped org=%s", org_id)


async def startup():
    """Reconnect every previously-authorized org account on boot."""
    db = get_db()
    accounts = await db.telegram_accounts.find({"session": {"$ne": None}}, {"_id": 0}).to_list(100)
    for acc in accounts:
        if not acc.get("session"):
            continue
        try:
            client = await _build_client(acc["api_id"], acc["api_hash"], acc["session"])
            if await client.is_user_authorized():
                clients[acc["organization_id"]] = client
                await _register_handler(acc["organization_id"], client)
                log.info("telegram userbot reconnected org=%s", acc["organization_id"])
            else:
                await client.disconnect()
        except Exception:
            log.exception("telegram reconnect failed org=%s", acc.get("organization_id"))


async def shutdown():
    for client in list(clients.values()):
        try:
            if client.is_connected():
                await client.disconnect()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Incoming vendor message -> autonomous AI negotiation
# --------------------------------------------------------------------------- #
async def _on_vendor_message(org_id: str, event):
    db = get_db()
    sender_id = event.sender_id
    deal = await db.telegram_deals.find_one(
        {"organization_id": org_id, "vendor_user_id": sender_id, "status": "ACTIVE"}, {"_id": 0})
    if not deal:
        return  # no active negotiation with this person — ignore

    async with _lock(deal["id"]):
        deal = await db.telegram_deals.find_one({"id": deal["id"]}, {"_id": 0})
        if not deal or deal.get("status") != "ACTIVE":
            return
        text = event.raw_text or ""
        transcript = deal.get("transcript", [])
        transcript.append({"role": "vendor", "text": text, "at": _now()})
        turns = deal.get("ai_turns", 0)

        if turns >= MAX_AI_TURNS:
            decision = {"message": "Thanks for your time. I'll get back to you if things change.",
                        "quoted_price": None, "deal_reached": False, "give_up": True,
                        "reasoning": "turn cap"}
        else:
            deal["transcript"] = transcript
            decision = await ai_negotiate(deal)

        quoted = decision.get("quoted_price")
        max_price = deal.get("max_price")
        agreed_price = deal.get("agreed_price")
        status = "ACTIVE"

        deal_reached = bool(decision.get("deal_reached"))
        # Hard authority guard: never let the AI close above the maximum.
        if deal_reached and quoted is not None and not _within_max(quoted, max_price):
            deal_reached = False
            decision["message"] = ("That's a bit above what I can do right now. Can you sharpen the price "
                                   "a little more?")
        if deal_reached:
            status = "DEAL_REACHED"
            agreed_price = quoted if quoted is not None else deal.get("latest_quote")
        elif decision.get("give_up"):
            status = "FAILED"

        msg = (decision.get("message") or "").strip()
        send_status = "SKIPPED"
        if msg:
            try:
                await event.client.send_message(await event.get_input_sender(), msg)
                send_status = "SENT"
                transcript.append({"role": "ai", "text": msg, "at": _now()})
            except FloodWaitError as e:
                send_status = f"FLOOD_WAIT_{e.seconds}s"
            except Exception:
                log.exception("send failed deal=%s", deal["id"])
                send_status = "SEND_FAILED"

        upd = {
            "transcript": transcript, "status": status,
            "ai_turns": turns + 1, "updated_at": _now(),
            "last_send_status": send_status,
        }
        if quoted is not None:
            upd["latest_quote"] = quoted
        if agreed_price is not None:
            upd["agreed_price"] = agreed_price
        if status != "ACTIVE":
            upd["outcome_summary"] = decision.get("reasoning")
        await db.telegram_deals.update_one({"id": deal["id"]}, {"$set": upd})
        await audit.log_event(org_id, "telegram_negotiation",
                              detail=f"[telegram] {deal.get('vendor_username')} -> {status} "
                                     f"(quote {quoted})")


# --------------------------------------------------------------------------- #
# Account linking endpoints
# --------------------------------------------------------------------------- #
class LinkStart(BaseModel):
    api_id: int
    api_hash: str = Field(min_length=8)
    phone: str = Field(min_length=5, max_length=32)


class LinkVerify(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    password: str | None = None


@router.get("/status")
async def status(user: dict = Depends(get_current_user)):
    org = user["organization_id"]
    db = get_db()
    acc = await db.telegram_accounts.find_one({"organization_id": org}, {"_id": 0})
    client = clients.get(org)
    authorized = False
    if client:
        try:
            authorized = await client.is_user_authorized()
        except Exception:
            authorized = False
    return {
        "linked": bool(acc and acc.get("session")) or authorized,
        "authorized": authorized,
        "username": acc.get("username") if acc else None,
        "phone": acc.get("phone") if acc else None,
        "pending_code": org in login_state,
    }


@router.post("/link/start")
async def link_start(body: LinkStart, user: dict = Depends(get_current_user)):
    org = user["organization_id"]
    # Tear down any half-open client for this org first.
    old = clients.pop(org, None)
    if old:
        try:
            await old.disconnect()
        except Exception:
            pass
    try:
        client = await _build_client(body.api_id, body.api_hash, "")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not connect with these API credentials")
    if await client.is_user_authorized():
        clients[org] = client
        await _register_handler(org, client)
        return {"status": "already_authorized"}
    try:
        sent = await client.send_code_request(body.phone)
    except PhoneNumberInvalidError:
        await client.disconnect()
        raise HTTPException(status_code=400, detail="Invalid phone number")
    except Exception as e:
        await client.disconnect()
        raise HTTPException(status_code=400, detail=f"Could not send login code: {type(e).__name__}")
    clients[org] = client
    login_state[org] = {"phone": body.phone, "phone_code_hash": sent.phone_code_hash,
                        "api_id": body.api_id, "api_hash": body.api_hash}
    return {"status": "code_sent"}


@router.post("/link/verify")
async def link_verify(body: LinkVerify, user: dict = Depends(get_current_user)):
    org = user["organization_id"]
    st = login_state.get(org)
    client = clients.get(org)
    if not st or not client:
        raise HTTPException(status_code=409, detail="Start the login first")
    try:
        try:
            await client.sign_in(phone=st["phone"], code=body.code,
                                 phone_code_hash=st["phone_code_hash"])
        except SessionPasswordNeededError:
            if not body.password:
                raise HTTPException(status_code=428, detail="Two-factor password required")
            await client.sign_in(password=body.password)
    except PhoneCodeInvalidError:
        raise HTTPException(status_code=400, detail="Invalid login code")
    except PhoneCodeExpiredError:
        login_state.pop(org, None)
        raise HTTPException(status_code=400, detail="Login code expired — start again")

    me = await client.get_me()
    session_str = client.session.save()
    db = get_db()
    await db.telegram_accounts.update_one(
        {"organization_id": org},
        {"$set": {"organization_id": org, "api_id": st["api_id"], "api_hash": st["api_hash"],
                  "phone": st["phone"], "session": session_str,
                  "username": me.username, "user_id": me.id, "updated_at": _now()}},
        upsert=True)
    login_state.pop(org, None)
    await _register_handler(org, client)
    return {"status": "authorized", "username": me.username,
            "name": (me.first_name or "") + ((" " + me.last_name) if me.last_name else "")}


@router.post("/unlink")
async def unlink(user: dict = Depends(get_current_user)):
    org = user["organization_id"]
    client = clients.pop(org, None)
    if client:
        try:
            await client.log_out()
        except Exception:
            try:
                await client.disconnect()
            except Exception:
                pass
    login_state.pop(org, None)
    await get_db().telegram_accounts.delete_one({"organization_id": org})
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Deals (negotiations)
# --------------------------------------------------------------------------- #
class DealBody(BaseModel):
    vendor_username: str = Field(min_length=2)
    vendor_name: str | None = None
    material: str = Field(min_length=1)
    quantity: float | None = None
    unit: str | None = None
    target_price: float
    max_price: float
    currency: str = "INR"
    notes: str | None = None


def _clean_username(u: str) -> str:
    u = u.strip()
    if u.startswith("https://t.me/"):
        u = u.split("t.me/", 1)[1]
    return u.lstrip("@")


def _is_phone(v: str) -> bool:
    d = v.strip().replace(" ", "").replace("-", "")
    return d.startswith("+") or (d.isdigit() and len(d) >= 10)


def _norm_phone(v: str, default_cc: str = "91") -> str:
    d = v.strip().replace(" ", "").replace("-", "")
    if d.startswith("+"):
        return d
    if d.isdigit() and len(d) == 10:
        return "+" + default_cc + d
    return "+" + d


async def _resolve_vendor(client, identifier: str, name_hint: str | None):
    """Resolve a vendor by @username OR phone number (imported as a contact)."""
    if _is_phone(identifier):
        phone = _norm_phone(identifier)
        contact = InputPhoneContact(client_id=0, phone=phone,
                                    first_name=(name_hint or "Vendor"), last_name="")
        res = await client(ImportContactsRequest([contact]))
        if not res.users:
            raise HTTPException(status_code=404,
                                detail=f"{phone} is not on Telegram (no account found for this number)")
        entity = res.users[0]
        return entity, phone
    username = _clean_username(identifier)
    try:
        entity = await client.get_entity(username)
    except (UsernameInvalidError, UsernameNotOccupiedError, ValueError):
        raise HTTPException(status_code=404, detail=f"Telegram user @{username} not found")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not resolve that Telegram username")
    return entity, username


@router.post("/deals")
async def create_deal(body: DealBody, user: dict = Depends(get_current_user)):
    org = user["organization_id"]
    client = clients.get(org)
    if not client or not await client.is_user_authorized():
        raise HTTPException(status_code=400, detail="Link your Telegram account first")
    if body.max_price < body.target_price:
        raise HTTPException(status_code=400, detail="Maximum price must be >= target price")

    entity, vendor_ref = await _resolve_vendor(client, body.vendor_username, body.vendor_name)

    deal = {
        "id": uuid.uuid4().hex, "organization_id": org, "created_by": user["id"],
        "vendor_username": vendor_ref, "vendor_user_id": entity.id,
        "vendor_display_name": body.vendor_name or getattr(entity, "first_name", None) or vendor_ref,
        "material": body.material, "quantity": body.quantity, "unit": body.unit,
        "currency": body.currency, "target_price": body.target_price, "max_price": body.max_price,
        "notes": body.notes, "status": "ACTIVE", "transcript": [], "ai_turns": 0,
        "latest_quote": None, "agreed_price": None, "outcome_summary": None,
        "created_at": _now(), "updated_at": _now(),
    }

    opener = await ai_negotiate(deal, opening=True)
    msg = (opener.get("message") or "").strip() or (
        f"Hi, I'm interested in {body.material}. Could you share your best price and availability?")
    try:
        await client.send_message(entity, msg)
    except FloodWaitError as e:
        raise HTTPException(status_code=429, detail=f"Telegram flood wait: retry after {e.seconds}s")
    except Exception:
        raise HTTPException(status_code=502, detail="Failed to send the opening message on Telegram")

    deal["transcript"].append({"role": "ai", "text": msg, "at": _now()})
    await get_db().telegram_deals.insert_one(dict(deal))
    await audit.log_event(org, "telegram_negotiation", actor=user.get("name"),
                          detail=f"[telegram] opened negotiation with {vendor_ref} for {body.material}")
    deal.pop("_id", None)
    return deal


@router.get("/deals")
async def list_deals(user: dict = Depends(get_current_user)):
    return await get_db().telegram_deals.find(
        {"organization_id": user["organization_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)


@router.get("/deals/{deal_id}")
async def get_deal(deal_id: str, user: dict = Depends(get_current_user)):
    deal = await get_db().telegram_deals.find_one(
        {"id": deal_id, "organization_id": user["organization_id"]}, {"_id": 0})
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal


@router.post("/deals/{deal_id}/stop")
async def stop_deal(deal_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    deal = await db.telegram_deals.find_one(
        {"id": deal_id, "organization_id": user["organization_id"]}, {"_id": 0})
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    await db.telegram_deals.update_one(
        {"id": deal_id}, {"$set": {"status": "STOPPED", "updated_at": _now()}})
    return {"ok": True, "status": "STOPPED"}

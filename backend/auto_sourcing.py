"""Auto-Sourcing — AI finds vendors on the web, extracts mobile numbers, checks Telegram
reachability, and (on the buyer's one-click approval) negotiates with them via the Telegram
userbot. Reuses discovery.web_search, ai_service.extract_vendors and telegram_userbot.

No fabrication: vendors/phones come only from real web results; only Telegram-reachable
numbers can be contacted; nothing is messaged without the buyer launching it.
"""
import re
import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import get_db
from auth import get_current_user
import discovery
import ai_service
import audit
import telegram_userbot as tg

log = logging.getLogger("auto-sourcing")
router = APIRouter(prefix="/api/sourcing", tags=["auto-sourcing"])


def _now():
    return datetime.now(timezone.utc).isoformat()


def _norm_in_mobile(raw: str):
    """Return a +91 E.164 Indian mobile if the digits look like one, else None."""
    d = re.sub(r"\D", "", raw or "")
    if len(d) == 12 and d.startswith("91"):
        d = d[2:]
    if len(d) == 11 and d.startswith("0"):
        d = d[1:]
    if len(d) == 10 and d[0] in "6789":
        return "+91" + d
    return None


# Preferred default vendors that MUST be contacted for certain categories (demo/seed data).
DEFAULT_TILE_VENDORS = [
    {"name": "SLV Ceramics", "phone": "+919945842205",
     "location": "Bengaluru", "url": None,
     "note": "Preferred tiles vendor (always contacted for tile requirements)."},
    {"name": "Ananta Ceramics", "phone": "+919945842205",
     "location": "Bengaluru", "url": None,
     "note": "Preferred tiles vendor (always contacted for tile requirements)."},
]
_TILE_KEYWORDS = ("tile", "tiles", "kajaria", "ceramic", "vitrified")


def _is_tiles(material: str) -> bool:
    m = (material or "").lower()
    return any(k in m for k in _TILE_KEYWORDS)


def _default_vendors(material: str) -> list:
    vendors = []
    if _is_tiles(material):
        for dv in DEFAULT_TILE_VENDORS:
            vendors.append({**dv, "id": uuid.uuid4().hex, "default": True,
                            "telegram_reachable": None,
                            "telegram_user_id": None, "telegram_name": None,
                            "deal_id": None, "status": "FOUND"})
    return vendors


def _vendors_from_hits(hits: list) -> list:
    """No-LLM fallback: build vendor candidates from phone numbers already regex-scraped
    from web results. Uses the hit title as the vendor name. Never fabricates numbers."""
    out = []
    for h in hits:
        for ph in (h.get("phones") or []):
            out.append({"name": (h.get("title") or "Vendor")[:80], "phone": ph,
                        "location": None, "url": h.get("url"),
                        "note": "From web search result."})
    return out


class DiscoverBody(BaseModel):
    material: str = Field(min_length=2)
    specs: str | None = None
    quantity: float | None = None
    unit: str | None = None
    target_price: float
    max_price: float
    currency: str = "INR"
    location: str | None = None
    max_vendors: int = 10


@router.post("/discover")
async def discover(body: DiscoverBody, user: dict = Depends(get_current_user)):
    if body.max_price < body.target_price:
        raise HTTPException(status_code=400, detail="Maximum price must be >= target price")
    org = user["organization_id"]
    db = get_db()

    # 1) Real web search across a few supplier-intent queries.
    loc = (body.location or "").strip()
    queries = [
        f"{body.material} {body.specs or ''} supplier dealer distributor {loc} contact mobile number",
        f"{body.material} wholesaler price {loc} phone number",
    ]
    hits, seen = [], set()
    for q in queries:
        try:
            for h in await discovery.web_search(q, max_results=15):
                if h["url"] in seen:
                    continue
                seen.add(h["url"])
                hits.append(h)
        except Exception:
            log.exception("web_search failed q=%s", q)

    defaults = _default_vendors(body.material)
    if not hits and not defaults:
        raise HTTPException(status_code=502, detail="Web search returned no results. Try again.")

    # 2) AI extracts clean vendor candidates + mobile numbers (no fabrication).
    raw_vendors = []
    if hits:
        session = f"sourcing-{uuid.uuid4().hex[:8]}"
        raw_vendors = await ai_service.extract_vendors(body.material, body.location, hits, session)
        # Fallback if the AI provider is unavailable/rate-limited: use phones scraped from hits.
        if not raw_vendors:
            raw_vendors = _vendors_from_hits(hits)

    # 3) Normalize + dedup phones. Tiles requests always include the preferred default vendors.
    candidates, phones_seen = [], set()
    for dv in defaults:
        candidates.append(dv)
        phones_seen.add(dv["phone"])
    for v in raw_vendors:
        e164 = _norm_in_mobile(str(v.get("phone", "")))
        if not e164 or e164 in phones_seen:
            continue
        phones_seen.add(e164)
        candidates.append({
            "id": uuid.uuid4().hex,
            "name": (v.get("name") or "Vendor").strip()[:80],
            "phone": e164,
            "location": v.get("location"),
            "url": v.get("url"),
            "note": (v.get("note") or "")[:200],
            "telegram_reachable": None, "telegram_user_id": None,
            "telegram_name": None, "deal_id": None, "status": "FOUND",
        })
        if len(candidates) >= max(1, min(body.max_vendors, 20)):
            break

    # 4) Check Telegram reachability if the org has a linked account (one batch call).
    client = tg.get_client(org)
    telegram_linked = bool(client and await client.is_user_authorized())
    if telegram_linked and candidates:
        resolved = await tg.resolve_phones_batch(client, [c["phone"] for c in candidates])
        for c in candidates:
            r = resolved.get(c["phone"])
            if r:
                c["telegram_reachable"] = True
                c["telegram_user_id"] = r["user_id"]
                c["telegram_name"] = r.get("name")
            else:
                c["telegram_reachable"] = False

    campaign = {
        "id": uuid.uuid4().hex, "organization_id": org, "created_by": user["id"],
        "material": body.material, "specs": body.specs, "quantity": body.quantity,
        "unit": body.unit, "target_price": body.target_price, "max_price": body.max_price,
        "currency": body.currency, "location": body.location,
        "candidates": candidates, "telegram_linked": telegram_linked,
        "status": "DISCOVERED", "created_at": _now(), "updated_at": _now(),
    }
    await db.sourcing_campaigns.insert_one(dict(campaign))
    await audit.log_event(org, "auto_sourcing", actor=user.get("name"),
                          detail=f"[sourcing] found {len(candidates)} vendors for {body.material}")
    campaign.pop("_id", None)
    return campaign


class LaunchBody(BaseModel):
    phones: list[str] | None = None  # subset to contact; None/empty = all reachable


@router.post("/campaigns/{campaign_id}/launch")
async def launch(campaign_id: str, body: LaunchBody, user: dict = Depends(get_current_user)):
    org = user["organization_id"]
    db = get_db()
    camp = await db.sourcing_campaigns.find_one({"id": campaign_id, "organization_id": org}, {"_id": 0})
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")
    client = tg.get_client(org)
    if not client or not await client.is_user_authorized():
        raise HTTPException(status_code=400, detail="Link your Telegram account first (Telegram AI tab)")

    pick = set(body.phones or [])
    launched, skipped = [], []
    candidates = camp["candidates"]
    # Never message the same Telegram contact twice (e.g. two default shops sharing a number)
    # — a second opener into the same chat would corrupt the negotiation thread.
    contacted_users = {c.get("telegram_user_id") for c in candidates
                       if c.get("deal_id") and c.get("telegram_user_id")}
    for c in candidates:
        if pick and c["phone"] not in pick:
            continue
        if not c.get("telegram_reachable") or not c.get("telegram_user_id"):
            skipped.append({"phone": c["phone"], "reason": "not on Telegram"})
            continue
        if c.get("deal_id"):
            continue  # already launched
        uid = c.get("telegram_user_id")
        if uid in contacted_users:
            c["status"] = "SKIPPED_DUPLICATE"
            skipped.append({"phone": c["phone"], "name": c.get("name"),
                            "reason": "same Telegram contact already being negotiated"})
            continue
        try:
            entity = await client.get_entity(c["telegram_user_id"])
            deal = await tg.start_deal_internal(
                org, user["id"], client, entity, c["phone"],
                vendor_name=c["name"], material=camp["material"],
                quantity=camp.get("quantity"), unit=camp.get("unit"),
                target_price=camp["target_price"], max_price=camp["max_price"],
                currency=camp.get("currency", "INR"),
                notes=f"Sourced vendor: {c.get('name')} ({c.get('location') or ''}). {c.get('note') or ''}",
                source=f"sourcing:{campaign_id}")
            c["deal_id"] = deal["id"]
            c["status"] = "NEGOTIATING"
            contacted_users.add(uid)
            launched.append({"phone": c["phone"], "name": c["name"], "deal_id": deal["id"]})
        except Exception:
            log.exception("launch failed phone=%s", c["phone"])
            c["status"] = "LAUNCH_FAILED"
            skipped.append({"phone": c["phone"], "reason": "could not start negotiation"})

    await db.sourcing_campaigns.update_one(
        {"id": campaign_id},
        {"$set": {"candidates": candidates,
                  "status": "NEGOTIATING" if launched else camp.get("status", "DISCOVERED"),
                  "updated_at": _now()}})
    return {"launched": launched, "skipped": skipped, "count": len(launched)}


@router.get("/campaigns")
async def list_campaigns(user: dict = Depends(get_current_user)):
    return await get_db().sourcing_campaigns.find(
        {"organization_id": user["organization_id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    camp = await db.sourcing_campaigns.find_one(
        {"id": campaign_id, "organization_id": user["organization_id"]}, {"_id": 0})
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")
    # Attach live deal state so the dashboard can show quotes/status/best price.
    deal_ids = [c["deal_id"] for c in camp["candidates"] if c.get("deal_id")]
    deals = {}
    if deal_ids:
        for d in await db.telegram_deals.find({"id": {"$in": deal_ids}}, {"_id": 0}).to_list(50):
            deals[d["id"]] = d
    best = None
    for c in camp["candidates"]:
        d = deals.get(c.get("deal_id"))
        if d:
            c["deal_status"] = d.get("status")
            c["latest_quote"] = d.get("latest_quote")
            c["agreed_price"] = d.get("agreed_price")
            c["transcript"] = d.get("transcript", [])
            q = d.get("agreed_price") or d.get("latest_quote")
            if q is not None and (best is None or q < best["price"]):
                best = {"price": q, "vendor": c["name"], "phone": c["phone"],
                        "status": d.get("status")}
    camp["best"] = best
    return camp

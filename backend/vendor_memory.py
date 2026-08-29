"""Cross-mission vendor memory — remembers negotiated prices and outcomes per supplier."""
import uuid
from datetime import datetime, timezone
from db import get_db


def _now():
    return datetime.now(timezone.utc).isoformat()


async def get_memory(org_id: str, domain: str | None) -> dict | None:
    if not domain:
        return None
    return await get_db().vendor_memory.find_one(
        {"organization_id": org_id, "domain": domain}, {"_id": 0})


def memory_note(mem: dict | None) -> str | None:
    if not mem:
        return None
    parts = [f"We have negotiated with this supplier {mem.get('negotiations_count', 0)} time(s) before."]
    if mem.get("best_price") is not None:
        parts.append(f"Best price previously secured: {mem['best_price']} per unit.")
    if mem.get("last_price") is not None:
        parts.append(f"Most recent price: {mem['last_price']} per unit.")
    return " ".join(parts)


async def record_outcome(org_id: str, vendor: dict, mission_id: str,
                         price, source: str = "negotiation"):
    db = get_db()
    domain = vendor.get("domain")
    if not domain:
        return
    mem = await db.vendor_memory.find_one({"organization_id": org_id, "domain": domain})
    now = _now()
    outcome = {"mission_id": mission_id, "price": price, "source": source, "at": now}
    if not mem:
        await db.vendor_memory.insert_one({
            "id": uuid.uuid4().hex, "organization_id": org_id, "domain": domain,
            "name": vendor.get("name"), "website": vendor.get("website"),
            "negotiations_count": 1, "last_price": price, "best_price": price,
            "missions": [mission_id], "reliability_score": vendor.get("reliability_score"),
            "outcomes": [outcome], "created_at": now, "last_interaction": now,
        })
    else:
        best = mem.get("best_price")
        if price is not None and (best is None or price < best):
            best = price
        missions = sorted(set((mem.get("missions") or []) + [mission_id]))
        await db.vendor_memory.update_one(
            {"_id": mem["_id"]},
            {"$set": {"last_price": price, "best_price": best, "missions": missions,
                      "name": vendor.get("name"), "website": vendor.get("website"),
                      "last_interaction": now},
             "$inc": {"negotiations_count": 1},
             "$push": {"outcomes": outcome}})


async def list_memory(org_id: str) -> list:
    return await get_db().vendor_memory.find(
        {"organization_id": org_id}, {"_id": 0}).sort("last_interaction", -1).to_list(200)

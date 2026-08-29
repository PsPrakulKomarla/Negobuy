"""Plan entitlement enforcement — reads limits from the billing plan catalog."""
from fastapi import HTTPException
from db import get_db
import billing

TERMINAL = ["COMPLETED", "CANCELLED", "REJECTED", "APPROVED"]


def plan_limits(plan_id: str) -> dict:
    p = next((p for p in billing.PLANS if p["id"] == plan_id), None)
    return (p or billing.PLANS[0]).get("limits", {})


async def active_mission_count(org_id: str) -> int:
    return await get_db().missions.count_documents(
        {"organization_id": org_id, "status": {"$nin": TERMINAL}})


async def check_mission_quota(user: dict):
    plan = user.get("plan", "free")
    limit = plan_limits(plan).get("active_missions")
    if limit is None:
        return
    count = await active_mission_count(user["organization_id"])
    if count >= limit:
        raise HTTPException(
            status_code=402,
            detail=(f"You've reached your plan limit of {limit} active mission(s) on the "
                    f"'{plan}' plan. Complete or cancel a mission, or upgrade to run more."))


async def voice_minutes_remaining(user: dict):
    plan = user.get("plan", "free")
    limit = plan_limits(plan).get("voice_minutes", 0)
    usage = await get_db().usage.find_one({"organization_id": user["organization_id"]}, {"_id": 0})
    used = round((usage or {}).get("voice_minutes_used", 0), 2)
    if limit is None:
        return {"limit": None, "used": used, "remaining": None}
    return {"limit": limit, "used": used, "remaining": max(0, round(limit - used, 2))}


async def add_voice_usage(org_id: str, minutes: float):
    await get_db().usage.update_one(
        {"organization_id": org_id},
        {"$inc": {"voice_minutes_used": round(minutes, 2)}}, upsert=True)

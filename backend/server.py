import os
from dotenv import load_dotenv
load_dotenv()

import uuid
from datetime import datetime, timezone
from fastapi import FastAPI, APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db import get_db, create_indexes
from auth import router as auth_router, get_current_user, seed_admin
from billing import router as billing_router
from voice import (router as voice_router, register_realtime, voice_configured,
                   telephony_configured)
from team import router as team_router
from reports import router as reports_router
from outreach import router as outreach_router
from whatsapp import router as whatsapp_router, status_router as whatsapp_status_router, wa_configured
from email_service import email_configured, sender_email
import ai_service
import discovery
import orchestrator
import entitlements
import vendor_memory
import audit
from payments import router as payments_router, webhook_router as razorpay_webhook_router
from telephony import router as telephony_router
from landed_cost import compute_landed_cost

app = FastAPI(title="NegoBuy API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ============================ CORE / HEALTH ============================
core = APIRouter(prefix="/api")


@core.get("/")
async def root():
    return {"service": "NegoBuy API", "status": "online"}


@core.get("/system/status")
async def system_status(user: dict = Depends(get_current_user)):
    razorpay = ("LIVE" if os.environ.get("RAZORPAY_KEY_ID", "").startswith("rzp_live")
                else "TEST" if os.environ.get("RAZORPAY_KEY_ID") else "NOT_CONFIGURED")
    return {
        "ai": {"state": "CONFIGURED" if ai_service.is_configured() else "NOT_CONFIGURED",
               "configured": ai_service.is_configured(), "model": os.environ.get("LLM_MODEL"),
               "provider": "openai"},
        "discovery": {"state": "CONFIGURED", "configured": discovery.search_configured(),
                      "has_key": discovery.has_search_key(), "provider": "tavily"},
        "email": {"state": "CONFIGURED" if email_configured() else "NOT_CONFIGURED",
                  "configured": email_configured(), "sender": sender_email(), "provider": "sendgrid"},
        "voice": {"state": "READY" if voice_configured() else "NOT_CONFIGURED",
                  "configured": voice_configured(), "provider": "openai_realtime"},
        "telephony": {"state": "READY" if telephony_configured() else "NOT_CONFIGURED",
                      "configured": telephony_configured(), "provider": "twilio"},
        "whatsapp": {"state": "READY" if wa_configured() else "NOT_CONFIGURED",
                     "configured": wa_configured(), "provider": "meta_cloud_api"},
        "payments": {"state": razorpay, "configured": razorpay != "NOT_CONFIGURED",
                     "provider": "razorpay"},
    }


# ============================ MISSIONS ============================
missions = APIRouter(prefix="/api/missions", tags=["missions"])

MISSION_STATUSES = ["DRAFT", "REQUIREMENT_REVIEW", "DISCOVERING", "VERIFYING", "CONTACTING",
                    "NEGOTIATING", "COMPARING", "AWAITING_APPROVAL", "APPROVED", "REJECTED",
                    "COMPLETED", "CANCELLED"]


class ExtractBody(BaseModel):
    text: str


class MissionCreate(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None
    quantity: int | None = None
    unit: str | None = None
    budget: float | None = None
    currency: str | None = "INR"
    delivery_location: str | None = None
    deadline_days: int | None = None
    required_delivery_date: str | None = None
    specifications: list[str] = []
    quality_requirements: list[str] = []
    warranty_requirements: str | None = None
    payment_requirements: str | None = None
    raw_request: str | None = None


class MissionUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None
    quantity: int | None = None
    budget: float | None = None
    currency: str | None = None
    delivery_location: str | None = None
    deadline_days: int | None = None
    warranty_requirements: str | None = None
    payment_requirements: str | None = None
    specifications: list[str] | None = None
    status: str | None = None


async def _get_mission(mission_id: str, user: dict) -> dict:
    m = await get_db().missions.find_one(
        {"id": mission_id, "organization_id": user["organization_id"]}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Mission not found")
    return m


@missions.post("/extract")
async def extract(body: ExtractBody, user: dict = Depends(get_current_user)):
    if not ai_service.is_configured():
        raise HTTPException(status_code=503, detail="AI service not configured")
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Provide a requirement description")
    result = await ai_service.extract_requirement(body.text, f"extract-{user['id']}")
    return result


@missions.post("")
async def create_mission(body: MissionCreate, user: dict = Depends(get_current_user)):
    await entitlements.check_mission_quota(user)
    db = get_db()
    mission = body.model_dump()
    mission.update({
        "id": uuid.uuid4().hex,
        "organization_id": user["organization_id"],
        "created_by": user["id"],
        "title": body.title or (body.category and f"{body.quantity or ''} {body.category}".strip()) or "Untitled Mission",
        "status": "REQUIREMENT_REVIEW",
        "approval_threshold": body.budget,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    })
    await db.missions.insert_one(mission)
    await orchestrator.log_action(mission["id"], "Requirement Agent", "Mission created",
                                  mission["title"])
    await audit.log_event(user["organization_id"], "mission_created", actor=user.get("name"),
                          mission_id=mission["id"], detail=mission["title"])
    mission.pop("_id", None)
    return mission


@missions.get("")
async def list_missions(user: dict = Depends(get_current_user)):
    docs = await get_db().missions.find(
        {"organization_id": user["organization_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return docs


@missions.get("/{mission_id}")
async def get_mission(mission_id: str, user: dict = Depends(get_current_user)):
    return await _get_mission(mission_id, user)


@missions.patch("/{mission_id}")
async def update_mission(mission_id: str, body: MissionUpdate, user: dict = Depends(get_current_user)):
    await _get_mission(mission_id, user)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if "status" in updates and updates["status"] not in MISSION_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    updates["updated_at"] = now_iso()
    await get_db().missions.update_one({"id": mission_id}, {"$set": updates})
    return await _get_mission(mission_id, user)


@missions.delete("/{mission_id}")
async def delete_mission(mission_id: str, user: dict = Depends(get_current_user)):
    await _get_mission(mission_id, user)
    db = get_db()
    await db.missions.delete_one({"id": mission_id})
    for coll in ["vendors", "offers", "negotiations", "agent_actions", "approvals"]:
        await db[coll].delete_many({"mission_id": mission_id})
    return {"ok": True}


@missions.post("/{mission_id}/discover")
async def discover(mission_id: str, background: BackgroundTasks, user: dict = Depends(get_current_user)):
    await _get_mission(mission_id, user)
    background.add_task(orchestrator.run_discovery_pipeline, mission_id)
    return {"ok": True, "message": "Discovery started"}


@missions.get("/{mission_id}/vendors")
async def mission_vendors(mission_id: str, user: dict = Depends(get_current_user)):
    await _get_mission(mission_id, user)
    docs = await get_db().vendors.find({"mission_id": mission_id}, {"_id": 0}) \
        .sort("weighted_score", -1).to_list(50)
    for v in docs:
        mem = await vendor_memory.get_memory(user["organization_id"], v.get("domain"))
        if mem and mem.get("missions") and mission_id not in mem["missions"]:
            v["memory"] = {"negotiations_count": mem.get("negotiations_count"),
                           "best_price": mem.get("best_price"),
                           "last_price": mem.get("last_price")}
    return docs


@missions.get("/{mission_id}/activity")
async def mission_activity(mission_id: str, user: dict = Depends(get_current_user)):
    await _get_mission(mission_id, user)
    docs = await get_db().agent_actions.find({"mission_id": mission_id}, {"_id": 0}) \
        .sort("created_at", -1).to_list(100)
    return docs


# ---------------- NEGOTIATION (AI, simulated vendor preview) ----------------
class NegotiateBody(BaseModel):
    rounds: int = 3


@missions.post("/{mission_id}/vendors/{vendor_id}/negotiate")
async def negotiate(mission_id: str, vendor_id: str, body: NegotiateBody,
                    user: dict = Depends(get_current_user)):
    if not ai_service.is_configured():
        raise HTTPException(status_code=503, detail="AI service not configured")
    mission = await _get_mission(mission_id, user)
    db = get_db()
    vendor = await db.vendors.find_one({"id": vendor_id, "mission_id": mission_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    qty = mission.get("quantity") or 1
    budget = mission.get("budget") or 0
    max_price = round(budget / qty, 2) if (budget and qty) else None
    constraints = {
        "max_price": max_price,
        "target_price": round(max_price * 0.9, 2) if max_price else None,
        "min_warranty": mission.get("warranty_requirements"),
        "max_delivery_days": mission.get("deadline_days"),
    }
    mem = await vendor_memory.get_memory(user["organization_id"], vendor.get("domain"))
    constraints["memory_note"] = vendor_memory.memory_note(mem)
    session = f"nego-{mission_id}-{vendor_id}"
    history = []
    events = []
    final = {"price": None, "delivery_days": None, "warranty": None}

    await orchestrator.set_status(mission_id, "NEGOTIATING")
    rounds = max(1, min(body.rounds, 5))
    for i in range(rounds):
        buyer = await ai_service.negotiation_turn(mission, vendor, constraints, history, session)
        history.append({"role": "buyer_ai", "text": buyer.get("message", "")})
        events.append({"role": "buyer_ai", "text": buyer.get("message", ""),
                       "within_authority": buyer.get("within_authority", True),
                       "target_price": buyer.get("target_price"), "at": now_iso()})
        vend = await ai_service.simulated_vendor_turn(mission, vendor, history, session)
        history.append({"role": "vendor", "text": vend.get("message", "")})
        events.append({"role": "vendor", "text": vend.get("message", ""),
                       "offered_price": vend.get("offered_price_per_unit"),
                       "delivery_days": vend.get("delivery_days"),
                       "warranty": vend.get("warranty"), "at": now_iso()})
        if vend.get("offered_price_per_unit"):
            final["price"] = vend["offered_price_per_unit"]
        if vend.get("delivery_days"):
            final["delivery_days"] = vend["delivery_days"]
        if vend.get("warranty"):
            final["warranty"] = vend["warranty"]
        if not vend.get("willing_to_continue", True):
            break

    negotiation = {
        "id": uuid.uuid4().hex, "mission_id": mission_id, "vendor_id": vendor_id,
        "vendor_name": vendor["name"], "organization_id": user["organization_id"],
        "mode": "AI_SIMULATION_PREVIEW",
        "simulation": True,
        "constraints": constraints, "events": events,
        "final_price": final["price"], "final_delivery_days": final["delivery_days"],
        "final_warranty": final["warranty"], "status": "COMPLETED",
        "created_at": now_iso(),
    }
    await db.negotiations.insert_one(negotiation)
    await orchestrator.log_action(
        mission_id, "Negotiation Agent",
        f"Negotiation preview with {vendor['name']}",
        f"[SIMULATION] Reached indicative price {final['price']} per unit over {rounds} rounds")
    negotiation.pop("_id", None)

    # Create/refresh an offer from the negotiated indicative terms.
    if final["price"]:
        offer = {
            "id": uuid.uuid4().hex, "mission_id": mission_id, "vendor_id": vendor_id,
            "vendor_name": vendor["name"], "organization_id": user["organization_id"],
            "original_price": final["price"], "negotiated_price": final["price"],
            "quantity": qty, "taxes": None, "shipping": None, "fees": None,
            "currency": mission.get("currency"),
            "delivery_time": f"{final['delivery_days']} days" if final["delivery_days"] else None,
            "warranty": final["warranty"], "payment_terms": None,
            "reliability_score": vendor.get("reliability_score"),
            "source": "ai_negotiation_preview", "simulation": True,
            "status": "OPEN", "created_at": now_iso(),
        }
        await db.offers.delete_many({"mission_id": mission_id, "vendor_id": vendor_id})
        await db.offers.insert_one(offer)
        await vendor_memory.record_outcome(user["organization_id"], vendor, mission_id,
                                            final["price"], source="negotiation_preview")
    return negotiation


@missions.get("/{mission_id}/negotiations")
async def list_negotiations(mission_id: str, user: dict = Depends(get_current_user)):
    await _get_mission(mission_id, user)
    docs = await get_db().negotiations.find({"mission_id": mission_id}, {"_id": 0}) \
        .sort("created_at", -1).to_list(50)
    return docs


# ---------------- OFFERS ----------------
class OfferBody(BaseModel):
    vendor_id: str
    negotiated_price: float
    quantity: int | None = None
    taxes: float | None = None
    shipping: float | None = None
    fees: float | None = None
    delivery_time: str | None = None
    warranty: str | None = None
    payment_terms: str | None = None


@missions.get("/{mission_id}/offers")
async def list_offers(mission_id: str, user: dict = Depends(get_current_user)):
    await _get_mission(mission_id, user)
    docs = await get_db().offers.find({"mission_id": mission_id}, {"_id": 0}).to_list(50)
    for o in docs:
        o["landed"] = compute_landed_cost(o, o.get("quantity"))
    return docs


@missions.post("/{mission_id}/offers")
async def add_offer(mission_id: str, body: OfferBody, user: dict = Depends(get_current_user)):
    mission = await _get_mission(mission_id, user)
    db = get_db()
    vendor = await db.vendors.find_one({"id": body.vendor_id, "mission_id": mission_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    offer = body.model_dump()
    offer.update({
        "id": uuid.uuid4().hex, "mission_id": mission_id, "vendor_id": body.vendor_id,
        "vendor_name": vendor["name"], "organization_id": user["organization_id"],
        "original_price": body.negotiated_price,
        "quantity": body.quantity or mission.get("quantity"),
        "currency": mission.get("currency"),
        "reliability_score": vendor.get("reliability_score"),
        "source": "manual", "simulation": False, "status": "OPEN", "created_at": now_iso(),
    })
    await db.offers.insert_one(offer)
    offer.pop("_id", None)
    offer["landed"] = compute_landed_cost(offer, offer["quantity"])
    return offer


# ---------------- COMPARISON / RECOMMENDATION ----------------
@missions.post("/{mission_id}/compare")
async def compare(mission_id: str, user: dict = Depends(get_current_user)):
    mission = await _get_mission(mission_id, user)
    db = get_db()
    offers = await db.offers.find({"mission_id": mission_id}, {"_id": 0}).to_list(50)
    if not offers:
        raise HTTPException(status_code=400, detail="No offers to compare. Negotiate or add offers first.")
    for o in offers:
        landed = compute_landed_cost(o, o.get("quantity"))
        o["total_cost"] = landed["total_cost"]
        o["landed"] = landed

    recommendation = None
    if ai_service.is_configured():
        try:
            recommendation = await ai_service.recommend(mission, offers, f"compare-{mission_id}")
        except Exception:
            recommendation = None
    if not recommendation:
        best = min(offers, key=lambda o: o["total_cost"])
        recommendation = {"recommended_offer_id": best["id"], "recommendation_score": 60,
                          "reasoning": "Lowest total landed cost.", "risks": [], "ranking": []}

    result = {
        "id": uuid.uuid4().hex, "mission_id": mission_id, "offers": offers,
        "recommendation": recommendation, "created_at": now_iso(),
    }
    await db.comparisons.delete_many({"mission_id": mission_id})
    await db.comparisons.insert_one(dict(result))
    result.pop("_id", None)
    await orchestrator.set_status(mission_id, "AWAITING_APPROVAL")
    rec_offer = next((o for o in offers if o["id"] == recommendation.get("recommended_offer_id")), None)
    await orchestrator.log_action(
        mission_id, "Comparison Agent", "Comparison complete",
        f"Recommended {rec_offer['vendor_name'] if rec_offer else 'top offer'} "
        f"(landed {rec_offer['total_cost'] if rec_offer else '?'})")
    return result


@missions.get("/{mission_id}/comparison")
async def get_comparison(mission_id: str, user: dict = Depends(get_current_user)):
    await _get_mission(mission_id, user)
    doc = await get_db().comparisons.find_one({"mission_id": mission_id}, {"_id": 0})
    return doc  # null (200) when not yet computed


# ---------------- APPROVAL ----------------
class ApprovalBody(BaseModel):
    action: str  # APPROVE | REJECT | NEGOTIATE_FURTHER
    offer_id: str | None = None
    note: str | None = None


@missions.post("/{mission_id}/approve")
async def approve(mission_id: str, body: ApprovalBody, user: dict = Depends(get_current_user)):
    mission = await _get_mission(mission_id, user)
    db = get_db()
    action = body.action.upper()
    if action not in ["APPROVE", "REJECT", "NEGOTIATE_FURTHER"]:
        raise HTTPException(status_code=400, detail="Invalid action")

    approval = {
        "id": uuid.uuid4().hex, "mission_id": mission_id, "action": action,
        "offer_id": body.offer_id, "note": body.note, "approved_by": user["id"],
        "approver_name": user.get("name"), "created_at": now_iso(),
    }
    await db.approvals.insert_one(approval)

    if action == "APPROVE":
        offer = await db.offers.find_one({"id": body.offer_id, "mission_id": mission_id}, {"_id": 0})
        landed = compute_landed_cost(offer, offer.get("quantity")) if offer else {}
        await db.purchases.insert_one({
            "id": uuid.uuid4().hex, "mission_id": mission_id, "offer_id": body.offer_id,
            "vendor_id": offer.get("vendor_id") if offer else None,
            "vendor_name": offer.get("vendor_name") if offer else None,
            "total_cost": landed.get("total_cost"), "approved_by": user["id"],
            "status": "APPROVED", "created_at": now_iso(),
        })
        await orchestrator.set_status(mission_id, "APPROVED")
        await orchestrator.log_action(mission_id, "Approval Agent", "Purchase approved",
                                      f"Approved by {user.get('name')} — {offer.get('vendor_name') if offer else ''}")
        await audit.log_event(user["organization_id"], "human_approved", actor=user.get("name"),
                              mission_id=mission_id,
                              detail=f"Approved {offer.get('vendor_name') if offer else ''}")
    elif action == "REJECT":
        await orchestrator.set_status(mission_id, "REJECTED")
        await orchestrator.log_action(mission_id, "Approval Agent", "Rejected", body.note or "")
    else:
        await orchestrator.set_status(mission_id, "NEGOTIATING")
        await orchestrator.log_action(mission_id, "Approval Agent", "Sent back for negotiation",
                                      body.note or "")
    approval.pop("_id", None)
    return approval


# ============================ DASHBOARD ============================
dashboard = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@dashboard.get("/stats")
async def stats(user: dict = Depends(get_current_user)):
    db = get_db()
    org = user["organization_id"]
    all_missions = await db.missions.find({"organization_id": org}, {"_id": 0}).to_list(500)
    active = [m for m in all_missions if m["status"] not in
              ["COMPLETED", "CANCELLED", "REJECTED", "APPROVED"]]
    completed = [m for m in all_missions if m["status"] in ["APPROVED", "COMPLETED"]]
    negotiating = [m for m in all_missions if m["status"] == "NEGOTIATING"]
    awaiting = [m for m in all_missions if m["status"] == "AWAITING_APPROVAL"]
    vendors_count = await db.vendors.count_documents({"organization_id": org})

    # Estimated savings: sum(budget - landed) across compared missions, only positive.
    savings = 0.0
    purchases = await db.purchases.find({"mission_id": {"$in": [m["id"] for m in all_missions]}},
                                        {"_id": 0}).to_list(500)
    pmap = {p["mission_id"]: p for p in purchases}
    for m in all_missions:
        p = pmap.get(m["id"])
        if p and m.get("budget") and p.get("total_cost"):
            diff = m["budget"] - p["total_cost"]
            if diff > 0:
                savings += diff

    recent = await db.agent_actions.find({"mission_id": {"$in": [m["id"] for m in all_missions]}},
                                         {"_id": 0}).sort("created_at", -1).to_list(12)
    return {
        "active_missions": len(active),
        "completed_missions": len(completed),
        "vendors_discovered": vendors_count,
        "negotiations_active": len(negotiating),
        "pending_approvals": len(awaiting),
        "estimated_savings": round(savings, 2),
        "total_missions": len(all_missions),
        "recent_activity": recent,
        "missions": all_missions[:6],
    }


@dashboard.get("/analytics")
async def analytics(user: dict = Depends(get_current_user)):
    db = get_db()
    org = user["organization_id"]
    all_missions = await db.missions.find({"organization_id": org}, {"_id": 0}).to_list(1000)
    mids = [m["id"] for m in all_missions]
    purchases = await db.purchases.find({"mission_id": {"$in": mids}}, {"_id": 0}).to_list(1000)
    pmap = {p["mission_id"]: p for p in purchases}

    # Savings & spend over time (by month of mission creation), only for concluded purchases.
    buckets = {}
    by_category = {}
    for m in all_missions:
        month = (m.get("created_at") or "")[:7] or "unknown"
        b = buckets.setdefault(month, {"month": month, "savings": 0.0, "spend": 0.0, "missions": 0})
        b["missions"] += 1
        p = pmap.get(m["id"])
        if p and p.get("total_cost"):
            b["spend"] += p["total_cost"]
            cat = m.get("category") or "Other"
            by_category[cat] = round(by_category.get(cat, 0) + p["total_cost"], 2)
            if m.get("budget"):
                diff = m["budget"] - p["total_cost"]
                if diff > 0:
                    b["savings"] += diff
    series = sorted(buckets.values(), key=lambda x: x["month"])
    for s in series:
        s["savings"] = round(s["savings"], 2)
        s["spend"] = round(s["spend"], 2)

    mem = await vendor_memory.list_memory(org)
    top_vendors = [{"name": v.get("name"), "negotiations": v.get("negotiations_count"),
                    "best_price": v.get("best_price")} for v in mem[:6]]
    status_counts = {}
    for m in all_missions:
        status_counts[m["status"]] = status_counts.get(m["status"], 0) + 1

    return {
        "savings_over_time": series,
        "spend_by_category": [{"category": k, "spend": v} for k, v in by_category.items()],
        "top_vendors": top_vendors,
        "status_breakdown": [{"status": k.replace("_", " "), "count": v}
                             for k, v in status_counts.items()],
        "total_spend": round(sum(s["spend"] for s in series), 2),
        "total_savings": round(sum(s["savings"] for s in series), 2),
        "vendors_remembered": len(mem),
    }


vendors_r = APIRouter(prefix="/api/vendors", tags=["vendors"])


@vendors_r.get("/memory")
async def vendor_memory_list(user: dict = Depends(get_current_user)):
    return await vendor_memory.list_memory(user["organization_id"])


app.include_router(auth_router)
app.include_router(core)
app.include_router(missions)
app.include_router(dashboard)
app.include_router(vendors_r)
app.include_router(billing_router)
app.include_router(voice_router)
app.include_router(team_router)
app.include_router(reports_router)
app.include_router(outreach_router)
app.include_router(whatsapp_router)
app.include_router(whatsapp_status_router)
app.include_router(audit.router)
app.include_router(payments_router)
app.include_router(razorpay_webhook_router)
app.include_router(telephony_router)


@app.on_event("startup")
async def startup():
    await create_indexes()
    await seed_admin()
    register_realtime(app)
    print("[NegoBuy] startup complete")

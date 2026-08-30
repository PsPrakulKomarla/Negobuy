"""Master Procurement Orchestrator — derives the authoritative lifecycle stage from the
single mission state + related artifacts (no duplicate memory), reports what's happening,
what needs human approval, and which agent should act next. Read/derive only: it recommends;
humans and specialized agents act via their own endpoints."""
from fastapi import APIRouter, Depends
from db import get_db
from auth import get_current_user

router = APIRouter(prefix="/api/missions", tags=["orchestrator"])

LIFECYCLE = [
    "REQUIREMENT_CREATED", "VENDOR_DISCOVERY", "VENDOR_VERIFICATION", "SHORTLIST_READY",
    "NEGOTIATION", "OFFERS_COLLECTED", "OFFERS_COMPARED", "RECOMMENDATION_READY",
    "AWAITING_HUMAN_DECISION", "SUPPLIER_SELECTED", "CONTRACT_REVIEW",
    "AWAITING_CONTRACT_APPROVAL", "ORDER_AUTHORIZED", "ORDER_TRACKING",
    "DELIVERY_PENDING_VERIFICATION", "COMPLETED",
]


def _act(action, endpoint, agent, requires_human=False):
    return {"action": action, "endpoint": endpoint, "agent": agent, "requires_human": requires_human}


@router.get("/{mission_id}/orchestrator")
async def orchestrate(mission_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    mission = await db.missions.find_one(
        {"id": mission_id, "organization_id": user["organization_id"]}, {"_id": 0})
    if not mission:
        return {"error": "MISSION_NOT_FOUND"}
    org = user["organization_id"]
    base = f"/api/missions/{mission_id}"

    vcount = await db.vendors.count_documents({"mission_id": mission_id})
    offers = await db.offers.find({"mission_id": mission_id}, {"_id": 0}).to_list(50)
    comparison = await db.comparisons.find_one({"mission_id": mission_id}, {"_id": 0})
    contract = await db.contract_reviews.find_one(
        {"mission_id": mission_id}, {"_id": 0}, sort=[("created_at", -1)])
    order = await db.orders.find_one({"mission_id": mission_id}, {"_id": 0})
    ms = mission.get("status")

    human_required = False
    actions = []

    # Derive stage by precedence (post-order → back to requirement).
    if order:
        st = order.get("status")
        if st in ("DELIVERED_PENDING_VERIFICATION",):
            stage = "DELIVERY_PENDING_VERIFICATION"
            human_required = True
            summary = "Delivery reported. Human verification of quantity/condition is required."
            actions = [_act("verify_delivery", f"{base}/order/delivery", "Assurance Agent", True)]
        elif st in ("COMPLETED", "DELIVERY_VERIFIED"):
            stage = "COMPLETED"
            summary = "Order delivered and verified. Mission complete."
        else:
            stage = "ORDER_TRACKING"
            summary = f"Order is being tracked. Current order status: {st}."
            actions = [
                _act("update_order_status", f"{base}/order/status", "Assurance Agent"),
                _act("verify_invoice", f"{base}/order/invoice", "Assurance Agent", True),
                _act("mark_delivered", f"{base}/order/delivery", "Assurance Agent"),
            ]
            if order.get("status") == "PAYMENT_ACTION_REQUIRED":
                human_required = True
                summary = "Invoice discrepancy detected — human review required before payment."
    elif contract:
        rec = (contract.get("analysis") or {}).get("recommendation")
        stage = "AWAITING_CONTRACT_APPROVAL"
        human_required = True
        summary = f"Contract analyzed ({rec}). Human approval required before authorizing the order."
        actions = [
            _act("review_contract", f"{base}/contract", "Assurance Agent", True),
            _act("authorize_order", f"{base}/order/authorize", "Human Buyer", True),
        ]
    elif comparison and comparison.get("recommendation"):
        stage = "RECOMMENDATION_READY"
        human_required = True
        rec = comparison["recommendation"]
        summary = "Recommendation ready. A human must select the supplier before contract/order."
        actions = [
            _act("approve_supplier", f"{base}/approve", "Human Buyer", True),
            _act("analyze_contract", f"{base}/contract/analyze", "Assurance Agent"),
        ]
    elif len(offers) >= 2:
        stage = "OFFERS_COMPARED" if comparison else "OFFERS_COLLECTED"
        summary = (f"{len(offers)} offers collected. "
                   + ("Comparison ready — generate a recommendation."
                      if comparison else "Run comparison to rank offers."))
        actions = [_act("compare_offers", f"{base}/compare", "Analysis Agent")]
    elif len(offers) == 1:
        stage = "OFFERS_COLLECTED"
        summary = "One offer collected. Negotiate further or collect more offers, then compare."
        actions = [
            _act("negotiate", f"{base}/vendors/{{vendor_id}}/negotiation/message", "Negotiation Agent"),
            _act("compare_offers", f"{base}/compare", "Analysis Agent"),
        ]
    elif vcount > 0:
        stage = "SHORTLIST_READY"
        summary = f"{vcount} suppliers shortlisted. Begin negotiation to collect offers."
        actions = [
            _act("negotiate", f"{base}/vendors/{{vendor_id}}/negotiation/message", "Negotiation Agent"),
            _act("email_outreach", f"{base}/vendors/{{vendor_id}}/outreach/compose", "Negotiation Agent"),
            _act("call_vendor", "/api/voice/exotel/call", "Negotiation Agent"),
        ]
    elif ms in ("DRAFT",) or not mission.get("ready_for_discovery", True):
        stage = "REQUIREMENT_CREATED"
        summary = "Requirement captured. Verify details, then start supplier discovery."
        actions = [_act("discover_vendors", f"{base}/discover", "Discovery Agent")]
    else:
        stage = "VENDOR_DISCOVERY"
        summary = "Ready to discover suppliers for this requirement."
        actions = [_act("discover_vendors", f"{base}/discover", "Discovery Agent")]

    next_agent = actions[0]["agent"] if actions else "Human Buyer"

    timeline = await db.audit_logs.find(
        {"organization_id": org, "mission_id": mission_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(20)

    return {
        "mission_id": mission_id,
        "mission_status": ms,
        "stage": stage,
        "lifecycle": LIFECYCLE,
        "stage_index": LIFECYCLE.index(stage) if stage in LIFECYCLE else None,
        "status_summary": summary,
        "human_action_required": human_required,
        "next_agent": next_agent,
        "available_actions": actions,
        "counts": {"vendors": vcount, "offers": len(offers)},
        "order": {"exists": bool(order), "status": (order or {}).get("status")},
        "contract_reviewed": bool(contract),
        "timeline": timeline,
        "authority": {
            "budget": mission.get("budget"), "currency": mission.get("currency"),
            "quantity": mission.get("quantity"),
            "max_unit_price": (round(mission["budget"] / mission["quantity"], 2)
                               if mission.get("budget") and mission.get("quantity") else None),
        },
        "principle": "AI analyzes, negotiates, recommends, tracks and alerts. Humans approve all material decisions.",
    }

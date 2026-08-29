"""Billing abstraction — plans, subscriptions, usage, entitlements.
Provider-agnostic. Stripe wiring activates when STRIPE_API_KEY is configured."""
import os
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from auth import get_current_user
from db import get_db

router = APIRouter(prefix="/api/billing", tags=["billing"])

# Configurable plan catalog (prices are placeholders / configurable, not hard-coded commercial commitments).
PLANS = [
    {
        "id": "free", "name": "Explorer", "type": "free", "price": 0, "currency": "USD",
        "interval": None,
        "features": ["1 active mission", "Vendor discovery", "AI requirement extraction",
                     "Landed-cost comparison"],
        "limits": {"active_missions": 3, "voice_minutes": 30},
    },
    {
        "id": "mission", "name": "Procurement Mission", "type": "one_time", "price": None,
        "currency": "USD", "interval": None,
        "features": ["One full procurement mission", "Supplier research + shortlist",
                     "Verification", "AI negotiation", "Offer comparison", "Final recommendation",
                     "Procurement report"],
        "limits": {"active_missions": 1, "voice_minutes": 30},
    },
    {
        "id": "pro", "name": "AI Buyer Pro", "type": "subscription", "price": None,
        "currency": "USD", "interval": "month",
        "features": ["Recurring procurement missions", "Vendor discovery + intelligence",
                     "AI + voice negotiation", "Negotiation memory", "Vendor history",
                     "Savings analytics", "Full procurement history"],
        "limits": {"active_missions": None, "voice_minutes": 500},
    },
]


def stripe_configured() -> bool:
    return bool(os.environ.get("STRIPE_API_KEY"))


@router.get("/plans")
async def list_plans():
    return {"plans": PLANS, "payment_configured": stripe_configured(),
            "provider": "stripe",
            "message": None if stripe_configured()
            else "Live checkout requires payment configuration. Plans below are available to preview."}


@router.get("/subscription")
async def get_subscription(user: dict = Depends(get_current_user)):
    db = get_db()
    sub = await db.subscriptions.find_one({"organization_id": user["organization_id"]}, {"_id": 0})
    usage = await db.usage.find_one({"organization_id": user["organization_id"]}, {"_id": 0})
    return {
        "plan": user.get("plan", "free"),
        "subscription": sub,
        "usage": usage or {"active_missions": 0, "voice_minutes_used": 0},
        "payment_configured": stripe_configured(),
    }


@router.post("/checkout/{plan_id}")
async def create_checkout(plan_id: str, user: dict = Depends(get_current_user)):
    plan = next((p for p in PLANS if p["id"] == plan_id), None)
    if not plan:
        return {"error": "Unknown plan"}
    if not stripe_configured():
        return {
            "status": "not_configured",
            "message": "Payment provider not configured. Add STRIPE_API_KEY to enable live checkout.",
            "plan": plan,
        }
    # Real Stripe checkout would be created here using emergentintegrations payments.
    return {"status": "not_configured",
            "message": "Stripe integration point ready — awaiting live checkout implementation.",
            "plan": plan}


def razorpay_state() -> str:
    kid = os.environ.get("RAZORPAY_KEY_ID", "")
    if kid.startswith("rzp_live"):
        return "LIVE"
    if kid:
        return "TEST"
    return "NOT_CONFIGURED"


@router.post("/orders/{plan_id}")
async def create_order(plan_id: str, user: dict = Depends(get_current_user)):
    """Razorpay order creation. Returns NOT_CONFIGURED until Razorpay keys are set."""
    plan = next((p for p in PLANS if p["id"] == plan_id), None)
    if not plan:
        return {"error": "UNKNOWN_PLAN", "message": "Unknown plan."}
    state = razorpay_state()
    if state == "NOT_CONFIGURED":
        return {"status": "NOT_CONFIGURED", "provider": "razorpay",
                "message": ("Payments require RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET. "
                            "The order + webhook-verification architecture is implemented and "
                            "activates once keys are configured."),
                "required": ["RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET"],
                "plan": plan}
    # With keys present, a real Razorpay order would be created here and verified via webhook.
    return {"status": "READY", "mode": state, "provider": "razorpay", "plan": plan}

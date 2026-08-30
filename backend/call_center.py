"""NegoBuy Live AI Voice Negotiation — Call Center.

Reuses the EXISTING pieces (does NOT rebuild them):
  - exotel_service.place_outbound_call / config/live status  (telephony provider)
  - ai_service negotiation persona + engine_turn + simulated_vendor_turn (ONE shared brain)
  - ai_service.analyze_call (post-call analysis)
  - negotiation_engine thread linkage (org -> mission -> supplier -> thread)
  - audit.log_event (unified honest event stream)

Adds the missing lifecycle: Call Test Console -> explicit approval -> real/test call ->
recording state machine -> timestamped transcript -> post-call analysis + AI self-review ->
human approval gate -> per-mission call history.

Safety invariants (enforced in code):
  - No call is ever placed without an explicit approve step.
  - Authority (target/max price) is frozen at approval, backend is the source of truth,
    and can never be mutated by a webhook or by the voice agent.
  - Nothing here creates an offer/order/purchase/approval automatically.
  - We never claim a recording/transcript exists unless the provider actually delivered it.
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
import exotel_service
import vendor_memory
import negotiation_engine

log = logging.getLogger("call_center")
router = APIRouter(prefix="/api/voice/console", tags=["call-center"])

RECORDING_STATES = ["RECORDING_REQUESTED", "RECORDING_ACTIVE", "RECORDING_AVAILABLE",
                    "RECORDING_FAILED", "RECORDING_NOT_SUPPORTED"]
TERMINAL_STATUSES = {"completed", "failed", "no-answer", "busy", "canceled",
                     "SIMULATED_COMPLETE", "NOT_CONFIGURED"}
LIVE_CHANNEL = "exotel"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _mmss(seconds: float) -> str:
    seconds = int(seconds or 0)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _authority_from_objective(obj: dict) -> dict:
    """Authority is derived and frozen backend-side — never trusted from a webhook."""
    qty = obj.get("quantity") or 1
    return {
        "currency": obj.get("currency") or "INR",
        "target_price_per_unit": obj.get("target_price"),
        "max_price_per_unit": obj.get("max_authorized_price"),
        "quantity": qty,
        "max_delivery_days": obj.get("delivery_deadline_days"),
        "min_warranty": obj.get("warranty_requirements"),
    }


def _not_authorized(authority: dict) -> list:
    cur = authority.get("currency") or ""
    mx = authority.get("max_price_per_unit")
    return [
        f"Agree to any price above the maximum authorized {cur} {mx}/unit" if mx
        else "Agree to a price above the buyer's authorized maximum",
        "Change the quantity without buyer authorization",
        "Accept different specifications without buyer authorization",
        "Accept payment terms outside the approved preferences",
        "Make any legally binding commitment or sign a contract",
        "Finalize, confirm or place an order without human approval",
    ]


def _disclosure_script(obj: dict, disclose_ai: bool, recording_notice: bool) -> str:
    if not disclose_ai:
        return ""
    line = ("Hi, I'm NegoBuy's AI procurement assistant, calling on behalf of a buyer who is "
            f"interested in discussing {('the purchase of ' + obj.get('product')) if obj.get('product') else 'a purchase'}. "
            "Is this a good time to talk?")
    if recording_notice:
        line += " Please note this call may be recorded for quality and record-keeping."
    return line


async def _get_mission_vendor(db, mission_id, vendor_id, user):
    mission = await db.missions.find_one(
        {"id": mission_id, "organization_id": user["organization_id"]}, {"_id": 0})
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    vendor = await db.vendors.find_one({"id": vendor_id, "mission_id": mission_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return mission, vendor


async def _owned_call(db, ref, user):
    doc = await db.voice_calls.find_one(
        {"session_ref": ref, "organization_id": user["organization_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Call not found")
    return doc


def _check_webhook_token(params: dict):
    expected = os.environ.get("EXOTEL_WEBHOOK_TOKEN")
    if expected and params.get("token") != expected:
        raise HTTPException(status_code=401, detail="Invalid webhook token")
    if not expected and exotel_service.is_configured():
        raise HTTPException(status_code=401, detail="Webhook secret not configured")


async def _merged_params(request: Request) -> dict:
    params = {}
    try:
        form = await request.form()
        params.update({k: str(v) for k, v in form.items()})
    except Exception:
        pass
    params.update({k: v for k, v in request.query_params.items()})
    return params


# --------------------------------------------------------------------------- #
# 1. CALL TEST CONSOLE — create a configuration (NO call is placed here)
# --------------------------------------------------------------------------- #
class CallConfigBody(BaseModel):
    mission_id: str
    vendor_id: str
    to_number: str
    supplier_name: str | None = None
    product: str | None = None
    quantity: int | None = None
    current_price: float | None = None
    target_price: float | None = None
    max_authorized_price: float | None = None
    delivery_location: str | None = None
    delivery_deadline_days: int | None = None
    warranty_requirements: str | None = None
    payment_preferences: str | None = None
    negotiation_priorities: list[str] = []
    special_instructions: str | None = None
    currency: str | None = None
    test_mode: bool = True
    disclose_ai: bool = True
    recording_notice: bool = True


@router.post("/config")
async def create_config(body: CallConfigBody, user: dict = Depends(get_current_user)):
    db = get_db()
    mission, vendor = await _get_mission_vendor(db, body.mission_id, body.vendor_id, user)
    to_number = exotel_service._normalize_number(body.to_number)
    if not to_number:
        raise HTTPException(status_code=400, detail="A destination phone number is required")

    objective = {
        "supplier_name": body.supplier_name or vendor.get("name"),
        "product": body.product or mission.get("title"),
        "quantity": body.quantity or mission.get("quantity"),
        "current_price": body.current_price,
        "target_price": body.target_price,
        "max_authorized_price": body.max_authorized_price,
        "delivery_location": body.delivery_location or mission.get("delivery_location"),
        "delivery_deadline_days": body.delivery_deadline_days or mission.get("deadline_days"),
        "warranty_requirements": body.warranty_requirements or mission.get("warranty_requirements"),
        "payment_preferences": body.payment_preferences or mission.get("payment_requirements"),
        "negotiation_priorities": body.negotiation_priorities,
        "special_instructions": body.special_instructions,
        "currency": body.currency or mission.get("currency") or "INR",
    }
    authority = _authority_from_objective(objective)
    # Authority sanity: never freeze inverted or negative limits.
    tp, mx = objective.get("target_price"), objective.get("max_authorized_price")
    for v in (tp, mx, objective.get("current_price")):
        if v is not None and v < 0:
            raise HTTPException(status_code=400, detail="Prices cannot be negative")
    if tp is not None and mx is not None and float(tp) > float(mx):
        raise HTTPException(status_code=400,
                            detail="Target price cannot exceed the maximum authorized price")
    session_ref = uuid.uuid4().hex
    provider_status = await exotel_service.live_status()

    doc = {
        "id": uuid.uuid4().hex, "session_ref": session_ref, "provider": "exotel",
        "organization_id": user["organization_id"],
        "mission_id": body.mission_id, "mission_title": mission.get("title"),
        "vendor_id": body.vendor_id, "vendor_name": vendor.get("name"),
        "to": to_number,
        "objective": objective, "authority": authority,
        "not_authorized": _not_authorized(authority),
        "test_mode": body.test_mode,
        "disclose_ai": body.disclose_ai, "recording_notice": body.recording_notice,
        "disclosure_script": _disclosure_script(objective, body.disclose_ai, body.recording_notice),
        "status": "CONFIGURED", "approved": False, "approval": None,
        "call_sid": None,
        "recording": {"state": "RECORDING_REQUESTED" if body.recording_notice
                      else "RECORDING_NOT_SUPPORTED", "url": None},
        "transcript": [], "transcript_status": "PENDING",
        "analysis": None, "outcome": None,
        "duration": None, "provider_ready": provider_status.get("state"),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.voice_calls.insert_one(dict(doc))
    await audit.log_event(user["organization_id"], "call_configured", mission_id=body.mission_id,
                          actor=user.get("name"),
                          detail=f"Call to {objective['supplier_name']} configured "
                                 f"({'TEST' if body.test_mode else 'LIVE'}) — awaiting approval")
    doc.pop("_id", None)
    return doc


@router.get("/config/{ref}")
async def get_config(ref: str, user: dict = Depends(get_current_user)):
    return await _owned_call(get_db(), ref, user)


@router.get("/session/{ref}")
async def get_session(ref: str, user: dict = Depends(get_current_user)):
    return await _owned_call(get_db(), ref, user)


@router.get("/history")
async def call_history(mission_id: str | None = None, user: dict = Depends(get_current_user)):
    q = {"organization_id": user["organization_id"]}
    if mission_id:
        q["mission_id"] = mission_id
    docs = await get_db().voice_calls.find(q, {"_id": 0, "transcript": 0}).sort(
        "created_at", -1).to_list(100)
    for d in docs:
        an = d.get("analysis") or {}
        d["key_outcome"] = an.get("summary")
        d["recording_state"] = (d.get("recording") or {}).get("state")
    return docs


# --------------------------------------------------------------------------- #
# 2. EXPLICIT APPROVAL — the ONLY place a call is initiated
# --------------------------------------------------------------------------- #
@router.post("/approve/{ref}")
async def approve_and_place(ref: str, user: dict = Depends(get_current_user)):
    db = get_db()
    doc = await _owned_call(db, ref, user)
    if doc["status"] != "CONFIGURED":
        raise HTTPException(status_code=400, detail=f"Call already {doc['status']}")

    approval = {"approved_by": user.get("name"), "approved_by_id": user["id"],
                "approved_at": _now()}
    await audit.log_event(user["organization_id"], "call_approved", mission_id=doc["mission_id"],
                          actor=user.get("name"),
                          detail=f"Approved AI negotiation call to {doc['objective']['supplier_name']} "
                                 f"at {doc['to']}")

    # ---- TEST MODE: simulate a full two-way conversation through the shared brain ----
    if doc.get("test_mode"):
        await db.voice_calls.update_one({"session_ref": ref}, {"$set": {
            "approved": True, "approval": approval, "status": "SIMULATING",
            "channel": "simulation", "recording": {"state": "RECORDING_NOT_SUPPORTED", "url": None},
            "started_at": _now(), "updated_at": _now()}})
        result = await _run_simulation(db, ref)
        return result

    # ---- LIVE MODE: reuse the existing Exotel provider abstraction ----
    provider = await exotel_service.live_status()
    if provider.get("state") != "READY":
        await db.voice_calls.update_one({"session_ref": ref}, {"$set": {
            "approved": True, "approval": approval, "status": "NOT_CONFIGURED",
            "provider_ready": provider.get("state"),
            "provider_message": provider.get("message"), "updated_at": _now()}})
        return {"status": "NOT_CONFIGURED", "provider": provider,
                "message": provider.get("message"), "session_ref": ref}

    base = os.environ.get("PUBLIC_BASE_URL", "")
    tok = os.environ.get("EXOTEL_WEBHOOK_TOKEN", "")
    status_cb = f"{base}/api/voice/console/status-callback?token={tok}"
    record = bool(doc.get("recording_notice"))
    result = await exotel_service.place_outbound_call(
        doc["to"], status_cb, custom_field=ref, record=record)

    status = "calling" if result.get("ok") else "failed"
    rec_state = ("RECORDING_REQUESTED" if record else "RECORDING_NOT_SUPPORTED")
    await db.voice_calls.update_one({"session_ref": ref}, {"$set": {
        "approved": True, "approval": approval, "status": status,
        "channel": LIVE_CHANNEL, "call_sid": result.get("provider_call_sid"),
        "recording": {"state": rec_state, "url": None},
        "started_at": _now(), "updated_at": _now(),
        "live_bridge": "REQUIRES_EXOTEL_STREAMING_APPLET"}})
    await audit.log_event(user["organization_id"], "call_started", mission_id=doc["mission_id"],
                          actor=user.get("name"),
                          detail=f"Exotel call to {doc['objective']['supplier_name']} — {status}")
    return {"status": status, "provider": "exotel", "session_ref": ref,
            "provider_call_sid": result.get("provider_call_sid"),
            "accepted": result.get("ok"), "http_status": result.get("status_code"),
            "note": ("The call is being placed. For the AI to hold a live two-way spoken "
                     "conversation, an Exotel App-Bazaar Voicebot/streaming applet must point "
                     "its Passthru at /api/voice/console/voice-start and stream audio to the "
                     "bridge. Until then the call connects but in-call AI speech is not active.")}


# --------------------------------------------------------------------------- #
# Simulation (TEST MODE) — drives the SAME negotiation brain end-to-end.
# Clearly labelled as SIMULATED; produces transcript + analysis for review.
# --------------------------------------------------------------------------- #
async def _run_simulation(db, ref: str, rounds: int = 4):
    doc = await db.voice_calls.find_one({"session_ref": ref}, {"_id": 0})
    mission = await db.missions.find_one({"id": doc["mission_id"]}, {"_id": 0}) or {}
    vendor = await db.vendors.find_one({"id": doc["vendor_id"]}, {"_id": 0}) or \
        {"name": doc["vendor_name"]}
    authority = doc["authority"]
    obj = doc["objective"]
    constraints = {"max_price": authority.get("max_price_per_unit"),
                   "target_price": authority.get("target_price_per_unit"),
                   "min_warranty": authority.get("min_warranty"),
                   "max_delivery_days": authority.get("max_delivery_days")}
    mem = await vendor_memory.get_memory(doc["organization_id"], vendor.get("domain"))
    constraints["memory_note"] = vendor_memory.memory_note(mem)
    session_id = f"call-sim-{ref}"

    transcript = []
    t = 0

    def stamp(secs):
        return _mmss(secs)

    # System event + AI disclosure (transparency rule)
    transcript.append({"id": uuid.uuid4().hex, "timestamp": stamp(0), "speaker": "SYSTEM",
                       "text": "Call connected (SIMULATED test call).", "confidence": None})
    if doc.get("disclosure_script"):
        t += 4
        transcript.append({"id": uuid.uuid4().hex, "timestamp": stamp(t), "speaker": "AI",
                           "text": doc["disclosure_script"], "confidence": 0.99})

    history = [{"role": "buyer_ai", "text": doc.get("disclosure_script", "")}] \
        if doc.get("disclosure_script") else []
    supplier_msg = "Yes, this is a good time. What are you looking for?"
    for i in range(rounds):
        t += 6
        transcript.append({"id": uuid.uuid4().hex, "timestamp": stamp(t), "speaker": "SUPPLIER",
                           "text": supplier_msg, "confidence": 0.92})
        history.append({"role": "supplier", "text": supplier_msg})
        turn = await ai_service.engine_turn(
            mission, vendor, constraints, "NEGOTIATE", {}, history, supplier_msg, session_id)
        ai_reply = turn.get("reply", "")
        t += 5
        transcript.append({"id": uuid.uuid4().hex, "timestamp": stamp(t), "speaker": "AI",
                           "text": ai_reply, "confidence": 0.98})
        history.append({"role": "buyer_ai", "text": ai_reply})
        vend = await ai_service.simulated_vendor_turn(mission, vendor, history, session_id)
        supplier_msg = vend.get("message", "Let me see what I can do.")
        if not vend.get("willing_to_continue", True):
            t += 6
            transcript.append({"id": uuid.uuid4().hex, "timestamp": stamp(t),
                               "speaker": "SUPPLIER", "text": supplier_msg, "confidence": 0.9})
            break
    t += 5
    transcript.append({"id": uuid.uuid4().hex, "timestamp": stamp(t), "speaker": "SYSTEM",
                       "text": "Call ended (SIMULATED).", "confidence": None})

    analysis = await ai_service.analyze_call(obj, authority, transcript, f"call-an-{ref}")
    await db.voice_calls.update_one({"session_ref": ref}, {"$set": {
        "status": "SIMULATED_COMPLETE", "channel": "simulation", "simulation": True,
        "transcript": transcript, "transcript_status": "AVAILABLE",
        "duration": t, "analysis": analysis, "ended_at": _now(), "updated_at": _now()}})
    await _persist_offer_from_analysis(db, ref, analysis)
    await _link_thread_event(db, doc, analysis, simulated=True)
    await audit.log_event(doc["organization_id"], "call_ended", mission_id=doc["mission_id"],
                          detail=f"[SIMULATION] Call with {obj['supplier_name']} complete — "
                                 f"{analysis.get('summary', '')[:120]}")
    return await db.voice_calls.find_one({"session_ref": ref}, {"_id": 0})


async def _link_thread_event(db, doc, analysis, simulated=False):
    """Append a phone-call summary into the SHARED (mission,vendor) negotiation thread
    so a later WhatsApp continuation has the call context (unified memory)."""
    try:
        thread = await negotiation_engine.get_thread(
            db, doc["mission_id"], doc["vendor_id"], doc["organization_id"], doc["vendor_name"])
        events = thread.get("events", [])
        events.append({"id": uuid.uuid4().hex, "role": "system", "channel": "phone",
                       "text": f"Phone call ({'simulated' if simulated else 'live'}) completed. "
                               f"{(analysis or {}).get('summary', '')}", "at": _now()})
        await db.negotiation_threads.update_one(
            {"mission_id": doc["mission_id"], "vendor_id": doc["vendor_id"]},
            {"$set": {"events": events, "updated_at": _now()}})
    except Exception as e:
        log.error("thread link failed: %s", type(e).__name__)


async def _persist_offer_from_analysis(db, ref: str, analysis: dict):
    """Mirror the discussed price into offers for comparison — flagged, NEVER a purchase."""
    doc = await db.voice_calls.find_one({"session_ref": ref}, {"_id": 0})
    price = (analysis.get("price") or {}).get("final_discussed") \
        or (analysis.get("proposed_supplier_terms") or {}).get("unit_price")
    if price in (None, ""):
        return
    authority = doc["authority"]
    mx = authority.get("max_price_per_unit")
    within = True
    try:
        if mx is not None and float(price) > float(mx):
            within = False
    except Exception:
        pass
    pt = analysis.get("proposed_supplier_terms") or {}
    offer = {
        "id": uuid.uuid4().hex, "mission_id": doc["mission_id"], "vendor_id": doc["vendor_id"],
        "vendor_name": doc["vendor_name"], "organization_id": doc["organization_id"],
        "original_price": (analysis.get("price") or {}).get("original") or price,
        "negotiated_price": price, "quantity": authority.get("quantity") or 1,
        "currency": authority.get("currency"),
        "delivery_time": (f"{pt.get('delivery_days')} days" if pt.get("delivery_days") else None),
        "warranty": pt.get("warranty"), "payment_terms": pt.get("payment_terms"),
        "taxes": None, "shipping": None, "fees": None,
        "source": "voice_call", "channel": doc.get("channel"),
        "simulation": bool(doc.get("simulation")),
        "within_authority": within, "status": "OPEN" if within else "OUT_OF_AUTHORITY",
        "max_authorized_price": mx, "call_ref": ref, "created_at": _now(),
    }
    await db.offers.delete_many({"mission_id": doc["mission_id"], "vendor_id": doc["vendor_id"],
                                 "source": "voice_call"})
    await db.offers.insert_one(offer)


# --------------------------------------------------------------------------- #
# 3. Re-run analysis on demand (e.g. after a live call captured a transcript)
# --------------------------------------------------------------------------- #
@router.post("/analyze/{ref}")
async def analyze(ref: str, user: dict = Depends(get_current_user)):
    db = get_db()
    doc = await _owned_call(db, ref, user)
    transcript = doc.get("transcript") or []
    if not transcript:
        raise HTTPException(status_code=400, detail="No transcript available to analyze")
    analysis = await ai_service.analyze_call(doc["objective"], doc["authority"], transcript,
                                             f"call-an-{ref}")
    await db.voice_calls.update_one({"session_ref": ref},
                                    {"$set": {"analysis": analysis, "updated_at": _now()}})
    await _persist_offer_from_analysis(db, ref, analysis)
    return analysis


# --------------------------------------------------------------------------- #
# 4. HUMAN APPROVAL GATE on the call outcome (never an auto-purchase)
# --------------------------------------------------------------------------- #
class OutcomeBody(BaseModel):
    decision: str  # APPROVE_NEXT | REQUEST_CHANGES | CONTINUE_NEGOTIATION | REJECT
    note: str | None = None


@router.post("/outcome/{ref}")
async def record_outcome(ref: str, body: OutcomeBody, user: dict = Depends(get_current_user)):
    valid = {"APPROVE_NEXT", "REQUEST_CHANGES", "CONTINUE_NEGOTIATION", "REJECT"}
    if body.decision not in valid:
        raise HTTPException(status_code=400, detail="Invalid decision")
    db = get_db()
    doc = await _owned_call(db, ref, user)
    if doc.get("status") == "CONFIGURED":
        raise HTTPException(status_code=400,
                            detail="Record an outcome only after the call has run")
    outcome = {"decision": body.decision, "note": body.note,
               "by": user.get("name"), "at": _now()}
    await db.voice_calls.update_one({"session_ref": ref},
                                    {"$set": {"outcome": outcome, "updated_at": _now()},
                                     "$push": {"outcome_history": outcome}})
    await audit.log_event(user["organization_id"],
                          "human_approved" if body.decision == "APPROVE_NEXT"
                          else "negotiation_action",
                          mission_id=doc["mission_id"], actor=user.get("name"),
                          detail=f"Call outcome for {doc['vendor_name']}: {body.decision}"
                                 + (f" — {body.note}" if body.note else ""))
    # NOTE: APPROVE_NEXT records intent to proceed; it does NOT place an order/purchase.
    return await db.voice_calls.find_one({"session_ref": ref}, {"_id": 0})


# --------------------------------------------------------------------------- #
# 5. Provider webhooks (reuse Exotel token scheme; authority stays read-only)
# --------------------------------------------------------------------------- #
@router.post("/voice-start")
async def voice_start(request: Request):
    """Exotel Passthru for an answered call. Returns READ-ONLY agent context for the
    voice bot: the disclosure to speak, objective, authority (frozen), and the persona.
    Cannot mutate authority or create anything."""
    params = await _merged_params(request)
    _check_webhook_token(params)
    db = get_db()
    ref = params.get("CustomField") or params.get("session_ref")
    call_sid = params.get("CallSid")
    doc = await db.voice_calls.find_one({"session_ref": ref}, {"_id": 0}) if ref else None
    if not doc and call_sid:
        doc = await db.voice_calls.find_one({"call_sid": call_sid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Unknown call session")
    # Never let an unapproved/unplaced session be marked connected by a webhook.
    if not doc.get("approved"):
        raise HTTPException(status_code=409, detail="Call not approved")
    if call_sid and not doc.get("call_sid"):
        await db.voice_calls.update_one({"session_ref": doc["session_ref"]},
                                        {"$set": {"call_sid": call_sid, "status": "connected",
                                                  "recording": {"state": "RECORDING_ACTIVE",
                                                                "url": (doc.get("recording") or {}).get("url")}
                                                  if doc.get("recording_notice") else doc.get("recording")}})
    mission = await db.missions.find_one({"id": doc["mission_id"]}, {"_id": 0}) or {}
    vendor = await db.vendors.find_one({"id": doc["vendor_id"]}, {"_id": 0}) or \
        {"name": doc["vendor_name"]}
    authority = doc["authority"]
    constraints = {"max_price": authority.get("max_price_per_unit"),
                   "target_price": authority.get("target_price_per_unit"),
                   "max_delivery_days": authority.get("max_delivery_days"),
                   "min_warranty": authority.get("min_warranty")}
    agent_prompt = ai_service.build_agent_prompt(mission, vendor, constraints)
    return {
        "session_ref": doc["session_ref"],
        "disclosure": doc.get("disclosure_script"),
        "objective": doc["objective"],
        "authority": authority,  # read-only context
        "agent_prompt": agent_prompt,
        "rules": ("Open with the disclosure. Negotiate toward the target price and never exceed "
                  "the maximum authorized price. You may not commit, approve or place any order. "
                  "A human approves all purchases."),
    }


@router.post("/status-callback")
async def status_callback(request: Request):
    """Exotel StatusCallback. Persists status/duration/recording. Triggers analysis.
    Idempotent per CallSid. Never creates a purchase."""
    params = await _merged_params(request)
    _check_webhook_token(params)
    db = get_db()
    ref = params.get("CustomField") or params.get("session_ref")
    call_sid = params.get("CallSid")
    doc = await db.voice_calls.find_one({"session_ref": ref}, {"_id": 0}) if ref else None
    if not doc and call_sid:
        doc = await db.voice_calls.find_one({"call_sid": call_sid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Unknown call session")
    if not doc.get("approved"):
        raise HTTPException(status_code=409, detail="Call not approved")
    if doc.get("status") in TERMINAL_STATUSES and doc.get("terminal_recorded"):
        return {"status": "duplicate"}

    call_status = (params.get("CallStatus") or params.get("DialCallStatus") or "completed").lower()
    duration = params.get("ConversationDuration") or params.get("DialCallDuration") \
        or params.get("OnCallDuration") or params.get("Duration")
    try:
        duration = int(duration) if duration is not None else None
    except Exception:
        duration = None
    recording_url = params.get("RecordingUrl")

    rec = dict(doc.get("recording") or {})
    if not doc.get("recording_notice"):
        rec = {"state": "RECORDING_NOT_SUPPORTED", "url": None}
    elif recording_url:
        rec = {"state": "RECORDING_AVAILABLE", "url": recording_url}
    elif call_status in ("failed", "no-answer", "busy", "canceled"):
        rec = {"state": "RECORDING_FAILED", "url": None}
    else:
        rec.setdefault("state", "RECORDING_REQUESTED")

    # Optional transcript pushed by the streaming bridge (stored only).
    transcript = doc.get("transcript") or []
    tstatus = "AVAILABLE" if transcript else "UNAVAILABLE"

    update = {"status": call_status, "duration": duration, "recording": rec,
              "transcript_status": tstatus, "terminal_recorded": True,
              "ended_at": _now(), "updated_at": _now()}
    await db.voice_calls.update_one({"session_ref": doc["session_ref"]}, {"$set": update})
    await audit.log_event(doc["organization_id"], "call_ended", mission_id=doc["mission_id"],
                          detail=f"Exotel call {call_status}"
                                 + (f", {duration}s" if duration else ""))

    # Analyze only if we actually captured a transcript — never fabricate one.
    if transcript:
        try:
            analysis = await ai_service.analyze_call(doc["objective"], doc["authority"],
                                                     transcript, f"call-an-{doc['session_ref']}")
            await db.voice_calls.update_one({"session_ref": doc["session_ref"]},
                                            {"$set": {"analysis": analysis}})
            await _persist_offer_from_analysis(db, doc["session_ref"], analysis)
            await _link_thread_event(db, doc, analysis, simulated=False)
        except Exception as e:
            log.error("post-call analysis failed: %s", type(e).__name__)
    return {"status": "recorded", "call_status": call_status,
            "recording_state": rec["state"], "transcript_status": tstatus}


class TranscriptItem(BaseModel):
    speaker: str  # AI | SUPPLIER | SYSTEM
    text: str
    timestamp: str | None = None
    confidence: float | None = None


@router.post("/transcript/{ref}")
async def push_transcript(ref: str, item: TranscriptItem, request: Request):
    """Ingest a live transcript line from the streaming/realtime bridge (token-protected)."""
    params = await _merged_params(request)
    _check_webhook_token(params)
    db = get_db()
    doc = await db.voice_calls.find_one({"session_ref": ref}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Unknown call session")
    speaker = item.speaker.upper()
    if speaker not in ("AI", "SUPPLIER", "SYSTEM"):
        speaker = "SYSTEM"
    line = {"id": uuid.uuid4().hex, "speaker": speaker, "text": item.text,
            "timestamp": item.timestamp or _mmss((doc.get("duration") or 0)),
            "confidence": item.confidence}
    await db.voice_calls.update_one(
        {"session_ref": ref},
        {"$push": {"transcript": line}, "$set": {"transcript_status": "AVAILABLE",
                                                 "updated_at": _now()}})
    return {"ok": True}

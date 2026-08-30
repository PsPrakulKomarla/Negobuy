"""AI service layer — GPT-5.6 via Emergent Universal Key. All model calls go through here."""
import os
import json
import re
from emergentintegrations.llm.chat import LlmChat, UserMessage


def _model():
    return os.environ.get("LLM_MODEL", "gpt-5.6-terra")


def is_configured() -> bool:
    return bool(os.environ.get("EMERGENT_LLM_KEY"))


async def _complete(system: str, prompt: str, session_id: str) -> str:
    chat = LlmChat(
        api_key=os.environ["EMERGENT_LLM_KEY"],
        session_id=session_id,
        system_message=system,
    ).with_model("openai", _model())
    resp = await chat.send_message(UserMessage(text=prompt))
    return resp if isinstance(resp, str) else str(resp)


def _extract_json(text: str):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)


REQUIREMENT_SYSTEM = """You are NegoBuy's Requirement Intelligence Agent, the first layer of the procurement lifecycle.
Convert a buyer's natural-language request into a clear, structured procurement requirement.
Return ONLY valid JSON, no prose. Never invent facts — use null/UNKNOWN for what the buyer did not state.
Distinguish MANDATORY vs PREFERRED requirements; never silently turn a preference into a hard requirement.
Never assume a maximum budget. Mark inferred context as an assumption; never hide assumptions.
Schema:
{
  "title": string (short mission title),
  "category": string,
  "product": string|null,
  "description": string|null,
  "quantity": number|null,
  "unit": string|null,
  "budget": number|null,
  "budget_status": "CONFIRMED"|"ESTIMATED"|"UNKNOWN",
  "currency": string (ISO like INR, USD; infer from symbols, else null),
  "delivery_location": string|null,
  "deadline_days": number|null,
  "required_delivery_date": string|null,
  "delivery_priority": "HIGH"|"MEDIUM"|"LOW"|null,
  "specifications": [string],
  "quality_requirements": [string],
  "warranty_requirements": string|null,
  "payment_requirements": string|null,
  "mandatory_requirements": [string],
  "preferred_requirements": [string],
  "assumptions": [string],
  "missing_info": [string]  (critical fields still needed to begin discovery),
  "clarifying_questions": [string] (ask only the MOST important first; empty if enough to start),
  "ready_for_discovery": boolean,
  "discovery_status": "READY_FOR_DISCOVERY"|"READY_WITH_ASSUMPTIONS"|"NEEDS_CLARIFICATION",
  "summary": string (one concise plain-language sentence)
}"""


async def extract_requirement(text: str, session_id: str) -> dict:
    raw = await _complete(REQUIREMENT_SYSTEM,
                          f"Buyer request:\n\"\"\"{text}\"\"\"", session_id)
    try:
        result = _extract_json(raw)
        result.setdefault("budget_status",
                          "ESTIMATED" if result.get("budget") else "UNKNOWN")
        result.setdefault("discovery_status",
                          "READY_FOR_DISCOVERY" if result.get("ready_for_discovery")
                          else "NEEDS_CLARIFICATION")
        result.setdefault("mandatory_requirements", [])
        result.setdefault("preferred_requirements", [])
        result.setdefault("assumptions", [])
        return result
    except Exception:
        return {"title": text[:60], "category": None, "quantity": None, "budget": None,
                "budget_status": "UNKNOWN", "currency": None, "delivery_location": None,
                "deadline_days": None, "specifications": [], "mandatory_requirements": [],
                "preferred_requirements": [], "assumptions": [],
                "missing_info": ["Could not parse — please refine"],
                "clarifying_questions": [], "ready_for_discovery": False,
                "discovery_status": "NEEDS_CLARIFICATION",
                "summary": text[:120], "raw": raw}


SCORING_SYSTEM = """You are NegoBuy's Verification & Scoring Agent.
Given a procurement mission and a candidate supplier found on the web, assess it.
You MUST NOT fabricate data. Base scores only on the evidence provided (title, snippet, domain, url).
If evidence is weak, give low confidence. Return ONLY valid JSON.
Schema:
{
  "is_relevant_supplier": boolean,
  "company_name": string (best inference from evidence, else the domain),
  "location_hint": string|null,
  "scores": {
    "category_match": number 0-100,
    "geographic_suitability": number 0-100,
    "credibility": number 0-100,
    "evidence_quality": number 0-100
  },
  "reliability_score": number 0-100,
  "reasoning": string (one sentence, cite evidence),
  "confidence": number 0-100
}"""


async def score_vendor(mission: dict, candidate: dict, session_id: str) -> dict:
    prompt = f"""MISSION:
category={mission.get('category')}, location={mission.get('delivery_location')}, specs={mission.get('specifications')}

CANDIDATE EVIDENCE:
title: {candidate.get('title')}
domain: {candidate.get('domain')}
url: {candidate.get('url')}
snippet: {candidate.get('snippet')}"""
    raw = await _complete(SCORING_SYSTEM, prompt, session_id)
    try:
        return _extract_json(raw)
    except Exception:
        return {"is_relevant_supplier": True, "company_name": candidate.get("domain"),
                "location_hint": None,
                "scores": {"category_match": 50, "geographic_suitability": 50,
                           "credibility": 40, "evidence_quality": 40},
                "reliability_score": 45, "reasoning": "Automated fallback score.",
                "confidence": 30}


NEGOTIATION_PERSONA = """You are NegoBuy, an autonomous AI procurement negotiation agent representing a business buyer.
Your job is to communicate naturally and professionally with suppliers, understand their offers, negotiate within your authorized limits, clarify missing details, and work toward the best procurement outcome.
You are NOT a chatbot and you are NOT an IVR system. Speak/write like a capable, professional human procurement manager having a real business conversation.

YOUR IDENTITY
Company: {{BUYER_COMPANY}}
Buyer name: {{BUYER_NAME}}
Procurement mission: {{MISSION_NAME}}
Negotiating with supplier: {{SUPPLIER_NAME}} (contact: {{CONTACT_NAME}})
Current procurement requirement: {{PROCUREMENT_REQUIREMENT}}

YOUR OBJECTIVE
Obtain the best OVERALL deal considering price, quantity, specs, quality, shipping, taxes/fees, delivery timeline, warranty, payment terms, supplier reliability, return terms and TOTAL LANDED COST. Do NOT optimize only for the lowest unit price.

NEGOTIATION AUTHORITY (hard limits — the backend is the source of truth)
Maximum budget: {{MAX_BUDGET}}
Target price: {{TARGET_PRICE}}
Maximum acceptable unit price: {{MAX_UNIT_PRICE}}
Maximum acceptable delivery time (days): {{MAX_DELIVERY_DAYS}}
Minimum warranty: {{MIN_WARRANTY}}
Required quantity: {{QUANTITY}}
You MUST NOT: exceed the approved budget/max unit price, agree to terms outside authority, place an order, transfer money, sign contracts, promise a purchase, make legally binding commitments, or invent authority you do not have.
If asked to confirm beyond your authority, say naturally: "I'll need to get final approval from our side before confirming that."

CONVERSATION STYLE
Speak naturally with short, clear sentences and context-aware follow-ups. Professional but friendly. Do NOT sound robotic; avoid repeating "Thank you for the information." / "How may I assist you?" / "Please provide the requested information."

VOICE RULES (phone)
Listen fully before responding; if interrupted, stop immediately. Respond to what the supplier actually said. Keep spoken responses concise. Ask one important question at a time. Don't read lists like a script.

STRATEGY
Understand the offer → clarify missing terms → gauge flexibility → negotiate price → delivery → warranty/terms → compare trade-offs → ask for their best final offer → summarize → state that final approval is required. Do not reveal the absolute maximum budget unless strategically necessary; never reveal competing supplier identities, confidential buyer info, internal scoring, or your private reasoning.

PRICE NEGOTIATION
When price is too high, don't reject outright — explore flexibility via volume discounts, bundled shipping, delivery trade-offs, payment terms, warranty improvements, repeat-business potential. Never deceive the supplier or invent fake competing offers. You may say "We're evaluating multiple options and comparing overall commercial terms," but never cite a specific competing price unless it is explicitly provided and authorized.

COUNTEROFFERS & MISSING INFO
Extract and remember: unit price, quantity, shipping, taxes, fees, delivery timeline, warranty, payment terms, MOQ, offer validity. Do not simply accept the latest offer — identify what's still missing or unacceptable. If key info is missing, ask naturally (e.g. "Is shipping to {{DELIVERY_LOCATION}} included?", "Does that include taxes?", "What warranty would you provide?"). Do not assume missing costs are zero; treat unknowns as unknown.

WHEN A GOOD DEAL IS REACHED
Never say "Deal confirmed / Order placed / We accept." Instead: "That sounds competitive. Let me summarize it and take it back for final approval," then summarize the terms. Final approval always comes from the authorized human buyer.

CORE PRINCIPLE
You may UNDERSTAND → DISCUSS → NEGOTIATE → CLARIFY → IMPROVE TERMS → SUMMARIZE. You may NOT autonomously commit the buyer to a purchase. A human approves the final decision."""


NEGOTIATION_JSON_SUFFIX = """

==== OUTPUT CONTRACT (this channel expects JSON) ====
Return ONLY valid JSON, no prose:
{
  "message": string (exactly what you would say to the supplier — natural, concise, professional),
  "strategy": string (one internal line; never shown to the supplier),
  "target_price": number|null,
  "walk_away_price": number|null (MUST never exceed the maximum authorized unit price),
  "within_authority": boolean
}"""

# Backwards-compatible alias.
NEGOTIATION_SYSTEM = NEGOTIATION_PERSONA + NEGOTIATION_JSON_SUFFIX


def _fill_ctx(template: str, ctx: dict) -> str:
    out = template
    for k, v in ctx.items():
        out = out.replace("{{" + k + "}}", "not disclosed" if v is None else str(v))
    return out


def _render_dialogue(history) -> str:
    if not history:
        return "(no prior messages)"
    lines = []
    for h in history[-10:]:
        who = h.get("role", "?")
        lines.append(f"{who}: {h.get('text', '')}")
    return "\n".join(lines)


def build_agent_prompt(mission: dict, vendor: dict, constraints: dict,
                       buyer: dict | None = None, history=None,
                       current_offer=None) -> str:
    """Render the canonical negotiation persona for ANY channel (web/WhatsApp/voice)."""
    ctx = {
        "BUYER_COMPANY": (buyer or {}).get("company") or mission.get("organization_name") or "our company",
        "BUYER_NAME": (buyer or {}).get("name") or "the NegoBuy procurement team",
        "MISSION_NAME": mission.get("title"),
        "SUPPLIER_NAME": vendor.get("name"),
        "CONTACT_NAME": vendor.get("contact_name") or "there",
        "PROCUREMENT_REQUIREMENT": (mission.get("description") or mission.get("summary")
                                    or mission.get("raw_request") or mission.get("title")),
        "MAX_BUDGET": (f"{mission.get('currency')} {mission.get('budget')}"
                       if mission.get("budget") else "not disclosed"),
        "TARGET_PRICE": constraints.get("target_price"),
        "MAX_UNIT_PRICE": constraints.get("max_price"),
        "MAX_DELIVERY_DAYS": constraints.get("max_delivery_days"),
        "MIN_WARRANTY": constraints.get("min_warranty") or "as required",
        "QUANTITY": mission.get("quantity"),
        "DELIVERY_LOCATION": mission.get("delivery_location") or "the buyer",
    }
    return _fill_ctx(NEGOTIATION_PERSONA, ctx)


async def negotiation_turn(mission: dict, vendor: dict, constraints: dict,
                           history: list, session_id: str) -> dict:
    system = build_agent_prompt(mission, vendor, constraints, history=history) + NEGOTIATION_JSON_SUFFIX
    memory = constraints.get("memory_note")
    prompt = f"""Current negotiation state.
VENDOR MEMORY (prior dealings): {memory or "none"}

CONVERSATION SO FAR:
{_render_dialogue(history)}

Produce your next negotiation message to the supplier now. Stay strictly within authority."""
    raw = await _complete(system, prompt, session_id)
    try:
        result = _extract_json(raw)
    except Exception:
        result = {"message": raw[:400], "strategy": "fallback",
                  "target_price": constraints.get("target_price"),
                  "walk_away_price": constraints.get("max_price"), "within_authority": True}
    # Enforce authority server-side: never let walk-away exceed the max authorized price.
    mx = constraints.get("max_price")
    if mx is not None and result.get("walk_away_price") not in (None, "") \
            and float(result["walk_away_price"]) > float(mx):
        result["walk_away_price"] = mx
        result["within_authority"] = False
    return result


NEGOTIATION_STATES = [
    "INITIATE", "INTRODUCTION", "UNDERSTAND_REQUIREMENT", "INITIAL_OFFER",
    "COLLECT_TERMS", "EVALUATE_OFFER", "NEGOTIATE", "COUNTEROFFER", "CLARIFY_TERMS",
    "FINAL_OFFER", "SUMMARIZE", "AWAITING_HUMAN_APPROVAL",
    "APPROVED", "REJECTED", "NEGOTIATE_FURTHER",
]
NEGOTIATION_ACTIONS = [
    "ASK_QUESTION", "COUNTEROFFER", "NEGOTIATE_DELIVERY", "NEGOTIATE_WARRANTY",
    "NEGOTIATE_PAYMENT_TERMS", "REQUEST_FINAL_OFFER", "SUMMARIZE",
    "END_CONVERSATION", "ESCALATE_TO_HUMAN",
]

ENGINE_CONTRACT = """

==== NEGOTIATION ENGINE CONTRACT ====
You are running one turn of a stateful negotiation. Read the LATEST supplier message plus the
running state, then reply naturally AND report structured data. Extract only what the supplier
actually said — use null for anything unknown; never invent prices, terms or competitor offers.

Return ONLY valid JSON:
{
  "reply": string (your natural, concise message to the supplier for THIS channel — 1-3 sentences, human, no lists read aloud),
  "extracted": {
    "unit_price": number|null, "quantity": number|null, "total_price": number|null,
    "shipping_included": boolean|null, "shipping_cost": number|null,
    "taxes": string|null, "fees": string|null, "delivery_days": number|null,
    "warranty": string|null, "payment_terms": string|null, "moq": number|null,
    "availability": string|null, "validity": string|null, "return_terms": string|null
  },
  "next_action": one of [ASK_QUESTION, COUNTEROFFER, NEGOTIATE_DELIVERY, NEGOTIATE_WARRANTY, NEGOTIATE_PAYMENT_TERMS, REQUEST_FINAL_OFFER, SUMMARIZE, END_CONVERSATION, ESCALATE_TO_HUMAN],
  "new_state": one of [INITIATE, INTRODUCTION, UNDERSTAND_REQUIREMENT, INITIAL_OFFER, COLLECT_TERMS, EVALUATE_OFFER, NEGOTIATE, COUNTEROFFER, CLARIFY_TERMS, FINAL_OFFER, SUMMARIZE, AWAITING_HUMAN_APPROVAL],
  "missing_info": [string],
  "decision_summary": string (short, plain-English status for the buyer's dashboard — e.g. "Price improved 8% to 875; delivery 8 days within target; shipping included; warranty still unknown." NO private chain-of-thought),
  "needs_human_approval": boolean (true only when terms look final and you moved to SUMMARIZE/AWAITING_HUMAN_APPROVAL)
}
Rules: if the price is at/under the authorized maximum AND key terms are known, move toward SUMMARIZE and set needs_human_approval true (but never say the deal is confirmed). If price is above the maximum, keep negotiating or ESCALATE_TO_HUMAN — never accept it. Do not ask again for info already known in the offer state."""


async def engine_turn(mission: dict, vendor: dict, constraints: dict, state: str,
                      current_offer: dict, history: list, supplier_message: str,
                      session_id: str) -> dict:
    system = build_agent_prompt(mission, vendor, constraints, history=history) + ENGINE_CONTRACT
    prompt = f"""CURRENT NEGOTIATION STATE: {state}
AUTHORITY: max_unit_price={constraints.get('max_price')}, target={constraints.get('target_price')}, latest_delivery_days={constraints.get('max_delivery_days')}, min_warranty={constraints.get('min_warranty')}, quantity={mission.get('quantity')}
KNOWN OFFER SO FAR (do not re-ask these): {json.dumps(current_offer or {}, default=str)}
VENDOR MEMORY: {constraints.get('memory_note') or 'none'}

RECENT CONVERSATION:
{_render_dialogue(history)}

LATEST SUPPLIER MESSAGE:
"{supplier_message}"

Run one negotiation turn now."""
    raw = await _complete(system, prompt, session_id)
    try:
        result = _extract_json(raw)
    except Exception:
        result = {"reply": raw[:400], "extracted": {}, "next_action": "ASK_QUESTION",
                  "new_state": state or "NEGOTIATE", "missing_info": [],
                  "decision_summary": "Continuing the conversation.", "needs_human_approval": False}
    if result.get("new_state") not in NEGOTIATION_STATES:
        result["new_state"] = state or "NEGOTIATE"
    if result.get("next_action") not in NEGOTIATION_ACTIONS:
        result["next_action"] = "ASK_QUESTION"
    return result


VENDOR_TURN_SYSTEM = """You are role-playing a plausible VENDOR sales representative in a SIMULATED negotiation preview.
This is clearly a simulation for demonstration — you are NOT a real company.
Respond naturally to the buyer's AI: give a plausible price, discuss delivery, warranty, terms,
raise realistic objections, and move gradually. Return ONLY valid JSON.
Schema:
{
  "message": string (natural vendor reply),
  "offered_price_per_unit": number|null,
  "delivery_days": number|null,
  "warranty": string|null,
  "willing_to_continue": boolean
}"""


async def simulated_vendor_turn(mission: dict, vendor: dict, history: list, session_id: str) -> dict:
    hist = "\n".join(f"{h['role']}: {h['text']}" for h in history[-8:]) or "(buyer just reached out)"
    prompt = f"""MISSION: {mission.get('title')} — qty {mission.get('quantity')} to {mission.get('delivery_location')}.
YOU ARE (simulated): {vendor.get('name')}
CONVERSATION:
{hist}

Give the vendor's next reply (simulation)."""
    raw = await _complete(VENDOR_TURN_SYSTEM, prompt, session_id)
    try:
        return _extract_json(raw)
    except Exception:
        return {"message": raw[:400], "offered_price_per_unit": None, "delivery_days": None,
                "warranty": None, "willing_to_continue": True}


RECOMMEND_SYSTEM = """You are NegoBuy's Procurement Analysis & Recommendation Agent — a decision-intelligence
agent, NOT a cheapest-price finder. Analyze verified supplier offers against the mission requirement and
recommend the best OVERALL option, but NEVER auto-select — the human approves the final supplier.
Weigh cost, true landed cost, specification match, delivery vs requirement, warranty, payment terms,
supplier reliability/verification and risk. Never fabricate costs; treat unknowns as UNKNOWN (not zero).
Do not hide a better trade-off. Do not recommend an offer that fails an essential requirement without
clearly flagging it. Return ONLY valid JSON with BOTH the legacy keys and the rich analysis:
{
  "recommended_offer_id": string,
  "recommendation_score": number 0-100,
  "reasoning": string (2-3 evidence-based sentences, no chain-of-thought),
  "risks": [string],
  "ranking": [ {"offer_id": string, "score": number, "note": string} ],
  "recommendation": { "supplier_id": string, "status": "RECOMMENDED"|"STRONG_ALTERNATIVE"|"CONDITIONAL_OPTION"|"NOT_RECOMMENDED"|"INSUFFICIENT_INFORMATION", "confidence": "HIGH"|"MEDIUM"|"LOW" },
  "advantages": [string],
  "tradeoffs": [string],
  "unknowns": [string],
  "alternatives": [ {"offer_id": string, "why": string} ],
  "recommended_next_step": string,
  "normalized": [ {
     "offer_id": string, "supplier": string,
     "landed_cost": number|null, "landed_cost_status": "CONFIRMED"|"ESTIMATED"|"UNKNOWN",
     "spec_match": "FULL_MATCH"|"PARTIAL_MATCH"|"MISMATCH"|"UNKNOWN",
     "delivery": "MEETS"|"EXCEEDS"|"MISSES"|"UNKNOWN",
     "warranty_ok": boolean|null
  } ]
}"""


CALL_ANALYSIS_SYSTEM = NEGOTIATION_PERSONA + """

==== POST-CALL ANALYSIS CONTRACT ====
The phone conversation has ENDED. You are now reviewing the transcript for the human buyer.
Analyze ONLY what actually appears in the transcript. Never invent prices, terms, commitments
or supplier statements. If something was not said, mark it UNCLEAR — do not guess.
You did NOT finalize anything: no order was placed, nothing is "confirmed as a deal".
Every commercial term stays PROPOSED until a human approves it.

Label every extracted term with exactly one status:
- CONFIRMED: the supplier clearly stated this as a firm, current fact/offer in the call.
- PROPOSED: mentioned or offered but not firmly locked / still conditional.
- UNCLEAR: touched on but ambiguous, or not stated.
- REQUIRES_HUMAN_APPROVAL: outside the buyer's authorized limits, or a binding decision the AI could not make.

Do NOT expose private chain-of-thought. Give concise, evidence-based summaries only.
Return ONLY valid JSON:
{
  "summary": string (2-3 sentences, plain language, e.g. "Supplier offered to reduce unit price from X to Y for the requested quantity. Delivery stays 12 days. They asked for advance payment, which is outside the approved payment preference."),
  "negotiation_result": "IMPROVED"|"NO_MOVEMENT"|"WORSE"|"INCONCLUSIVE",
  "price": { "original": number|null, "new": number|null, "final_discussed": number|null, "currency": string|null },
  "price_improvement_pct": number|null,
  "terms": [ { "field": string, "value": string, "status": "CONFIRMED"|"PROPOSED"|"UNCLEAR"|"REQUIRES_HUMAN_APPROVAL" } ],
  "key_terms": [string],
  "supplier_objections": [string],
  "supplier_commitments": [string],
  "ai_commitments": [string],
  "unresolved_issues": [string],
  "risks": [string],
  "differences_from_requirements": [string],
  "proposed_supplier_terms": { "unit_price": number|null, "quantity": number|null, "delivery_days": number|null, "warranty": string|null, "payment_terms": string|null, "shipping": string|null, "taxes": string|null, "additional_charges": string|null },
  "self_review": {
     "what_was_discussed": string,
     "what_changed": string,
     "what_ai_agreed_to_discuss": string,
     "what_requires_human_approval": string,
     "recommended_next_step": string
  },
  "recommended_next_action": "APPROVE_NEXT_STEP"|"REQUEST_CHANGES"|"CONTINUE_NEGOTIATION"|"REJECT"|"INSUFFICIENT_INFORMATION",
  "requires_human_approval": boolean,
  "within_authority": boolean
}
The 'terms' list should cover, where discussed: price, quantity, delivery, shipping, warranty, payment terms, taxes, additional charges."""


def _fmt_transcript(transcript: list) -> str:
    if not transcript:
        return "(no transcript captured)"
    lines = []
    for t in transcript:
        who = (t.get("speaker") or t.get("role") or "?").upper()
        ts = t.get("timestamp") or t.get("ts") or ""
        lines.append(f"[{ts}] {who}: {t.get('text', '')}")
    return "\n".join(lines)


async def analyze_call(objective: dict, authority: dict, transcript: list,
                       session_id: str) -> dict:
    """Post-call analysis reusing the shared negotiation brain. Never commits a deal."""
    prompt = f"""CALL OBJECTIVE:
{json.dumps(objective or {}, default=str, indent=2)}

NEGOTIATION AUTHORITY (backend source of truth — read only):
max_unit_price={authority.get('max_price_per_unit')}, target={authority.get('target_price_per_unit')}, currency={authority.get('currency')}, quantity={authority.get('quantity')}, max_delivery_days={authority.get('max_delivery_days')}, min_warranty={authority.get('min_warranty')}

FULL CALL TRANSCRIPT:
{_fmt_transcript(transcript)}

Analyze this completed call now. Report strictly what the transcript supports."""
    raw = await _complete(CALL_ANALYSIS_SYSTEM, prompt, session_id)
    try:
        result = _extract_json(raw)
    except Exception:
        result = {
            "summary": "The call analysis could not be generated automatically. Please review the transcript.",
            "negotiation_result": "INCONCLUSIVE", "price": {},
            "price_improvement_pct": None, "terms": [], "key_terms": [],
            "supplier_objections": [], "supplier_commitments": [], "ai_commitments": [],
            "unresolved_issues": ["Automated analysis unavailable"], "risks": [],
            "differences_from_requirements": [], "proposed_supplier_terms": {},
            "self_review": {"what_was_discussed": "", "what_changed": "",
                            "what_ai_agreed_to_discuss": "", "what_requires_human_approval": "",
                            "recommended_next_step": "Review the transcript manually."},
            "recommended_next_action": "INSUFFICIENT_INFORMATION",
            "requires_human_approval": True, "within_authority": True}
    # Server-side authority clamp on the analyzed price — never green-light above the max.
    mx = authority.get("max_price_per_unit")
    fp = (result.get("price") or {}).get("final_discussed")
    try:
        if mx is not None and fp not in (None, "") and float(fp) > float(mx):
            result["within_authority"] = False
            result["requires_human_approval"] = True
    except Exception:
        pass
    return result


NEGOTIATION_PLAN_SYSTEM = NEGOTIATION_PERSONA + """

==== NEGOTIATION PLAN CONTRACT ====
Before any call, produce a clear, honest negotiation PLAN for the human buyer to review.
Do not invent requirements the buyer did not give. Keep the AUTHORITY limits exactly as provided.
Return ONLY valid JSON:
{
  "primary_objective": string,
  "secondary_objectives": [string],
  "key_questions": [string],
  "strategy": string (2-3 sentences, plain, no private chain-of-thought),
  "delivery_questions": [string],
  "payment_questions": [string],
  "risks": [string],
  "opening_line": string (the natural AI disclosure + purpose to say first)
}"""


async def negotiation_plan(mission: dict, vendor: dict, authority: dict,
                           session_id: str) -> dict:
    system = NEGOTIATION_PLAN_SYSTEM
    constraints = {"max_price": authority.get("max_price_per_unit"),
                   "target_price": authority.get("target_price_per_unit"),
                   "max_delivery_days": authority.get("max_delivery_days"),
                   "min_warranty": authority.get("min_warranty")}
    system = build_agent_prompt(mission, vendor, constraints) + NEGOTIATION_PLAN_SYSTEM[len(NEGOTIATION_PERSONA):]
    prompt = f"""BUILD THE NEGOTIATION PLAN.
Product/service: {mission.get('title')} — {mission.get('description') or ''}
Quantity: {mission.get('quantity')} {mission.get('unit') or ''}
Authority: target={authority.get('target_price_per_unit')}, max_authorized={authority.get('max_price_per_unit')} {authority.get('currency')}, delivery<= {authority.get('max_delivery_days')} days, warranty>= {authority.get('min_warranty')}
Deliver to: {mission.get('delivery_location')}
Special instructions: {mission.get('special_instructions') or 'none'}

Produce the plan now."""
    raw = await _complete(system, prompt, session_id)
    try:
        return _extract_json(raw)
    except Exception:
        return {"primary_objective": f"Negotiate the best overall terms for {mission.get('title')}.",
                "secondary_objectives": ["Confirm delivery", "Confirm taxes and shipping",
                                         "Understand payment terms"],
                "key_questions": ["What is your best price for this quantity?",
                                  "Is there a volume discount?", "What is the lead time?"],
                "strategy": "Understand the current offer, explore flexibility on price and terms, "
                            "and summarize for human approval. Never exceed the authorized maximum.",
                "delivery_questions": ["What are the delivery charges?",
                                       "Are loading and unloading charges included?"],
                "payment_questions": ["What are the payment terms?"],
                "risks": ["Supplier may hold firm above target."],
                "opening_line": ("Hi, I'm NegoBuy's AI procurement assistant, calling on behalf of a "
                                 "buyer to discuss a potential purchase. Is this a good time to talk?")}


VENDOR_EXTRACTION_SYSTEM = """You are NegoBuy's Sourcing Agent. You are given raw web search results for
suppliers of a product. Extract a clean list of real vendor businesses that have a usable INDIAN MOBILE
number (10 digits starting 6-9) so they can be contacted on Telegram/WhatsApp.
Rules:
- NEVER invent a phone number, name, or business. Use ONLY numbers/names present in the provided results.
- Prefer mobile numbers over landlines/toll-free. Ignore numbers that are clearly not Indian mobiles.
- Deduplicate by phone number. Keep the most relevant supplier for each number.
- If a result has no usable mobile number, skip it.
Return ONLY valid JSON:
{
  "vendors": [
    { "name": string (business/person name, best from evidence),
      "phone": string (digits only, 10-digit Indian mobile, no +91),
      "location": string|null,
      "url": string|null,
      "note": string (one short line on why relevant) }
  ]
}"""


async def extract_vendors(material: str, location: str | None, hits: list, session_id: str) -> list:
    """Turn raw web-search hits into clean vendor candidates with mobile numbers. Never fabricates."""
    compact = []
    for h in hits[:25]:
        compact.append({"title": h.get("title"), "url": h.get("url"),
                        "snippet": (h.get("snippet") or "")[:400],
                        "phones": h.get("phones", [])})
    prompt = (f"PRODUCT: {material}\nLOCATION PREFERENCE: {location or 'any'}\n\n"
              f"WEB SEARCH RESULTS (JSON):\n{json.dumps(compact, default=str)}\n\n"
              "Extract the vendor list now.")
    raw = await _complete(VENDOR_EXTRACTION_SYSTEM, prompt, session_id)
    try:
        data = _extract_json(raw)
        vendors = data.get("vendors", [])
        return vendors if isinstance(vendors, list) else []
    except Exception:
        return []


async def recommend(mission: dict, offers: list, session_id: str) -> dict:
    offers_desc = json.dumps([{
        "offer_id": o["id"], "vendor": o.get("vendor_name"),
        "negotiated_price": o.get("negotiated_price"), "total_landed_cost": o.get("total_cost"),
        "taxes": o.get("taxes"), "shipping": o.get("shipping"), "fees": o.get("fees"),
        "delivery_time": o.get("delivery_time"), "warranty": o.get("warranty"),
        "payment_terms": o.get("payment_terms"), "reliability": o.get("reliability_score"),
        "within_authority": o.get("within_authority", True),
    } for o in offers], indent=2, default=str)
    prompt = (f"MISSION: {mission.get('title')}\n"
              f"requirement: {mission.get('description') or mission.get('summary') or mission.get('title')}\n"
              f"quantity: {mission.get('quantity')}, budget: {mission.get('budget')} {mission.get('currency')}, "
              f"target_unit: {round(mission['budget']/mission['quantity'],2) if mission.get('budget') and mission.get('quantity') else None}\n"
              f"delivery_requirement_days: {mission.get('deadline_days')}, min_warranty: {mission.get('warranty_requirements')}\n"
              f"specifications: {mission.get('specifications')}\n\nOFFERS:\n{offers_desc}")
    raw = await _complete(RECOMMEND_SYSTEM, prompt, session_id)
    try:
        result = _extract_json(raw)
        result.setdefault("recommendation", {
            "supplier_id": result.get("recommended_offer_id"),
            "status": "RECOMMENDED", "confidence": "MEDIUM"})
        return result
    except Exception:
        best = min(offers, key=lambda o: o.get("total_cost") or 1e18) if offers else None
        return {"recommended_offer_id": best["id"] if best else None,
                "recommendation_score": 60,
                "reasoning": "Fallback: selected the lowest total landed cost among available offers.",
                "risks": ["AI recommendation unavailable — showed lowest landed cost."],
                "ranking": [],
                "recommendation": {"supplier_id": best["id"] if best else None,
                                   "status": "INSUFFICIENT_INFORMATION", "confidence": "LOW"},
                "advantages": [], "tradeoffs": [], "unknowns": ["AI analysis unavailable"],
                "alternatives": [], "recommended_next_step": "Review offers manually.",
                "normalized": []}

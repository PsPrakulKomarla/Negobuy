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


REQUIREMENT_SYSTEM = """You are NegoBuy's Requirement Agent, an expert B2B procurement analyst.
Extract structured procurement requirements from a buyer's natural-language request.
Return ONLY valid JSON, no prose. Never invent facts the buyer did not state — use null for unknowns.
Schema:
{
  "title": string (short mission title),
  "category": string,
  "quantity": number|null,
  "unit": string|null,
  "budget": number|null,
  "currency": string (ISO like INR, USD; infer from symbols, default null),
  "delivery_location": string|null,
  "deadline_days": number|null,
  "required_delivery_date": string|null,
  "specifications": [string],
  "quality_requirements": [string],
  "warranty_requirements": string|null,
  "payment_requirements": string|null,
  "missing_info": [string]  (critical fields still needed to begin discovery),
  "clarifying_questions": [string] (only if truly needed; empty if enough to start),
  "ready_for_discovery": boolean,
  "summary": string (one concise sentence)
}"""


async def extract_requirement(text: str, session_id: str) -> dict:
    raw = await _complete(REQUIREMENT_SYSTEM,
                          f"Buyer request:\n\"\"\"{text}\"\"\"", session_id)
    try:
        return _extract_json(raw)
    except Exception:
        return {"title": text[:60], "category": None, "quantity": None, "budget": None,
                "currency": None, "delivery_location": None, "deadline_days": None,
                "specifications": [], "missing_info": ["Could not parse — please refine"],
                "clarifying_questions": [], "ready_for_discovery": False,
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


RECOMMEND_SYSTEM = """You are NegoBuy's Comparison & Recommendation Agent.
Given several vendor offers with landed costs, recommend the best overall option.
Do NOT simply pick the cheapest — weigh landed cost, delivery, warranty, reliability and risk.
Return ONLY valid JSON.
Schema:
{
  "recommended_offer_id": string,
  "recommendation_score": number 0-100,
  "reasoning": string (2-3 sentences explaining WHY, referencing tradeoffs),
  "risks": [string],
  "ranking": [ {"offer_id": string, "score": number, "note": string} ]
}"""


async def recommend(mission: dict, offers: list, session_id: str) -> dict:
    offers_desc = json.dumps([{
        "offer_id": o["id"], "vendor": o.get("vendor_name"),
        "negotiated_price": o.get("negotiated_price"), "total_landed_cost": o.get("total_cost"),
        "delivery_time": o.get("delivery_time"), "warranty": o.get("warranty"),
        "reliability": o.get("reliability_score"),
    } for o in offers], indent=2)
    prompt = f"MISSION: {mission.get('title')}, budget {mission.get('budget')} {mission.get('currency')}\nOFFERS:\n{offers_desc}"
    raw = await _complete(RECOMMEND_SYSTEM, prompt, session_id)
    try:
        return _extract_json(raw)
    except Exception:
        best = min(offers, key=lambda o: o.get("total_cost") or 1e18) if offers else None
        return {"recommended_offer_id": best["id"] if best else None,
                "recommendation_score": 60,
                "reasoning": "Fallback: selected the lowest total landed cost.",
                "risks": ["AI recommendation unavailable — showed lowest landed cost."],
                "ranking": []}

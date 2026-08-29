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


NEGOTIATION_SYSTEM = """You are NegoBuy's Negotiation Agent representing a business BUYER.
You negotiate professionally and naturally — never IVR-style, never robotic.
You operate strictly within authority limits and NEVER exceed the maximum authorized price
or concede beyond the allowed limits. You are transparent that you act on behalf of a buyer.
Return ONLY valid JSON.
Schema:
{
  "message": string (what the buyer's AI would say to the vendor — natural, concise, professional),
  "strategy": string (internal reasoning, one line),
  "target_price": number|null,
  "walk_away_price": number|null,
  "within_authority": boolean
}"""


async def negotiation_turn(mission: dict, vendor: dict, constraints: dict,
                           history: list, session_id: str) -> dict:
    hist = "\n".join(f"{h['role']}: {h['text']}" for h in history[-8:]) or "(no prior messages)"
    prompt = f"""MISSION: {mission.get('title')} — qty {mission.get('quantity')}, deliver to {mission.get('delivery_location')} by {mission.get('deadline_days')} days.
VENDOR: {vendor.get('name')}
AUTHORITY LIMITS: max_price_per_unit={constraints.get('max_price')}, target_price={constraints.get('target_price')}, min_warranty={constraints.get('min_warranty')}, latest_delivery_days={constraints.get('max_delivery_days')}
CONVERSATION SO FAR:
{hist}

Produce the buyer AI's next negotiation message. Stay within authority."""
    raw = await _complete(NEGOTIATION_SYSTEM, prompt, session_id)
    try:
        return _extract_json(raw)
    except Exception:
        return {"message": raw[:400], "strategy": "fallback", "target_price": constraints.get("target_price"),
                "walk_away_price": constraints.get("max_price"), "within_authority": True}


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

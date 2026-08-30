"""Procurement Assurance AI — contract analysis, negotiated-vs-contract comparison,
and invoice verification. Analysis only; never approves, signs, or authorizes payment.
Never fabricates terms — unknowns stay UNKNOWN."""
import json
from ai_service import _complete, _extract_json

CONTRACT_SYSTEM = """You are NegoBuy's Procurement Assurance Agent (an AI assistant, NOT a lawyer).
Analyze the supplied contract text and compare it against the buyer's NEGOTIATED terms (source of truth).
Extract only what the contract actually states — never invent terms; use "UNKNOWN" for anything not present.
Do NOT approve or bless the contract. Flag material differences. Recommend qualified review for high risk.
Return ONLY valid JSON:
{
  "extracted": {
    "supplier_legal_name": string|null, "buyer_legal_name": string|null,
    "product": string|null, "specifications": string|null, "quantity": number|null,
    "unit_price": number|null, "total_value": number|null, "currency": string|null,
    "taxes": string|null, "shipping": string|null, "additional_fees": string|null,
    "delivery_location": string|null, "delivery_deadline": string|null,
    "warranty": string|null, "payment_terms": string|null, "deposit": string|null,
    "cancellation_terms": string|null, "termination": string|null, "late_delivery_terms": string|null,
    "penalties": string|null, "liability": string|null, "dispute_resolution": string|null,
    "governing_law": string|null, "confidentiality": string|null, "duration": string|null,
    "signatories": string|null
  },
  "comparison": [
    {"term": string, "negotiated": string, "contract": string,
     "status": "MATCH"|"DIFFERENCE"|"MATERIAL_DIFFERENCE"|"MISSING"|"UNCLEAR"|"NEEDS_HUMAN_REVIEW",
     "explanation": string}
  ],
  "risks": [ {"severity": "low"|"medium"|"high", "issue": string} ],
  "simple_summary": string (1-2 plain sentences a non-lawyer understands),
  "recommendation": "READY_FOR_HUMAN_REVIEW"|"ISSUES_FOUND_REVIEW_REQUIRED"|"HIGH_RISK_DIFFERENCES_DETECTED",
  "needs_legal_review": boolean
}"""


async def analyze_contract(mission: dict, negotiated: dict, contract_text: str, session_id: str) -> dict:
    neg = {
        "quantity": mission.get("quantity"),
        "unit_price": (negotiated or {}).get("negotiated_price"),
        "currency": mission.get("currency"),
        "delivery_deadline_days": mission.get("deadline_days"),
        "warranty": mission.get("warranty_requirements") or (negotiated or {}).get("warranty"),
        "shipping": (negotiated or {}).get("shipping"),
        "payment_terms": (negotiated or {}).get("payment_terms"),
        "delivery_location": mission.get("delivery_location"),
        "total_approved_cost": (negotiated or {}).get("total_cost"),
    }
    prompt = (f"NEGOTIATED TERMS (source of truth):\n{json.dumps(neg, default=str, indent=2)}\n\n"
              f"CONTRACT TEXT:\n\"\"\"\n{contract_text[:12000]}\n\"\"\"")
    raw = await _complete(CONTRACT_SYSTEM, prompt, session_id)
    try:
        return _extract_json(raw)
    except Exception:
        return {"extracted": {}, "comparison": [], "risks": [
            {"severity": "medium", "issue": "Automated analysis could not parse the contract."}],
            "simple_summary": "Could not analyze automatically — please review manually.",
            "recommendation": "ISSUES_FOUND_REVIEW_REQUIRED", "needs_legal_review": True}


INVOICE_SYSTEM = """You are NegoBuy's Procurement Assurance Agent verifying an invoice.
Compare the invoice against the APPROVED order/negotiated terms. Do NOT approve payment.
Never invent values; use "UNKNOWN" if absent. Flag every discrepancy for human review.
Return ONLY valid JSON:
{
  "lines": [ {"field": string, "approved": string, "invoice": string,
              "status": "MATCH"|"DIFFERENCE"|"UNKNOWN"|"REQUIRES_REVIEW"} ],
  "total_difference": string,
  "summary": string (plain language, e.g. "Invoice is 20000 higher due to a separate shipping charge that was included in negotiation."),
  "has_discrepancies": boolean,
  "recommendation": "MATCHES_APPROVED"|"DISCREPANCIES_FOUND_REVIEW_REQUIRED"
}"""


async def verify_invoice(order: dict, invoice_text: str, session_id: str) -> dict:
    approved = {
        "supplier": order.get("supplier"), "quantity": order.get("quantity"),
        "unit_price": order.get("unit_price"), "total_approved_cost": order.get("total_cost"),
        "currency": order.get("currency"), "warranty": order.get("warranty"),
        "payment_terms": order.get("payment_terms"),
    }
    prompt = (f"APPROVED ORDER:\n{json.dumps(approved, default=str, indent=2)}\n\n"
              f"INVOICE TEXT:\n\"\"\"\n{invoice_text[:8000]}\n\"\"\"")
    raw = await _complete(INVOICE_SYSTEM, prompt, session_id)
    try:
        return _extract_json(raw)
    except Exception:
        return {"lines": [], "total_difference": "UNKNOWN",
                "summary": "Could not verify automatically — please review manually.",
                "has_discrepancies": True, "recommendation": "DISCREPANCIES_FOUND_REVIEW_REQUIRED"}

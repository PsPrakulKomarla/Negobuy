"""Vendor email outreach — SendGrid delivery + AI composition/parsing (GPT-5.6).
All AI prompts are procurement-specific and never fabricate prices."""
import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from ai_service import _complete, _extract_json


def email_configured() -> bool:
    return bool(os.environ.get("SENDGRID_API_KEY") and os.environ.get("SENDER_EMAIL"))


def sender_email() -> str | None:
    return os.environ.get("SENDER_EMAIL")


def send_email(to: str, subject: str, html: str, text: str | None = None) -> dict:
    if not email_configured():
        return {"ok": False, "error": "Email not configured (SENDGRID_API_KEY / SENDER_EMAIL)."}
    message = Mail(
        from_email=os.environ["SENDER_EMAIL"],
        to_emails=to,
        subject=subject,
        html_content=html or text,
        plain_text_content=text or None,
    )
    try:
        sg = SendGridAPIClient(os.environ["SENDGRID_API_KEY"])
        resp = sg.send(message)
        return {"ok": resp.status_code in (200, 201, 202), "status_code": resp.status_code}
    except Exception as e:
        detail = None
        b = getattr(e, "body", None)
        if isinstance(b, (bytes, bytearray)):
            detail = b.decode(errors="ignore")
        elif b:
            detail = str(b)
        return {"ok": False, "error": str(e), "detail": detail}


def _fill(template: str, ctx: dict) -> str:
    out = template
    for k, v in ctx.items():
        out = out.replace("{{" + k + "}}", "" if v is None else str(v))
    return out


def _mission_ctx(mission: dict) -> dict:
    return {
        "mission_requirements": mission.get("description") or mission.get("raw_request") or mission.get("title"),
        "mission_specifications": ", ".join(mission.get("specifications") or []) or "not specified",
        "quantity": mission.get("quantity"),
        "target_budget": (f"{mission.get('currency')} {mission.get('budget')}"
                          if mission.get("budget") else "not disclosed"),
        "timeline": (f"{mission.get('deadline_days')} days" if mission.get("deadline_days") else "flexible"),
    }


COMPOSE_TMPL = """You are NegoBuy, an AI procurement buyer. Compose a professional procurement outreach email.
=== MISSION CONTEXT ===
Requirements: {{mission_requirements}}
Specifications: {{mission_specifications}}
Quantity: {{quantity}}
Target Budget: {{target_budget}}
Timeline: {{timeline}}
=== VENDOR CONTEXT ===
Vendor: {{vendor_name}}
Website: {{vendor_website}}
Description: {{vendor_description}}
Contact: {{contact_name}} ({{contact_title}})
=== INSTRUCTIONS ===
Tone: {{tone}}
Custom instructions: {{custom_instructions}}
{{template_text}}
{{thread_history}}
=== RULES ===
1. Be concise but thorough (max 250 words)
2. Never make up prices or commitments
3. Ask clear questions about: pricing, MOQ, lead time, payment terms, shipping
4. Include a specific but reasonable deadline for response (5 business days)
5. Mention that this is a competitive procurement process
6. End with a clear call-to-action
7. Do NOT use markdown formatting in the email body
8. Sign as "NegoBuy Procurement Team" with a professional signature
Respond in JSON format:
{
  "subject": "...",
  "body_text": "...",
  "body_html": "...",
  "key_asks": ["pricing", "moq", "lead_time"],
  "estimated_response_quality": 0.8,
  "reasoning": "..."
}"""

FOLLOWUP_INSTR = """This is a FOLLOW-UP email. Reference the previous conversation naturally.
Address any open questions from the vendor. Maintain momentum toward getting a formal quote.
If the vendor hasn't responded to a specific ask, gently reiterate it."""

PARSE_TMPL = """You are a procurement data extraction specialist. Parse this vendor email reply and extract all offer terms.
Mission Requirements:
{{mission_requirements}}
Vendor Email:
---
Subject: {{email_subject}}
Body:
{{email_body}}
---
Extract the following fields. If a field is not mentioned, set it to null. Be precise — do NOT guess or hallucinate values.
Respond in JSON:
{
  "price_per_unit": null or number,
  "currency": "USD" or detected currency,
  "moq": null or integer,
  "lead_time_days": null or integer,
  "payment_terms": null or string (e.g. "Net 30", "50% upfront"),
  "shipping_terms": null or string (e.g. "FOB", "CIF", "Ex-works"),
  "validity_date": null or "YYYY-MM-DD",
  "notes": "Any other important terms, conditions, or caveats",
  "confidence": 0.0 to 1.0
}"""

STRATEGY_TMPL = """You are a senior procurement strategist. Analyze this vendor and mission to suggest the best outreach approach.
Mission Requirements:
{{mission_requirements}}
Vendor:
- Name: {{vendor_name}}
- Description: {{vendor_description}}
- Website: {{vendor_website}}
- Contact: {{contact_name}} ({{contact_title}})
Provide:
1. Best subject line approach
2. Opening hook strategy
3. Key value props to emphasize
4. Potential objections and how to address them
5. Recommended tone (professional/friendly/firm)
6. Confidence score (0-1)
Respond in JSON format:
{
  "subject_approach": "...",
  "opening_hook": "...",
  "value_props": ["..."],
  "objections": [{"objection": "...", "response": "..."}],
  "recommended_tone": "...",
  "confidence": 0.85,
  "reasoning": "..."
}"""

SUMMARY_TMPL = """Summarize this vendor email thread and suggest the next action.
Conversation:
{{conversation_text}}
Respond in JSON:
{
  "summary": "2-3 sentence summary of where things stand",
  "key_points": ["..."],
  "vendor_sentiment": "positive|neutral|hesitant|negative",
  "next_action": "Specific recommended next step",
  "urgency": "low|medium|high"
}"""


def _render_thread(messages: list) -> str:
    lines = []
    for m in messages[-5:]:
        d = "OUTBOUND (us)" if m.get("direction") == "outbound" else "INBOUND (vendor)"
        body = (m.get("body_text") or "")[:600]
        lines.append(f"[{d}] {m.get('subject','')}\n{body}")
    return "\n\n".join(lines) or "(no prior messages)"


async def compose_outreach(mission, vendor, tone, custom, messages, follow_up, session):
    ctx = _mission_ctx(mission)
    ctx.update({
        "vendor_name": vendor.get("name"),
        "vendor_website": vendor.get("website"),
        "vendor_description": (vendor.get("description") or "")[:400],
        "contact_name": "there", "contact_title": "",
        "tone": tone or "professional",
        "custom_instructions": custom or "None",
        "template_text": "",
        "thread_history": "",
    })
    prompt = _fill(COMPOSE_TMPL, ctx)
    if follow_up and messages:
        prompt += "\n\n=== PREVIOUS CONVERSATION ===\n" + _render_thread(messages) + "\n" + FOLLOWUP_INSTR
    raw = await _complete("You are an expert B2B procurement email writer. Return ONLY valid JSON.",
                          prompt, session)
    try:
        return _extract_json(raw)
    except Exception:
        return {"subject": f"Procurement enquiry — {mission.get('title')}", "body_text": raw[:1200],
                "body_html": f"<p>{raw[:1200]}</p>", "key_asks": ["pricing", "lead_time"],
                "estimated_response_quality": 0.5, "reasoning": "fallback"}


async def parse_reply(mission, subject, body, session):
    ctx = _mission_ctx(mission)
    ctx.update({"email_subject": subject or "", "email_body": body or ""})
    raw = await _complete("You are a precise procurement data extractor. Return ONLY valid JSON.",
                          _fill(PARSE_TMPL, ctx), session)
    try:
        return _extract_json(raw)
    except Exception:
        return {"price_per_unit": None, "currency": mission.get("currency") or "USD", "moq": None,
                "lead_time_days": None, "payment_terms": None, "shipping_terms": None,
                "validity_date": None, "notes": "Could not parse automatically.", "confidence": 0.0}


async def outreach_strategy(mission, vendor, session):
    ctx = _mission_ctx(mission)
    ctx.update({"vendor_name": vendor.get("name"), "vendor_description": (vendor.get("description") or "")[:400],
                "vendor_website": vendor.get("website"), "contact_name": "the sales team", "contact_title": ""})
    raw = await _complete("You are a senior procurement strategist. Return ONLY valid JSON.",
                          _fill(STRATEGY_TMPL, ctx), session)
    try:
        return _extract_json(raw)
    except Exception:
        return {"subject_approach": "Direct RFQ", "opening_hook": "State the opportunity clearly",
                "value_props": ["Serious buyer", "Repeat business potential"],
                "objections": [], "recommended_tone": "professional", "confidence": 0.4,
                "reasoning": "fallback"}


CONTACT_TMPL = """You are a business intelligence researcher. Given a vendor's website and description, find the best procurement contact point.
Vendor: {{vendor_name}}
Website: {{vendor_website}}
Description: {{vendor_description}}
Task:
1. Suggest the most likely email pattern (e.g., procurement@vendor.com, sales@vendor.com)
2. Suggest the best department/role to contact
3. Suggest a personalized subject line based on their business
Respond in JSON:
{
  "suggested_email": "procurement@vendor.com",
  "suggested_role": "Sales Manager / Procurement Contact",
  "recommended_subject": "...",
  "confidence": 0.7,
  "notes": "Any caveats about the suggestion"
}"""


async def suggest_contact(vendor, session):
    ctx = {"vendor_name": vendor.get("name"), "vendor_website": vendor.get("website"),
           "vendor_description": (vendor.get("description") or "")[:400]}
    raw = await _complete("You infer B2B procurement contact points. Return ONLY valid JSON.",
                          _fill(CONTACT_TMPL, ctx), session)
    try:
        result = _extract_json(raw)
    except Exception:
        domain = vendor.get("domain") or "vendor.com"
        result = {"suggested_email": f"sales@{domain}", "suggested_role": "Sales / Procurement",
                  "recommended_subject": f"Procurement enquiry — {vendor.get('name')}",
                  "confidence": 0.3, "notes": "Automated fallback pattern."}
    return result


async def thread_summary(messages, session):
    raw = await _complete("You summarize procurement email threads. Return ONLY valid JSON.",
                          _fill(SUMMARY_TMPL, {"conversation_text": _render_thread(messages)}), session)
    try:
        return _extract_json(raw)
    except Exception:
        return {"summary": "Conversation in progress.", "key_points": [],
                "vendor_sentiment": "neutral", "next_action": "Follow up for a formal quote.",
                "urgency": "medium"}

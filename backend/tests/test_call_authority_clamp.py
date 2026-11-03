"""Directly probe ai_service.analyze_call authority clamp with a transcript where the
final discussed price EXCEEDS max_authorized_price."""
import asyncio
import sys

from dotenv import load_dotenv

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")


def test_clamp_above_max():
    import ai_service

    objective = {
        "supplier_name": "TEST_Vendor", "product": "Vitrified tiles 600x600",
        "quantity": 500, "current_price": 62, "target_price": 52,
        "max_authorized_price": 56, "currency": "INR",
        "delivery_deadline_days": 12, "warranty_requirements": "2 years",
        "payment_preferences": "50/50", "negotiation_priorities": ["price"],
    }
    authority = {"currency": "INR", "target_price_per_unit": 52,
                 "max_price_per_unit": 56, "quantity": 500,
                 "max_delivery_days": 12, "min_warranty": "2 years"}
    transcript = [
        {"timestamp": "00:00", "speaker": "SYSTEM", "text": "Call connected."},
        {"timestamp": "00:04", "speaker": "AI",
         "text": "Hi, I'm NegoBuy's AI procurement assistant. We need 500 boxes of vitrified tiles."},
        {"timestamp": "00:10", "speaker": "SUPPLIER",
         "text": "My absolute best price is INR 61 per unit, I cannot go lower than 61."},
        {"timestamp": "00:16", "speaker": "AI",
         "text": "Understood. So we are noting INR 61 per unit with 10 day delivery and 2 year warranty."},
        {"timestamp": "00:22", "speaker": "SUPPLIER",
         "text": "Yes, 61 per unit, 10 days delivery, 2 year warranty confirmed."},
        {"timestamp": "00:28", "speaker": "SYSTEM", "text": "Call ended."},
    ]
    res = asyncio.run(ai_service.analyze_call(objective, authority, transcript, "qa-clamp-1"))
    print("ANALYSIS:", res)
    price = (res.get("price") or {}).get("final_discussed")
    assert price is not None, res
    assert float(price) > 56, f"expected >56 extracted, got {price}"
    assert res.get("within_authority") is False, res
    assert res.get("requires_human_approval") is True, res

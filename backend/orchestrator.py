"""Agent orchestration — logs agent actions and runs the discovery/verification pipeline.
Explicit state transitions only; no uncontrolled agent loops."""
import uuid
from datetime import datetime, timezone
from db import get_db
import ai_service
import discovery


def now_iso():
    return datetime.now(timezone.utc).isoformat()


async def log_action(mission_id: str, agent: str, action: str, result: str = "",
                     evidence: dict | None = None):
    await get_db().agent_actions.insert_one({
        "id": uuid.uuid4().hex, "mission_id": mission_id, "agent": agent,
        "action": action, "result": result, "evidence": evidence or {},
        "created_at": now_iso(),
    })


async def set_status(mission_id: str, status: str):
    await get_db().missions.update_one(
        {"id": mission_id},
        {"$set": {"status": status, "updated_at": now_iso()}})


async def run_discovery_pipeline(mission_id: str):
    """Runs discovery -> verification/scoring -> shortlist. Stores real evidence."""
    db = get_db()
    mission = await db.missions.find_one({"id": mission_id}, {"_id": 0})
    if not mission:
        return
    session_id = f"discovery-{mission_id}"
    try:
        await set_status(mission_id, "DISCOVERING")
        query = discovery.build_query(mission)
        await log_action(mission_id, "Discovery Agent", "Searching web sources",
                         f"Query: {query}")

        try:
            hits = await discovery.web_search(query, max_results=15)
        except Exception as e:
            await log_action(mission_id, "Discovery Agent", "Search failed",
                             f"Web search error: {type(e).__name__}. Discovery unavailable.")
            await set_status(mission_id, "REQUIREMENT_REVIEW")
            return

        hits = discovery.dedupe(hits)
        await log_action(mission_id, "Discovery Agent", "Candidates found",
                         f"{len(hits)} unique candidate sources discovered")

        if not hits:
            await log_action(mission_id, "Discovery Agent", "No suppliers found",
                             "No candidate suppliers returned for this query.")
            await set_status(mission_id, "REQUIREMENT_REVIEW")
            return

        await set_status(mission_id, "VERIFYING")
        await db.vendors.delete_many({"mission_id": mission_id})
        scored = []
        for h in hits[:12]:
            try:
                assessment = await ai_service.score_vendor(mission, h, session_id)
            except Exception:
                assessment = {"is_relevant_supplier": True, "company_name": h["domain"],
                              "location_hint": None,
                              "scores": {"category_match": 40, "geographic_suitability": 40,
                                         "credibility": 40, "evidence_quality": 40},
                              "reliability_score": 40, "reasoning": "Scoring unavailable.",
                              "confidence": 25}
            if not assessment.get("is_relevant_supplier", True):
                continue
            weighted = discovery.weighted_score(assessment.get("scores", {}))
            vendor = {
                "id": uuid.uuid4().hex, "mission_id": mission_id,
                "organization_id": mission["organization_id"],
                "name": assessment.get("company_name") or h["domain"],
                "domain": h["domain"], "website": h["url"],
                "description": h["snippet"][:400],
                "location": assessment.get("location_hint"),
                "category": mission.get("category"),
                "contact_emails": h.get("emails", []),
                "contact_phones": h.get("phones", []),
                "scores": assessment.get("scores", {}),
                "weighted_score": weighted,
                "reliability_score": assessment.get("reliability_score", weighted),
                "confidence": assessment.get("confidence", 30),
                "reasoning": assessment.get("reasoning", ""),
                "verification_status": "UNDER_REVIEW",
                "evidence": [{"type": "web_search", "url": h["url"], "title": h["title"],
                              "snippet": h["snippet"][:300]}],
                "created_at": now_iso(),
            }
            scored.append(vendor)

        scored.sort(key=lambda v: v["weighted_score"], reverse=True)
        shortlist = scored[:10]
        for i, v in enumerate(shortlist):
            v["rank"] = i + 1
            # Mark top credible candidates as VERIFIED only when evidence quality is strong.
            eq = v["scores"].get("evidence_quality", 0)
            cred = v["scores"].get("credibility", 0)
            v["verification_status"] = "VERIFIED" if (eq >= 60 and cred >= 55) else "UNVERIFIED"

        if shortlist:
            await db.vendors.insert_many(shortlist)
        verified_count = sum(1 for v in shortlist if v["verification_status"] == "VERIFIED")
        await log_action(mission_id, "Verification Agent", "Shortlist ranked",
                         f"{len(shortlist)} shortlisted, {verified_count} verified by evidence")
        await set_status(mission_id, "COMPARING")
    except Exception as e:
        await log_action(mission_id, "Orchestrator", "Pipeline error", str(e))
        await set_status(mission_id, "REQUIREMENT_REVIEW")

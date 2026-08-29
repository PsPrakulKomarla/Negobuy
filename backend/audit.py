"""Unified audit log — one honest event stream per organization."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from db import get_db
from auth import get_current_user

router = APIRouter(prefix="/api/audit", tags=["audit"])


async def log_event(organization_id, event_type, actor=None, mission_id=None,
                    detail=None, metadata=None):
    try:
        await get_db().audit_logs.insert_one({
            "id": uuid.uuid4().hex, "organization_id": organization_id,
            "event_type": event_type, "actor": actor, "mission_id": mission_id,
            "detail": detail, "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        print(f"[audit] failed to log {event_type}: {e}")


@router.get("")
async def list_audit(user: dict = Depends(get_current_user),
                     limit: int = Query(100, le=500), mission_id: str | None = None):
    q = {"organization_id": user["organization_id"]}
    if mission_id:
        q["mission_id"] = mission_id
    return await get_db().audit_logs.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)

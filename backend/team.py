"""Team management — members, role management, and email invites."""
import os
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr
from db import get_db
from auth import (get_current_user, hash_password, create_access_token,
                  create_refresh_token, _set_cookies, _public_user)
import email_service

router = APIRouter(prefix="/api/team", tags=["team"])
ROLES = ["owner", "admin", "buyer", "viewer"]


def _now():
    return datetime.now(timezone.utc).isoformat()


def require_manage(user: dict):
    if user.get("role") not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owners and admins can manage the team.")


@router.get("/members")
async def members(user: dict = Depends(get_current_user)):
    docs = await get_db().users.find(
        {"organization_id": user["organization_id"]},
        {"_id": 0, "password_hash": 0}).sort("created_at", 1).to_list(200)
    return docs


class InviteBody(BaseModel):
    email: EmailStr
    role: str = "buyer"


@router.get("/invites")
async def list_invites(user: dict = Depends(get_current_user)):
    return await get_db().invites.find(
        {"organization_id": user["organization_id"], "accepted": False},
        {"_id": 0}).sort("created_at", -1).to_list(100)


@router.post("/invite")
async def create_invite(body: InviteBody, user: dict = Depends(get_current_user)):
    require_manage(user)
    if body.role not in ROLES or body.role == "owner":
        raise HTTPException(status_code=400, detail="Invalid role")
    db = get_db()
    if await db.users.find_one({"email": body.email.lower(),
                                "organization_id": user["organization_id"]}):
        raise HTTPException(status_code=409, detail="That user is already in your organization.")
    token = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    doc = {
        "id": uuid.uuid4().hex, "token": token, "email": body.email.lower(), "role": body.role,
        "organization_id": user["organization_id"], "organization_name": user.get("organization_name"),
        "invited_by": user.get("name"), "accepted": False,
        "created_at": now.isoformat(), "expires_at": (now + timedelta(days=7)).isoformat(),
    }
    await db.invites.insert_one(dict(doc))
    doc.pop("_id", None)
    link = f"{os.environ.get('FRONTEND_URL')}/accept-invite?token={token}"
    doc["accept_link"] = link

    email_result = None
    if email_service.email_configured():
        html = (f"<p>Hi,</p><p><b>{user.get('name')}</b> invited you to join "
                f"<b>{user.get('organization_name')}</b> on NegoBuy as a <b>{body.role}</b>.</p>"
                f"<p><a href='{link}'>Accept your invitation</a></p>"
                f"<p>Or paste this link: {link}</p><p>— NegoBuy</p>")
        email_result = email_service.send_email(
            body.email, f"You're invited to {user.get('organization_name')} on NegoBuy", html)
    doc["email_result"] = email_result
    print(f"[TEAM INVITE] {body.email} -> {link}")
    return doc


@router.delete("/invites/{invite_id}")
async def revoke_invite(invite_id: str, user: dict = Depends(get_current_user)):
    require_manage(user)
    await get_db().invites.delete_one(
        {"id": invite_id, "organization_id": user["organization_id"]})
    return {"ok": True}


class RoleBody(BaseModel):
    role: str


@router.patch("/members/{user_id}")
async def set_role(user_id: str, body: RoleBody, user: dict = Depends(get_current_user)):
    require_manage(user)
    if body.role not in ROLES or body.role == "owner":
        raise HTTPException(status_code=400, detail="Invalid role")
    db = get_db()
    target = await db.users.find_one({"id": user_id, "organization_id": user["organization_id"]})
    if not target:
        raise HTTPException(status_code=404, detail="Member not found")
    if target.get("role") == "owner":
        raise HTTPException(status_code=400, detail="Cannot change the owner's role.")
    await db.users.update_one({"id": user_id}, {"$set": {"role": body.role}})
    await db.memberships.update_one(
        {"user_id": user_id, "organization_id": user["organization_id"]},
        {"$set": {"role": body.role}})
    return {"ok": True}


@router.delete("/members/{user_id}")
async def remove_member(user_id: str, user: dict = Depends(get_current_user)):
    require_manage(user)
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="You cannot remove yourself.")
    db = get_db()
    target = await db.users.find_one({"id": user_id, "organization_id": user["organization_id"]})
    if not target:
        raise HTTPException(status_code=404, detail="Member not found")
    if target.get("role") == "owner":
        raise HTTPException(status_code=400, detail="Cannot remove the owner.")
    # Detach the member into their own fresh personal workspace.
    new_org = uuid.uuid4().hex
    org_name = f"{(target.get('name') or 'My').split()[0]}'s Workspace"
    now = _now()
    await db.organizations.insert_one({"id": new_org, "name": org_name,
                                       "owner_id": user_id, "plan": "free", "created_at": now})
    await db.users.update_one({"id": user_id}, {"$set": {
        "organization_id": new_org, "organization_name": org_name, "role": "owner"}})
    await db.memberships.delete_many({"user_id": user_id,
                                      "organization_id": user["organization_id"]})
    await db.memberships.insert_one({"id": uuid.uuid4().hex, "user_id": user_id,
                                     "organization_id": new_org, "role": "owner", "created_at": now})
    return {"ok": True}


# ---- Public invite acceptance ----
@router.get("/invite/{token}")
async def invite_info(token: str):
    db = get_db()
    inv = await db.invites.find_one({"token": token, "accepted": False}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invite not found or already used.")
    user = await db.users.find_one({"email": inv["email"]}, {"_id": 0})
    return {"email": inv["email"], "organization_name": inv["organization_name"],
            "role": inv["role"], "invited_by": inv.get("invited_by"), "has_account": bool(user)}


class AcceptBody(BaseModel):
    token: str
    name: str | None = None
    password: str | None = None


@router.post("/accept")
async def accept_invite(body: AcceptBody, response: Response):
    db = get_db()
    inv = await db.invites.find_one({"token": body.token, "accepted": False})
    if not inv:
        raise HTTPException(status_code=400, detail="Invalid or expired invite.")
    now = _now()
    user = await db.users.find_one({"email": inv["email"]})
    if user:
        await db.users.update_one({"id": user["id"]}, {"$set": {
            "organization_id": inv["organization_id"],
            "organization_name": inv["organization_name"], "role": inv["role"]}})
        uid = user["id"]
    else:
        if not body.password or not body.name:
            raise HTTPException(status_code=400, detail="Name and password are required to create your account.")
        uid = uuid.uuid4().hex
        await db.users.insert_one({
            "id": uid, "email": inv["email"], "name": body.name,
            "password_hash": hash_password(body.password), "role": inv["role"],
            "organization_id": inv["organization_id"],
            "organization_name": inv["organization_name"],
            "plan": "free", "avatar": None, "created_at": now})
    await db.memberships.insert_one({"id": uuid.uuid4().hex, "user_id": uid,
                                     "organization_id": inv["organization_id"],
                                     "role": inv["role"], "created_at": now})
    await db.invites.update_one({"token": body.token}, {"$set": {"accepted": True}})
    fresh = await db.users.find_one({"id": uid}, {"_id": 0})
    access = create_access_token(fresh["id"], fresh["email"])
    _set_cookies(response, access, create_refresh_token(fresh["id"]))
    return {**_public_user(fresh), "access_token": access}

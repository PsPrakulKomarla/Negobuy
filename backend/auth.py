import os
import uuid
import jwt
import bcrypt
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pydantic import BaseModel, EmailStr, Field
from db import get_db

JWT_ALGORITHM = "HS256"
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _secret() -> str:
    return os.environ["JWT_SECRET"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: str, email: str) -> str:
    payload = {"sub": user_id, "email": email,
               "exp": datetime.now(timezone.utc) + timedelta(hours=12), "type": "access"}
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {"sub": user_id,
               "exp": datetime.now(timezone.utc) + timedelta(days=7), "type": "refresh"}
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def _set_cookies(response: Response, access: str, refresh: str):
    response.set_cookie("access_token", access, httponly=True, secure=True,
                        samesite="none", max_age=43200, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=True,
                        samesite="none", max_age=604800, path="/")


def _public_user(user: dict) -> dict:
    return {
        "id": user["id"], "email": user["email"], "name": user.get("name"),
        "role": user.get("role", "buyer"), "organization_id": user.get("organization_id"),
        "organization_name": user.get("organization_name"),
        "plan": user.get("plan", "free"), "avatar": user.get("avatar"),
    }


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await get_db().users.find_one({"id": payload["sub"]}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


class RegisterBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str
    organization_name: str | None = None


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class ForgotBody(BaseModel):
    email: EmailStr


class ResetBody(BaseModel):
    token: str
    password: str = Field(min_length=6)


async def _create_user(email, password, name, org_name, role="owner"):
    db = get_db()
    user_id = uuid.uuid4().hex
    org_id = uuid.uuid4().hex
    org_name = org_name or f"{name.split()[0]}'s Workspace"
    now = datetime.now(timezone.utc).isoformat()
    user = {
        "id": user_id, "email": email.lower(), "name": name,
        "password_hash": hash_password(password) if password else None,
        "role": role, "organization_id": org_id, "organization_name": org_name,
        "plan": "free", "avatar": None, "created_at": now,
    }
    await db.users.insert_one(user)
    await db.organizations.insert_one({
        "id": org_id, "name": org_name, "owner_id": user_id,
        "plan": "free", "created_at": now,
    })
    await db.memberships.insert_one({
        "id": uuid.uuid4().hex, "user_id": user_id, "organization_id": org_id,
        "role": "owner", "created_at": now,
    })
    return user


@router.post("/register")
async def register(body: RegisterBody, response: Response):
    db = get_db()
    if await db.users.find_one({"email": body.email.lower()}):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = await _create_user(body.email, body.password, body.name, body.organization_name)
    access = create_access_token(user["id"], user["email"])
    _set_cookies(response, access, create_refresh_token(user["id"]))
    return {**_public_user(user), "access_token": access}


@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response):
    db = get_db()
    ip = request.client.host if request.client else "unknown"
    identifier = f"{ip}:{body.email.lower()}"
    attempt = await db.login_attempts.find_one({"identifier": identifier})
    if attempt and attempt.get("count", 0) >= 5:
        locked_until = attempt.get("locked_until")
        if locked_until and datetime.fromisoformat(locked_until) > datetime.now(timezone.utc):
            raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")
    user = await db.users.find_one({"email": body.email.lower()})
    if not user or not user.get("password_hash") or not verify_password(body.password, user["password_hash"]):
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {"$inc": {"count": 1},
             "$set": {"locked_until": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}},
            upsert=True)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    await db.login_attempts.delete_one({"identifier": identifier})
    access = create_access_token(user["id"], user["email"])
    _set_cookies(response, access, create_refresh_token(user["id"]))
    return {**_public_user(user), "access_token": access}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return _public_user(user)


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await get_db().users.find_one({"id": payload["sub"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    response.set_cookie("access_token", create_access_token(user["id"], user["email"]),
                        httponly=True, secure=True, samesite="none", max_age=43200, path="/")
    return {"ok": True}


@router.post("/forgot-password")
async def forgot_password(body: ForgotBody):
    db = get_db()
    user = await db.users.find_one({"email": body.email.lower()})
    if user:
        token = secrets.token_urlsafe(32)
        await db.password_reset_tokens.insert_one({
            "token": token, "user_id": user["id"], "used": False,
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        })
        print(f"[PASSWORD RESET] {body.email}: {os.environ.get('FRONTEND_URL')}/reset-password?token={token}")
    return {"ok": True, "message": "If the email exists, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password(body: ResetBody):
    db = get_db()
    rec = await db.password_reset_tokens.find_one({"token": body.token, "used": False})
    if not rec:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    await db.users.update_one({"id": rec["user_id"]},
                              {"$set": {"password_hash": hash_password(body.password)}})
    await db.password_reset_tokens.update_one({"token": body.token}, {"$set": {"used": True}})
    return {"ok": True}


# ---- Emergent-managed Google session login ----
class SessionBody(BaseModel):
    session_id: str


# Short-lived cache so a duplicated exchange of the SAME single-use session_id still
# succeeds (Emergent session_ids are one-time; a StrictMode remount / double POST would
# otherwise get an upstream rejection on the 2nd call). Keyed by session_id.
_gsession_cache: dict = {}
_GSESSION_TTL = 300  # seconds


def _gcache_get(sid: str):
    import time
    item = _gsession_cache.get(sid)
    if not item:
        return None
    if item[0] < time.time():
        _gsession_cache.pop(sid, None)
        return None
    return item[1]


def _gcache_put(sid: str, data: dict):
    import time
    _gsession_cache[sid] = (time.time() + _GSESSION_TTL, data)


@router.post("/google/session")
async def google_session(body: SessionBody, response: Response):
    import httpx
    import logging
    log = logging.getLogger("google-auth")
    data = _gcache_get(body.session_id)
    if data is None:
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                r = await client.get(
                    "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                    headers={"X-Session-ID": body.session_id})
        except Exception as e:
            log.exception("google session-data request failed")
            raise HTTPException(status_code=502, detail=f"Auth service unreachable: {type(e).__name__}")
        if r.status_code != 200:
            log.error("google session exchange failed status=%s body=%s",
                      r.status_code, (r.text or "")[:500])
            raise HTTPException(status_code=401, detail="Invalid session")
        try:
            data = r.json()
        except Exception:
            log.error("google session-data non-JSON body=%s", (r.text or "")[:500])
            raise HTTPException(status_code=401, detail="Invalid session")
        if not data.get("email"):
            log.error("google session-data missing email: keys=%s", list(data.keys()))
            raise HTTPException(status_code=401, detail="Invalid session")
        _gcache_put(body.session_id, data)
    db = get_db()
    email = data["email"].lower()
    user = await db.users.find_one({"email": email})
    if not user:
        user = await _create_user(email, None, data.get("name", email.split("@")[0]), None)
        await db.users.update_one({"id": user["id"]}, {"$set": {"avatar": data.get("picture")}})
        user["avatar"] = data.get("picture")
    access = create_access_token(user["id"], user["email"])
    _set_cookies(response, access, create_refresh_token(user["id"]))
    return {**_public_user(user), "access_token": access}


async def seed_admin():
    db = get_db()
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@negobuy.ai").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await _create_user(admin_email, admin_password, "NegoBuy Admin", "NegoBuy HQ", role="admin")
    elif not verify_password(admin_password, existing.get("password_hash", "")):
        await db.users.update_one({"email": admin_email},
                                  {"$set": {"password_hash": hash_password(admin_password)}})

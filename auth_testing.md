# Auth-Gated App Testing Playbook (Emergent Google Auth + JWT)

NegoBuy uses BOTH email/password (JWT) and Emergent-managed Google login. Auth tokens are
JWTs (HS256) signed with JWT_SECRET. The frontend stores the access token in localStorage
(key `negobuy_token`) and sends it as `Authorization: Bearer <token>`; the backend also sets
httpOnly cookies (access_token/refresh_token).

## Backend endpoints (prefix /api/auth)
- POST /register {email,password,name,organization_name?}
- POST /login {email,password}  -> {..., access_token}
- POST /logout
- GET  /me  (Bearer or cookie)  -> public user
- POST /google/session {session_id}  (Emergent Google login; exchanges session_id with
  https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data using header X-Session-ID)

## Google flow (frontend)
1. Login button -> window.location = `https://auth.emergentagent.com/?redirect=${origin}/dashboard`
   REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
2. Returns to `${origin}/dashboard#session_id=xxx`.
3. App.js detects `useLocation().hash` containing `session_id=` DURING RENDER and renders <AuthCallback/>.
4. AuthCallback POSTs session_id to /api/auth/google/session, persists token, navigates to /dashboard.
5. AuthContext SKIPS the /me check on mount when `window.location.hash` includes `session_id=`.

## How to test the authenticated (protected) area without real Google
Mint a JWT for a seeded user and use it as a Bearer token (mirrors what google/session returns):

```python
import jwt, datetime
token = jwt.encode(
  {"sub": "<user_id>", "email": "<email>", "type": "access",
   "exp": datetime.datetime.utcnow()+datetime.timedelta(hours=12)},
  "<JWT_SECRET from backend/.env>", algorithm="HS256")
```
Then:
- curl GET /api/auth/me with `Authorization: Bearer <token>` -> 200 user
- In browser: `localStorage.setItem('negobuy_token', '<token>')` then goto /dashboard.

## Test accounts
- Admin (seeded): admin@negobuy.ai / NegoBuy@2026
- Register a buyer if needed.

## Checklist
- [ ] Email login returns access_token; /dashboard loads (no redirect to /login).
- [ ] /api/auth/me returns the user for a valid Bearer token; 401 for invalid.
- [ ] Google outbound: clicking "Continue with Google" reaches Google sign-in for emergentagent.com.
- [ ] Google callback routing: visiting /dashboard#session_id=BAD shows "Google sign-in failed"
      and redirects to /login (no stuck screen).
- [ ] Logout clears token and protected routes redirect to /login.

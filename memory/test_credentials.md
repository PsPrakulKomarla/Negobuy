# NegoBuy — Test Credentials

## Admin
- Email: `admin@negobuy.ai`
- Password: `NegoBuy@2026`
- Role: admin

## Test Buyer (owner)
- Email: `buyer@test.com`
- Password: `test123`
- Org: Acme Procurement

## Auth endpoints (prefix /api/auth)
- POST /register, /login, /logout, /refresh, /forgot-password, /reset-password
- GET /me
- POST /google/session  (Emergent-managed Google login; body {session_id})

Auth uses httpOnly cookies (access_token 12h, refresh_token 7d) with Bearer fallback.

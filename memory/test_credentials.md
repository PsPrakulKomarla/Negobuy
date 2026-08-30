# NegoBuy — Test Credentials

## Admin (PRIMARY — seeded automatically on startup, use this)
- Email: `admin@negobuy.ai`
- Password: `NegoBuy@2026`
- Role: admin

## Test Buyer (NOT auto-seeded in a fresh DB — register if needed)
- Email: `buyer@test.com`
- Password: `test123`

## Auth endpoints (prefix /api/auth)
- POST /register, /login, /logout, /refresh, /forgot-password, /reset-password
- GET /me
- POST /google/session  (Emergent-managed Google login; body {session_id})

Auth returns access_token (also httpOnly cookies). Frontend stores Bearer token in localStorage.

## Notes for testers
- Exotel is CONFIGURED and live-verified (account negobuy1, Caller ID 08047280637, api.exotel.com).
- OpenAI Realtime is CONFIGURED (OPENAI_API_KEY set).
- LIVE phone calls fail at Exotel with "Invalid 'From'" until an App Bazaar Voicebot/streaming
  applet is created (EXOTEL_APP_ID / EXOTEL_STREAM_URL). Use TEST mode to exercise the full pipeline.

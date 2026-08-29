# NegoBuy

**Your AI Buyer for the real world.**

NegoBuy is an AI procurement operator. Describe what you need to buy in plain language and NegoBuy
structures the requirement, discovers real suppliers on the web, scores and verifies them, negotiates
within your authority limits, computes true landed cost, recommends the best option with reasoning,
and requires explicit human approval before any purchase.

> It is not a chatbot with a dashboard — it is an AI procurement employee operating inside a premium command center.

## Highlights
- **AI requirement understanding** — GPT-5.6 converts natural language into a structured procurement spec.
- **Real vendor discovery** — live web search (Tavily), dedupe, AI scoring, verified top-10 shortlist with evidence URLs.
- **Negotiation engine** — AI negotiates within hard authority limits; every event recorded (voice preview simulated & clearly labelled until live voice is configured).
- **True landed cost** — product + tax + shipping + fees; missing costs surfaced as assumptions, never fabricated.
- **Comparison & recommendation** — reasoned recommendation weighing cost, delivery, warranty, reliability, risk.
- **Human approval** — nothing material happens without explicit authorization; full audit trail.
- **Premium 3D command center** — React Three Fiber AI-Buyer node network that responds to real mission state.

## Architecture
```
React (CRA) + R3F 3D  ──►  FastAPI (/api)  ──►  MongoDB
                              ├─ auth.py        (JWT + Bearer + Emergent Google)
                              ├─ ai_service.py  (GPT-5.6 layer)
                              ├─ discovery.py   (Tavily provider + scoring)
                              ├─ orchestrator.py(discovery/verification pipeline + audit)
                              ├─ landed_cost.py / billing.py / voice.py
                              └─ server.py      (missions, offers, compare, approve, dashboard)
```
Business logic is separated from UI; integrations sit behind swappable modules.

## Environment variables
Backend (`backend/.env`):
- `MONGO_URL`, `DB_NAME` — MongoDB
- `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` — auth
- `FRONTEND_URL` — CORS origin
- `EMERGENT_LLM_KEY`, `LLM_MODEL` — GPT-5.6 (Universal Key)
- `TAVILY_API_KEY` — optional (keyless discovery works without it)
- `OPENAI_API_KEY` — optional; enables realtime voice negotiation
- `STRIPE_API_KEY` — optional; enables live checkout

Frontend (`frontend/.env`): `REACT_APP_BACKEND_URL`

**Never commit `.env` or secrets.**

## Local development
- Services run under supervisor: `sudo supervisorctl restart backend|frontend`
- Backend: FastAPI on `:8001` (routes prefixed `/api`)
- Frontend: CRA on `:3000`
- MongoDB local

## API (selected, all under `/api`)
- Auth: `POST /auth/register|login|logout|refresh|forgot-password|reset-password`, `GET /auth/me`, `POST /auth/google/session`
- Missions: `POST /missions/extract`, `POST|GET /missions`, `GET|PATCH|DELETE /missions/{id}`
- Pipeline: `POST /missions/{id}/discover`, `GET /missions/{id}/vendors|activity|negotiations|offers|comparison`
- Actions: `POST /missions/{id}/vendors/{vid}/negotiate`, `POST /missions/{id}/offers`, `POST /missions/{id}/compare`, `POST /missions/{id}/approve`
- Ops: `GET /dashboard/stats`, `GET /voice/status`, `GET /billing/plans`, `GET /billing/subscription`

## Test credentials
- Buyer: `buyer@test.com` / `test123`
- Admin: `admin@negobuy.ai` / `NegoBuy@2026`

## Not-yet-configured capabilities (clearly labelled in the UI)
- Live realtime **voice phone calls** — set `OPENAI_API_KEY`.
- Live **payments/checkout** — set `STRIPE_API_KEY`.

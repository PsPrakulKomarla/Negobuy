# NegoBuy — PRD & Build Log

## Product
NegoBuy — "Your AI Buyer for the real world." An AI procurement operator that turns a buying
request into: requirement → supplier discovery → verification → negotiation → landed-cost
comparison → recommendation → human approval → purchase. Not a chatbot — a procurement operator.

## Original problem statement
Real working product (no fake data). AI requirement understanding (GPT-5.6), real web vendor
discovery, vendor scoring/verification, offer + true landed-cost engine, negotiation engine with
authority limits + memory, natural AI voice negotiation architecture, human approval, org/workspace
multi-tenant auth, subscription + one-time billing architecture, premium dark 3D command-center UI.

## User choices (locked)
- AI model: GPT-5.6 (Emergent Universal Key) — model `gpt-5.6-terra`
- Auth: BOTH JWT email/password AND Emergent-managed Google login
- Discovery: real web search via Tavily (keyless now; key optional later)
- Voice: full call UI + architecture, marked "requires configuration" (OpenAI Realtime, needs OPENAI_API_KEY)
- Billing: Stripe/architecture — preview only (no live checkout yet)
- Frontend: fully 3D, immersive, futuristic, dark-first, cinematic

## Architecture
- Backend (FastAPI, `/api` prefix): auth.py (JWT+Bearer+Google), ai_service.py (GPT-5.6 layer),
  discovery.py (Tavily provider + scoring), orchestrator.py (discovery/verification pipeline + audit),
  landed_cost.py, negotiation via ai_service, voice.py (OpenAI Realtime, gated), billing.py, server.py.
- DB: MongoDB (uuid string ids). Collections: users, organizations, memberships, missions, vendors,
  offers, negotiations, comparisons, agent_actions, approvals, purchases, login_attempts, password_reset_tokens.
- Frontend (React CRA): R3F 3D BuyerScene (state-driven node network), Tailwind, framer-motion, sonner.
  Auth via Bearer token in localStorage (cookies also set as fallback).

## Implemented (2026-06)
- Auth: register/login/logout/me/refresh/forgot/reset, roles (owner/admin/buyer/viewer), org/workspace, Google session.
- Missions: full CRUD, statuses, AI requirement extraction (GPT-5.6).
- Discovery: real Tavily web search → dedupe → AI scoring → ranked verified shortlist (top 10) with evidence.
- Negotiation: AI buyer vs simulated vendor (labelled SIMULATION) within authority limits; events recorded; offer produced.
- Offers + true landed-cost engine (assumptions surfaced, never fabricated).
- Comparison + AI recommendation (reasoned, not just cheapest). Human approval (approve/reject/negotiate-further) → purchase.
- Dashboard command center, audit trail, premium 3D landing + mission experience, Voice Call UI (gated), Pricing.
- Verified end-to-end by testing agent (backend 100%, frontend 100% of tested flows).

## Not yet configured (intentional, labelled in UI)
- Live realtime voice phone calls (needs OPENAI_API_KEY) — /api/voice/status reports configured:false.
- Live Stripe checkout (needs STRIPE_API_KEY) — plans preview only.
- Tavily API key optional (keyless works, rate-limited).

## Backlog / next
- P1: Wire OpenAI Realtime voice (OPENAI_API_KEY) for real vendor calls + live transcript.
- P1: Live Stripe/Razorpay checkout + usage metering + entitlements enforcement.
- P2: Vendor intelligence long-term memory across missions; savings analytics; email outreach channel.
- P2: Org member invites + role management UI; procurement report export (PDF).

## Fix log — June 2026
- Google sign-in bug fixed: React StrictMode double-fired AuthCallback effect, exchanging the one-time session_id twice → 401 → bounce to /login. Fixes: useRef processed-guard in AuthCallback, synchronous session_id hash detection in App.js render, AuthProvider skips /me when hash has session_id, redirect target changed to /dashboard per Emergent Auth playbook. Verified: single exchange request, graceful failure path. Real Google account login needs user confirmation.

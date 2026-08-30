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
- Frontend (React CRA): Tailwind, framer-motion, sonner, React Three Fiber + drei.
  Auth via Bearer token in localStorage (cookies also set as fallback).
- **Landing = cinematic 3D journey** (`src/three/experience/`): scroll-driven, one continuous world
  centered on an angular AI command **monolith** (NOT a sphere/brain). 11 connected scenes driven by
  framer-motion `useScroll` progress → camera keyframe path (`CameraRig`) + per-scene fade/scale
  presence (`World`). Text lives in 2D overlays (`Overlays`). Reduced-motion + WebGL fallback = `ReducedStory`.

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

## Cinematic 3D landing rebuild — June 2026
- Replaced the old sphere/orbit-node hero (which was exactly the forbidden "glowing sphere / AI brain")
  with a full scroll-driven cinematic 3D story per user brief.
- New module `src/three/experience/`: `Experience.js` (Canvas + framer useScroll + TopNav with
  `skip-intro`/`nav-login` + `ProgressRail` + reduced-motion & WebGL error fallback),
  `World.js` (persistent monolith + Grid floor + fog + Sparkles + 11 fading `<Scene>` groups),
  `CameraRig.js` (11 keyframe camera path), `primitives.js` (Monolith, Kiosk, Beam w/ traveling packet,
  Shard, instanced MarketField filtering funnel, CostTower, SealRing), `Overlays.js` (2D scene copy,
  data-testids `story-scene-0..10`, CTA buttons `story-approve/negotiate/reject-btn`, `story-final-cta`,
  `story-pricing`), `story.js` (scripted illustrative narrative — clearly labelled, not live data),
  `helpers.js`, `ReducedStory.js` (2D accessible fallback). `Landing.js` now just renders `<Experience/>`.
- 11 scenes: enter command center → request+shards → market discovery funnel (1247→10) → supplier
  intelligence kiosks → verification beams → negotiation (AI vs supplier, price ₹900→₹875) → multi-vendor
  war room → true landed-cost tower (assumptions tagged) → AI recommendation → human decision
  (Approve/Negotiate/Reject) → mission complete + seal ring.
- User choices honoured: scroll-driven; scripted demo on a state-driven architecture; persistent Skip/Sign-in;
  reduced-motion fallback. Verified by testing agent (frontend 100%, zero console errors) + screenshots.

## Feature expansion — June 2026 (session 2)
User asked to "complete all incomplete items". Keys provided: OpenAI (voice), SendGrid (email). Payments (Razorpay) left NOT_CONFIGURED per user + no keys. WhatsApp/Twilio architecture present, NOT_CONFIGURED.

Implemented & wired:
- LIVE VOICE: OpenAI Realtime over browser WebRTC (frontend `lib/RealtimeAudioChat.js`, `pages/VoiceCall.js`). Backend `voice.py` registers emergent realtime router at /api/voice/realtime/{session,negotiate}; minute metering via /api/voice/usage + entitlements. Requires real mic to fully exercise.
- EMAIL OUTREACH (SendGrid): `email_service.py` — AI compose/parse-reply/strategy/contact-suggest/thread-summary (GPT-5.6) using user-provided prompts; `outreach.py` router (compose/send/reply/apply-offer/thread/summary/strategy/contact). Frontend `components/OutreachModal.js` + Email button per vendor in MissionDetail. SENDER_EMAIL must be a VERIFIED SendGrid sender or sends 403 (surfaced honestly).
- CROSS-MISSION VENDOR MEMORY: `vendor_memory.py`; recorded on negotiation + email offer; injected into negotiation prompt; shown as "★ known" badge; org-wide GET /api/vendors/memory; dashboard "remembered suppliers".
- SAVINGS ANALYTICS: GET /api/dashboard/analytics + recharts on Dashboard (savings vs spend line, missions-by-stage bar, remembered suppliers).
- TEAM & ROLES: `team.py` — members, invite (emailed via SendGrid), role change, remove (detaches to own workspace), public accept-invite. Frontend `pages/Team.js` + `pages/AcceptInvite.js` + nav item + /accept-invite route.
- PDF EXPORT: `reports.py` (reportlab) GET /api/missions/{id}/report; "Download report" button in MissionDetail.
- PLAN ENTITLEMENTS: `entitlements.py` — active-mission quota enforced on create (free=3), voice-minute metering (free=30). billing PLANS limits updated.
- INTEGRATION STATUS: /api/system/status now reports ai/discovery/email/voice/telephony/whatsapp/payments as CONFIGURED/READY/NOT_CONFIGURED/TEST/LIVE. Razorpay orders stub /api/billing/orders returns NOT_CONFIGURED honestly.
- WHATSAPP: `whatsapp.py` — Meta Cloud API webhook verify + inbound handler routed through central AI agent; NOT_CONFIGURED without creds.

Still NOT_CONFIGURED (need creds): Twilio telephony (phone calls), Razorpay payments, WhatsApp Cloud API, Tavily key (keyless works). SendGrid needs a verified sender to actually deliver.

## Audit-completion pass — June 2026 (session 3)
Added real (credential-gated) architecture, verified by testing agent (backend 15/15 + prior 19/19):
- payments.py (Razorpay): POST /api/billing/orders (server-side order), POST /api/billing/verify (HMAC signature), POST /api/webhooks/razorpay (signature + idempotent webhook_events + entitlement activation only after verified payment). NOT_CONFIGURED until RAZORPAY_KEY_ID/SECRET/WEBHOOK_SECRET.
- telephony.py (Twilio): POST /api/voice/calls (outbound initiate + call record), GET /api/voice/calls, POST /api/voice/twiml/{id}. NOT_CONFIGURED until TWILIO_* (+OPENAI_API_KEY for realtime bridge).
- whatsapp.py: added authorized outbound POST /api/whatsapp/send (mission+vendor scoped). Hardened inbound signature: app secret mandatory when WA live.
- audit.py: unified audit_logs + GET /api/audit; events wired: mission_created, human_approved, payment_order_created, payment_verified, call_started, call_stub_recorded, message_sent.
Security verified: .env gitignored, no secrets in frontend, org isolation (cross-org mission GET → 404), webhook signature checks, entitlement server-side.

## Exotel voice integration — June 2026 (session 4)
Verified by testing agent: backend 14/14 (100%), zero bugs.
- NEW FILE backend/exotel_service.py: provider abstraction (is_configured/config_status/place_outbound_call via Exotel Voice v1 Calls/connect.json, Basic auth key:token) + 4 endpoints under /api/voice/exotel.
- Endpoints: GET /status (configured/unconfigured, no secrets), POST /call (auth required, org-owned mission+vendor, initiates call, returns session_ref, never exposes creds), POST /session-start (Passthru webhook, shared-secret validated, returns READ-ONLY authority context + rules, cannot mutate authority), POST /session-end (StatusCallback webhook, idempotent by CallSid, stores status/duration/recording/reported_offer, NEVER auto-creates offer/purchase).
- Security: webhook shared-secret EXOTEL_WEBHOOK_TOKEN (Exotel has no HMAC); refuses unauthenticated webhooks when live; auth+org-isolation on /call; authority computed backend-side only (_authority); no purchase from voice. Secrets never logged (only ok/http/call_sid) or returned.
- server.py: include exotel_router + exotel block in /api/system/status.
- .env: EXOTEL_ACCOUNT_SID, EXOTEL_API_KEY, EXOTEL_API_TOKEN, EXOTEL_SUBDOMAIN (provided) + EXOTEL_WEBHOOK_TOKEN (generated). EXOTEL_CALLER_ID (ExoPhone) NOT provided → status honestly NOT_CONFIGURED; optional EXOTEL_APP_ID/EXOTEL_AGENT_NUMBER/EXOTEL_STREAM_URL supported for the answered-call flow.
- Regression suites: tests/test_new_features.py, test_audit_pass.py, test_exotel.py.

## Exotel real-call flow + live validation — June 2026 (session 5)
Verified by testing agent: backend 13/13, frontend modal 100%, zero bugs. ONE real call placed to +919008136500.
- FIXED root cause of Exotel 403/34009: EXOTEL_ACCOUNT_SID typo negbuy1 -> negobuy1 (dashboard value). Account negobuy1 (Trial, Singapore region) verified live on api.exotel.com -> 200.
- Added live credential validation: exotel_service.verify_credentials() + live_status() (60s cache). GET /api/voice/exotel/status and system/status now show READY only if Exotel accepts creds; else INVALID_CREDENTIALS with Exotel code/message (no secrets). Currently READY, verified=true.
- Added GET /api/voice/exotel/session/{session_ref} (auth, org-scoped) for UI polling; _normalize_number() -> E.164 (+91).
- Frontend: components/ExotelCallModal.js — guided flow (mission+vendor context -> editable destination pre-filled 9008136500 -> explicit confirm -> place -> live status progress rail + duration/recording + read-only authority + "no offer/order created" note). MissionDetail: per-vendor Exotel button (data-testid exotel-call-{id}).
- Safety re-verified: call never creates offer/order/purchase/approval; authority read-only from webhooks; secrets never exposed to frontend or logs.

## Unified negotiation persona — June 2026 (session 6)
Verified by testing agent (7/7 + 7/7, zero bugs).
- ai_service.py: replaced terse NEGOTIATION_SYSTEM with the full canonical NegoBuy negotiation-agent persona (identity, objective, authority limits + MUST-NOTs, natural style, voice rules, strategy, price tactics, counteroffer extraction, no-commit, human approval). New build_agent_prompt(mission,vendor,constraints,...) renders it; used by ALL channels.
- negotiation_turn now uses persona + JSON output contract; server-side clamp forces walk_away_price <= max authorized and sets within_authority=false when exceeded.
- exotel_service.session_start now returns agent_prompt (the rendered persona) for the voice bot — no secrets leaked; authority read-only/frozen at call start.
- WhatsApp inbound already routes through negotiation_turn → inherits the persona (shared brain).
- server.negotiate hardening: persisted AI offer flagged status OPEN vs OUT_OF_AUTHORITY (+ within_authority, max_authorized_price); delete_many now source-scoped to 'ai_negotiation_preview' so real vendor_email/manual offers are never wiped. (apply-offer intentionally supersedes preview for that vendor.)

## Full agent suite + orchestrator — June 2026 (session 7)
Backend verified: negotiation engine + assurance + orchestrator via testing agent 14/14 (iteration_9); requirement agent verified via curl; recommend upgrade backward-compatible.
- negotiation_engine.py: stateful per (mission,vendor) thread shared across web/WhatsApp/phone; structured offer extraction each turn; state machine (INITIATE..AWAITING_HUMAN_APPROVAL); decision engine (next_action); authority enforced; mirrors offer source='negotiation_engine'; endpoints .../negotiation [GET], /message, /decision. WhatsApp inbound now routes through engine.converse (shared brain).
- assurance_service.py + assurance.py: contract analyze (negotiated-vs-contract MATCH/DIFFERENCE/MATERIAL/MISSING + risks + recommendation, never approves), order lifecycle state machine (AUTHORIZED..COMPLETED + ALT states incl DELIVERED_PENDING_VERIFICATION), status/timeline/health, invoice verify (flags discrepancies, no payment approval), delivery confirm (pending->verified, human gate). Order authorize blocks out-of-authority offers.
- mission_orchestrator.py: GET /api/missions/{id}/orchestrator derives lifecycle stage from single mission state + artifacts (no duplicate memory), returns human_action_required, available_actions (agent+endpoint+requires_human), next_agent, timeline (audit), authority.
- ai_service.py upgrades: engine_turn (persona+contract), richer recommend() (normalized offers, landed-cost CONFIRMED/ESTIMATED/UNKNOWN, spec/delivery classification, confidence, advantages/tradeoffs/unknowns/alternatives; legacy keys kept for UI), richer extract_requirement (mandatory/preferred, budget_status, assumptions, discovery_status). All persona/authority/human-approval rules enforced.
- Audit event types added: negotiation_action, contract_analyzed, order_authorized, order_status_update, invoice_verified, delivery_verified/delivery_update.
DEFERRED UI (backend live, APIs ready): in-app Negotiation Room panel, Assurance/contract-review panel, order-tracking timeline, orchestrator lifecycle bar. Frontend for these agents not yet built this session.

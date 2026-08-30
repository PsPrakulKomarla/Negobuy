# NegoBuy — PRD & Build Log

## Product
AI procurement command center. Users create missions, discover/verify suppliers, and let an
AI negotiate (chat, voice, WhatsApp) within human-set authority. No purchase is ever finalized
without explicit human approval.

## Architecture (existing, reused — do NOT rebuild)
- FastAPI backend + React frontend + MongoDB. Auth: JWT + Emergent Google (auth.py).
- Shared negotiation brain: ai_service.py (persona, engine_turn, simulated_vendor_turn,
  extract_requirement, recommend) + negotiation_engine.py (stateful (mission,vendor) thread).
- Providers: exotel_service.py (voice calls), voice.py (OpenAI Realtime), whatsapp.py (Cloud API).
- Unified audit log (audit.py). Offers/vendors/missions/messages/negotiation_threads collections.

## Environment note
`.env` files are gitignored and were absent on checkout — reconstructed backend/.env +
frontend/.env. Exotel key/token order was swapped and Caller ID differed from the account's real
ExoPhone (08047280637) — both corrected. Frontend must be restarted after .env changes (CRA bakes
REACT_APP_BACKEND_URL at start).

## Implemented this session (2026-06)
### Feature A — Live AI Voice Negotiation, Call Recording & Review (Call Center)
- backend/call_center.py (`/api/voice/console`): Call Test Console config, explicit approval,
  recording state machine, timestamped transcript store, post-call analysis (ai_service.analyze_call),
  AI self-review, human approval gate, per-mission call history. Reuses exotel_service + the shared brain.
- frontend: CallConsole.js, CallReview.js, CallHistory.js.
- TEST mode runs a full simulated conversation through the shared brain (labelled simulation=true).
- LIVE mode places a real Exotel call (honest — see below).
- Tested: iteration_10 (34/34 backend + frontend E2E). Hardened after review.

### Feature B — Direct Business Negotiation & Smart WhatsApp Fallback
- backend/direct_negotiation.py (`/api/direct-negotiation`): prepare (Requirement Intelligence +
  mission + business vendor + shared thread + negotiation plan + honest provider statuses),
  unified timeline, controlled one-shot WhatsApp fallback, shared-memory WhatsApp reply
  (negotiation_engine.converse), combined final report, human decision gate, list + full GET.
- ai_service.negotiation_plan() added.
- Phone + WhatsApp share ONE negotiation thread (call_center._link_thread_event).
- frontend: DirectNegotiation.js (route /direct, sidebar nav) — form → review (plan) → run
  (state-driven stage visual, unified timeline, transcript, WhatsApp panel, offers, report, decisions).
- Tested: iteration_11 (29/29 backend + frontend E2E). Fixed HIGH fallback-after-test-call bug.

## Honest integration status
- Exotel: CONFIGURED + auth-verified. LIVE in-call two-way AI audio NOT working — requires an
  Exotel App-Bazaar Voicebot/Voice-Streaming applet (EXOTEL_APP_ID/EXOTEL_STREAM_URL) + Trial
  destination verification. Real call attempt returns Exotel 400 "Invalid 'From'". TEST mode is
  a labelled simulation.
- OpenAI Realtime: CONFIGURED (browser WebRTC voice works; phone bridge blocked on Exotel applet).
- WhatsApp Cloud API: NOT_CONFIGURED — fallback/replies are SIMULATED and clearly labelled.
- No endpoint creates a purchase/order. Human approval records intent only.

## Backlog (P1/P2)
- Exotel App-Bazaar streaming applet → real live in-call AI (needs provider dashboard config).
- WhatsApp Cloud API credentials → real fallback/replies.
- Deep link /direct/:missionId + recent-direct-negotiations list (resume past runs).
- Unique index on (mission_id, kind='fallback'); split DirectNegotiation.js as it grows.

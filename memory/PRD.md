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

## Auto-Sourcing Agent (web discovery -> Telegram negotiation) — Aug 2026
- New "Auto-Sourcing" tab: buyer enters material+specs, qty/unit, target/max price, city, max vendors.
- backend/auto_sourcing.py:
  - POST /api/sourcing/discover -> discovery.web_search (Tavily keyless) across supplier-intent queries;
    ai_service.extract_vendors() (active provider) turns raw hits into clean vendors + Indian mobile numbers
    (never fabricated); normalizes/dedups phones; batch-resolves Telegram reachability via
    tg.resolve_phones_batch (one ImportContacts call). Stores sourcing_campaigns.
  - POST /api/sourcing/campaigns/{id}/launch {phones?} -> for approved, Telegram-reachable vendors,
    starts real negotiations via tg.start_deal_internal. Human review before any message (anti-ban).
  - GET /api/sourcing/campaigns[/{id}] -> candidates + live deal status/quotes + best price.
- ai_service.extract_vendors() added (VENDOR_EXTRACTION_SYSTEM, no fabrication, 10-digit IN mobiles).
- telegram_userbot.py: refactored create_deal into start_deal_internal(); added get_client(),
  resolve_phones_batch(). REPLACED flaky live event handler with a reload-proof POLLER
  (_poll_org/_poll_deal every 5s, last_in_id dedupe) — fixes "AI not replying after vendor reply"
  caused by hot-reload dropping Telethon updates (catch_up off).
- frontend: AutoSourcing.js (route /sourcing, nav "Auto-Sourcing"): discover form, vendor list with
  on/off-telegram badges, review + "Negotiate all/selected", live per-vendor chat + best-price banner.
- Verified LIVE: web search returned 7 real Kajaria tile vendors in Bengaluru with real mobiles;
  1 reachable on Telegram correctly flagged, others honestly marked not-on-telegram. Telegram
  negotiation poller confirmed working (vendor quoted 500, AI countered, quote extracted).
- Alerts = dashboard live status + best-price banner (no email/SMS yet).

## PENDING (explicitly requested, not yet built)
- GEMINI provider integration: add backend/ai/ provider abstraction (base/factory/gemini/openai/xai),
  AI_PROVIDER env switch, GEMINI_API_KEY (AQ. format, verified working with model gemini-3.6-flash via
  google-genai 2.20.0), GET /api/ai/status. Route ai_service._complete through the active provider.
  Groundwork done: key+model verified, google-genai installed. NOT wired yet.

## Telegram AI Negotiator (userbot) — Aug 2026
- Requirement: reach a vendor by @username and let AI negotiate to a target price, no simulation.
- Bot API CANNOT DM by username → used Telethon USERBOT (MTProto user account). Playbook via integration_expert.
- backend/telegram_userbot.py:
  - Per-org Telethon client managed in FastAPI lifespan (startup reconnects saved sessions; shutdown disconnects).
  - Account linking: POST /api/telegram/link/start {api_id,api_hash,phone} -> send code; /link/verify {code,password?}
    -> StringSession persisted in db.telegram_accounts (per organization_id). GET /status, POST /unlink.
  - Deals: POST /api/telegram/deals {vendor_username, material, quantity, unit, target_price, max_price, currency, notes}
    resolves @username, sends AI opener. GET /deals, GET /deals/{id}, POST /deals/{id}/stop.
  - Autonomous engine: incoming vendor msg -> ai_negotiate() (Claude Sonnet 5 via EMERGENT_LLM_KEY, model id
    "claude-sonnet-5") returns strict JSON {message, quoted_price, deal_reached, give_up}. HARD guard: never
    closes above max_price (overrides deal_reached). Turn cap 30. Statuses ACTIVE/DEAL_REACHED/FAILED/STOPPED.
- frontend: TelegramNegotiation.js (route /telegram, nav "Telegram AI"): link panel (api_id/hash/phone+code),
  new-deal form, live-polling transcript with target/latest-quote/max header + outcome banner.
- Verified: AI brain tested standalone with real Claude — counters above-max quote (1500 vs max 1100, no accept),
  accepts at/below target (890 vs target 900). Backend endpoints return correct contracts; page mounts.
- NOT yet live-tested end-to-end: requires user's real Telegram API ID/Hash/phone (entered in the UI, OTP login)
  + a real vendor chat. Userbot carries Telegram ToS risk (uses a real user account).
- Dep added: telethon==1.44.0.

## Google login (Emergent-managed) — verified Aug 2026
- iteration_13: backend 14/14 + frontend routing/regression green. Added defensive guard in auth.py
  google_session() (401 if session-data payload lacks email). Full OAuth is user-confirmed working.

## Backlog (P1/P2)
- Exotel App-Bazaar streaming applet → real live in-call AI (needs provider dashboard config).
- WhatsApp Cloud API credentials → real fallback/replies.
- Deep link /direct/:missionId + recent-direct-negotiations list (resume past runs).
- Telegram: encrypt StringSession at rest; optional approval-mode toggle; link Telegram deals to missions/offers.

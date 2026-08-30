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

## Orders tab, nav cleanup, INR plans, 2nd default vendor — Aug 2026 (DONE)
- ORDERS PAGE: /orders (nav "Orders") lists every placed order (vendor, phone, qty, unit price, total,
  status, time) + count/total-value summary. Data from GET /api/telegram/orders.
- NAV CLEANUP (AppLayout): removed Missions, New Mission, Direct Negotiation, Comms Hub, Team.
  Nav now: Command Center, Auto-Sourcing, Telegram AI, Orders, Plans. (Routes kept, only tabs removed.)
- PLANS (billing.py, INR): Explorer Free; Procurement Mission ₹500/month; AI Buyer Pro ₹1000/month.
  Pricing.js renders ₹ for INR.
- 2ND DEFAULT TILE VENDOR: DEFAULT_TILE_VENDORS now = SLV Ceramics (+919980402205) + Ananta Ceramics
  (+919945842205). Both injected first for tile requests; both Telegram-reachable (verified).
- GEMINI QUOTA RESILIENCE: provided GEMINI_API_KEY is FREE-TIER (20 req/day). extract_vendors now
  swallows provider errors and discover() falls back to regex-scraped phones from web hits, so sourcing
  keeps working (incl. default vendors) even when Gemini is 429-rate-limited. NOTE: heavy AI features
  (mission/requirement extraction) will 429 once the daily 20 is hit — user should add billing to the key.

## Orders, Comparison, Default Vendor, Login-persistence fix — Aug 2026 (DONE)
- BUG FIX: Telegram "Start the login first" after entering code. Root cause: pending login (Telethon
  session/auth key + phone_code_hash) was in-memory only and wiped by backend restart between
  /link/start and /link/verify. FIX: persist pending login to Mongo telegram_login in link_start;
  _get_login_client() rebuilds the client from it in link_verify; row deleted on success/expiry.
  Verified iteration_15 (18/18) + linked session survived many restarts.
- HUMAN APPROVAL GATE: POST /api/telegram/deals/{id}/accept — buyer explicitly places the order.
  Atomic claim (find_one_and_update on order_id null) → creates db.orders row, flips deal to
  ORDER_PLACED, sends REAL Telegram order-confirmation to vendor, returns {..., vendor_notified}.
  Guardrails: 404 unknown / 400 no-quote / 400 above-max / 409 already-ordered. GET /api/telegram/orders.
- FINAL COMPARISON / REVERSE AUCTION: AutoSourcing shows ranked vendor final prices (cheapest first,
  winner highlighted) + per-vendor "Accept" modal (price, qty, order total, last chat). Errors surfaced
  (src-accept-error / src-action-error). Telegram tab DealDetail has "Place order @ ..." gate.
- DEFAULT VENDOR: tile-related sourcing (tile/tiles/kajaria/ceramic/vitrified) always injects
  "SLV Ceramics (Muddinapalya)" +919980402205 first; non-tile requests never include it.
- LIVE PROOF: SLV Ceramics negotiation reached ₹420 (<= ₹450 max); order placed at ₹420.

## Gemini active AI provider + Alerts + Reverse Auction — Aug 2026 (DONE)
- backend/ai/ provider abstraction: base_provider.py (AIProvider ABC), gemini_provider.py
  (google-genai 2.20 client.aio, GEMINI_MODEL=gemini-3.6-flash, AFC disabled, status states),
  openai_provider.py (emergentintegrations universal key, LLM_MODEL), xai_provider.py (REST stub,
  NOT_CONFIGURED), provider_factory.py (AI_PROVIDER switch, default emergent).
- ai_service._complete()/is_configured() route through get_provider(); ALL ai_service flows now use
  Gemini. Telegram negotiation stays Claude Sonnet 5 (user choice).
- GET /api/ai/status {active_provider, providers} (no secrets); /api/system/status reports real provider+model.
- env: AI_PROVIDER=gemini, GEMINI_API_KEY, GEMINI_MODEL. iteration_14: backend 15/15, no leakage.
- DEAL ALERTS: _emit_alert() on deal conclusion -> real Telegram DM to buyer's Saved Messages + db.alerts
  row; GET /api/telegram/alerts. (Email/SMS not wired.)
- REVERSE AUCTION: AutoSourcing leaderboard ranks vendor quotes cheapest-first, highlights winner.
- launch() only flips campaign to NEGOTIATING when >=1 deal launched.

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

## Implemented (2026-08-30) — Pricing revamp + Razorpay TEST checkout
- billing.py PLANS: renamed "Procurement Mission"→"Procurement Machine" (₹349→₹69/mo, 80% off),
  "AI Buyer Pro" (₹499→₹119/mo, 76% off), Free (₹0). Added `original_price`; all INR.
- /api/billing/plans + /subscription now report Razorpay state (payment_configured, mode=TEST).
- Frontend Pricing.js: strike-through original price + discount badge; "Choose plan" now loads
  Razorpay checkout.js, POST /billing/orders → opens Razorpay Checkout → handler POST /billing/verify.
  AuthContext gained refreshUser().
- payments.py: verified payment now activates plan for both mission & pro.
- Razorpay TEST keys added to backend/.env (rzp_test_...). Server-side HMAC verify + Mongo storage;
  frontend success is never trusted. Webhook endpoint (pending secret): POST /api/webhooks/razorpay
  — configure RAZORPAY_WEBHOOK_SECRET in Razorpay dashboard to enable server-push confirmation.
- Env note: fresh checkout had NO .env files and was crashing (missing pyaes). Reconstructed
  backend/.env + frontend/.env, installed pyaes==1.6.1.
- Tested: iteration_16 (9/9 backend + frontend E2E, 100%). Legacy Stripe stubs left in billing.py (unused).

## Implemented (2026-08-30) — Default tile vendors + hardened auto-sourcing
- auto_sourcing.py DEFAULT_TILE_VENDORS now: SLV Ceramics & Ananta Ceramics, BOTH phone
  +919945842205 (per user). Each discovery candidate gets a unique `id`.
- Tile/ceramic/vitrified/kajaria searches ALWAYS inject both defaults (even if web search
  returns nothing — no 502 when defaults exist); non-tile searches do not.
- launch() dedups by telegram_user_id: the same Telegram contact is never messaged twice
  (2nd default -> SKIPPED_DUPLICATE) — prevents thread corruption / AI double-replies.
- AutoSourcing.js keys candidates/leaderboard/selected/openDeal by candidate id (c.id||c.phone)
  so two same-number cards render without duplicate React keys. Live chat + Final Comparison
  (reverse auction) + accept-order flow unchanged and intact.
- NOTE: live Telegram negotiation requires the org to LINK its Telegram userbot account in the
  "Telegram AI" tab (api_id/api_hash/phone + OTP). Until linked, vendors show but cannot be messaged.
- Tested: iteration_18 (14/14 backend + frontend E2E). Removed stale iteration_15 default test.

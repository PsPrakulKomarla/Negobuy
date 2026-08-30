import React, { useState, useEffect, useRef, useCallback } from "react";
import { Send, Link2, ShieldCheck, Loader2, X, Bot, User, CheckCircle2, XCircle, StopCircle } from "lucide-react";
import api, { formatApiError } from "../lib/api";
import {
  Button, Input, Textarea, Card, SectionLabel, Spinner, Badge, motion, fadeUp,
} from "../components/ui";

const STATUS_META = {
  ACTIVE: { label: "Negotiating", cls: "text-yellow-300 border-yellow-400/30 bg-yellow-400/10" },
  DEAL_REACHED: { label: "Deal Reached", cls: "text-secondary border-secondary/30 bg-secondary/10" },
  ORDER_PLACED: { label: "Order Placed", cls: "text-secondary border-secondary/40 bg-secondary/15" },
  FAILED: { label: "No Deal", cls: "text-accent border-accent/30 bg-accent/10" },
  STOPPED: { label: "Stopped", cls: "text-white/50 border-white/15 bg-white/5" },
};

function StatusChip({ status }) {
  const m = STATUS_META[status] || STATUS_META.STOPPED;
  return (
    <span className={`inline-flex items-center gap-1.5 text-[10px] font-mono tracking-wider uppercase px-3 py-1 rounded-full border ${m.cls}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {m.label}
    </span>
  );
}

// ------------------------- Account linking ------------------------- //
function LinkPanel({ status, onLinked }) {
  const [phase, setPhase] = useState("creds"); // creds | code
  const [apiId, setApiId] = useState("");
  const [apiHash, setApiHash] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const start = async (e) => {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const { data } = await api.post("/telegram/link/start", {
        api_id: Number(apiId), api_hash: apiHash.trim(), phone: phone.trim(),
      });
      if (data.status === "already_authorized") { onLinked(); return; }
      setPhase("code");
    } catch (e2) {
      setErr(formatApiError(e2.response?.data?.detail) || e2.message);
    } finally { setBusy(false); }
  };

  const verify = async (e) => {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      await api.post("/telegram/link/verify", { code: code.trim(), password: password || null });
      onLinked();
    } catch (e2) {
      const d = e2.response?.data?.detail;
      setErr(formatApiError(d) || e2.message);
    } finally { setBusy(false); }
  };

  return (
    <Card className="p-6 sm:p-8 border border-white/10">
      <div className="flex items-center gap-3 mb-2">
        <div className="w-10 h-10 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center">
          <Link2 size={18} className="text-primary" />
        </div>
        <div>
          <h3 className="font-display font-bold text-lg">Link your Telegram account</h3>
          <p className="text-sm text-white/50">The AI negotiates from your own account so it can DM vendors by @username.</p>
        </div>
      </div>

      <div className="text-xs text-white/40 bg-white/5 border border-white/10 rounded-xl p-3 my-4 font-mono leading-relaxed">
        Get your API ID & API Hash from my.telegram.org → API development tools. Your credentials
        and session stay on this server and are never shown to vendors.
      </div>

      {phase === "creds" ? (
        <form onSubmit={start} className="space-y-4">
          <Input label="API ID" value={apiId} onChange={(e) => setApiId(e.target.value)}
            placeholder="1234567" inputMode="numeric" data-testid="tg-api-id" required />
          <Input label="API Hash" value={apiHash} onChange={(e) => setApiHash(e.target.value)}
            placeholder="0123456789abcdef0123456789abcdef" data-testid="tg-api-hash" required />
          <Input label="Phone (international)" value={phone} onChange={(e) => setPhone(e.target.value)}
            placeholder="+14155550123" data-testid="tg-phone" required />
          {err && <div data-testid="tg-link-error" className="text-sm text-accent bg-accent/10 border border-accent/20 rounded-xl px-4 py-3">{err}</div>}
          <Button type="submit" size="lg" className="w-full" disabled={busy} data-testid="tg-send-code-btn">
            {busy ? <Spinner /> : <Send size={16} />} Send login code
          </Button>
        </form>
      ) : (
        <form onSubmit={verify} className="space-y-4">
          <p className="text-sm text-white/60">Enter the code Telegram just sent to <span className="text-primary">{phone}</span>.</p>
          <Input label="Login code" value={code} onChange={(e) => setCode(e.target.value)}
            placeholder="12345" inputMode="numeric" data-testid="tg-code" required />
          <Input label="Two-factor password (if enabled)" type="password" value={password}
            onChange={(e) => setPassword(e.target.value)} placeholder="Only if you set one" data-testid="tg-2fa" />
          {err && <div data-testid="tg-verify-error" className="text-sm text-accent bg-accent/10 border border-accent/20 rounded-xl px-4 py-3">{err}</div>}
          <div className="flex gap-3">
            <Button type="button" variant="ghost" onClick={() => { setPhase("creds"); setErr(""); }}>Back</Button>
            <Button type="submit" size="lg" className="flex-1" disabled={busy} data-testid="tg-verify-btn">
              {busy ? <Spinner /> : <ShieldCheck size={16} />} Verify & link
            </Button>
          </div>
        </form>
      )}
    </Card>
  );
}

// ------------------------- New deal form ------------------------- //
function NewDealForm({ onCreated }) {
  const [f, setF] = useState({ vendor_username: "", vendor_name: "", material: "", quantity: "", unit: "",
    target_price: "", max_price: "", currency: "INR", notes: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const { data } = await api.post("/telegram/deals", {
        vendor_username: f.vendor_username.trim(),
        vendor_name: f.vendor_name.trim() || null,
        material: f.material.trim(),
        quantity: f.quantity ? Number(f.quantity) : null,
        unit: f.unit.trim() || null,
        target_price: Number(f.target_price),
        max_price: Number(f.max_price),
        currency: f.currency,
        notes: f.notes.trim() || null,
      });
      setF({ vendor_username: "", vendor_name: "", material: "", quantity: "", unit: "", target_price: "",
        max_price: "", currency: "INR", notes: "" });
      onCreated(data);
    } catch (e2) {
      setErr(formatApiError(e2.response?.data?.detail) || e2.message);
    } finally { setBusy(false); }
  };

  return (
    <Card className="p-6 sm:p-8 border border-white/10">
      <SectionLabel>Start a negotiation</SectionLabel>
      <form onSubmit={submit} className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <Input label="Vendor @username or phone" value={f.vendor_username} onChange={set("vendor_username")}
            placeholder="@handle or +9199…" data-testid="deal-username" required />
          <Input label="Vendor name (optional)" value={f.vendor_name} onChange={set("vendor_name")}
            placeholder="e.g. Srinivasa Gowda" data-testid="deal-vendor-name" />
        </div>
        <div className="text-[11px] text-white/40 -mt-2">
          Phone numbers must belong to a Telegram account. 10-digit numbers are treated as Indian (+91).
        </div>
        <Input label="Material / product" value={f.material} onChange={set("material")}
          placeholder="e.g. Kajaria floor tiles" data-testid="deal-material" required />
        <div className="grid grid-cols-2 gap-4">
          <Input label="Quantity" value={f.quantity} onChange={set("quantity")} inputMode="decimal"
            placeholder="500" data-testid="deal-qty" />
          <Input label="Unit" value={f.unit} onChange={set("unit")} placeholder="pieces / kg / tons"
            data-testid="deal-unit" />
        </div>
        <div className="grid grid-cols-3 gap-4">
          <Input label="Target price" value={f.target_price} onChange={set("target_price")} inputMode="decimal"
            placeholder="900" data-testid="deal-target" required />
          <Input label="Max price" value={f.max_price} onChange={set("max_price")} inputMode="decimal"
            placeholder="1100" data-testid="deal-max" required />
          <Input label="Currency" value={f.currency} onChange={set("currency")} placeholder="INR"
            data-testid="deal-currency" />
        </div>
        <Textarea label="Notes for the AI (optional)" rows={2} value={f.notes} onChange={set("notes")}
          placeholder="Delivery timeline, quality specs, payment terms…" data-testid="deal-notes" />
        <div className="text-xs text-white/40 bg-white/5 border border-white/10 rounded-xl px-4 py-3">
          The AI will chat autonomously to reach your <span className="text-primary">target</span> and will
          <span className="text-secondary"> never</span> agree above your <span className="text-accent">max price</span>.
        </div>
        {err && <div data-testid="deal-error" className="text-sm text-accent bg-accent/10 border border-accent/20 rounded-xl px-4 py-3">{err}</div>}
        <Button type="submit" size="lg" className="w-full" disabled={busy} data-testid="start-deal-btn">
          {busy ? <><Spinner /> Reaching out…</> : <><Send size={16} /> Send first message & negotiate</>}
        </Button>
      </form>
    </Card>
  );
}

// ------------------------- Deal detail ------------------------- //
function DealDetail({ dealId, onClose }) {
  const [deal, setDeal] = useState(null);
  const scrollRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get(`/telegram/deals/${dealId}`);
      setDeal(data);
    } catch (e) { /* ignore */ }
  }, [dealId]);

  useEffect(() => {
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [deal?.transcript?.length]);

  const stop = async () => {
    await api.post(`/telegram/deals/${dealId}/stop`);
    load();
  };

  const [accepting, setAccepting] = useState(false);
  const onAccept = async () => {
    if (!window.confirm(`Place the order with this vendor at ${deal.currency} ${deal.agreed_price ?? deal.latest_quote}? A confirmation will be sent to them on Telegram.`)) return;
    setAccepting(true);
    try {
      await api.post(`/telegram/deals/${dealId}/accept`);
      await load();
    } catch (e) { window.alert(formatApiError(e.response?.data?.detail) || e.message); }
    finally { setAccepting(false); }
  };

  if (!deal) return <Card className="p-8 flex justify-center"><Spinner className="w-6 h-6" /></Card>;

  const cur = deal.currency || "";
  return (
    <Card className="border border-white/10 overflow-hidden flex flex-col h-[70vh]" data-testid="deal-detail">
      <div className="flex items-center justify-between px-5 py-4 border-b hairline">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-display font-bold truncate">@{deal.vendor_username}</span>
            <StatusChip status={deal.status} />
          </div>
          <div className="text-xs text-white/50 truncate">{deal.material}</div>
        </div>
        <button onClick={onClose} className="text-white/40 hover:text-white" data-testid="deal-close">
          <X size={18} />
        </button>
      </div>

      <div className="grid grid-cols-3 gap-px bg-white/5 text-center">
        <div className="bg-void py-3">
          <div className="text-[10px] uppercase tracking-wider text-white/40 font-mono">Target</div>
          <div className="text-sm font-semibold text-primary">{cur} {deal.target_price}</div>
        </div>
        <div className="bg-void py-3">
          <div className="text-[10px] uppercase tracking-wider text-white/40 font-mono">Latest quote</div>
          <div className="text-sm font-semibold text-yellow-300" data-testid="deal-latest-quote">
            {deal.latest_quote != null ? `${cur} ${deal.latest_quote}` : "—"}
          </div>
        </div>
        <div className="bg-void py-3">
          <div className="text-[10px] uppercase tracking-wider text-white/40 font-mono">Max</div>
          <div className="text-sm font-semibold text-accent">{cur} {deal.max_price}</div>
        </div>
      </div>

      {deal.status === "DEAL_REACHED" && (
        <div className="bg-secondary/10 border-y border-secondary/20 px-5 py-3 flex items-center gap-2 text-secondary text-sm" data-testid="deal-outcome">
          <CheckCircle2 size={16} /> Deal reached at {cur} {deal.agreed_price ?? deal.latest_quote}.
        </div>
      )}
      {deal.status === "ORDER_PLACED" && (
        <div className="bg-secondary/15 border-y border-secondary/30 px-5 py-3 flex items-center gap-2 text-secondary text-sm" data-testid="deal-outcome">
          <CheckCircle2 size={16} /> Order placed at {cur} {deal.agreed_price ?? deal.latest_quote}.
        </div>
      )}
      {deal.status === "FAILED" && (
        <div className="bg-accent/10 border-y border-accent/20 px-5 py-3 flex items-center gap-2 text-accent text-sm" data-testid="deal-outcome">
          <XCircle size={16} /> No deal reached within your limits.
        </div>
      )}

      {deal.latest_quote != null && deal.status !== "ORDER_PLACED" && (
        <div className="bg-white/5 border-y border-white/10 px-5 py-3 flex items-center justify-between gap-3">
          <span className="text-xs text-white/50">Review the price &amp; chat, then place the order (nothing is ordered automatically).</span>
          <Button size="sm" onClick={onAccept} disabled={accepting} data-testid="deal-accept-btn">
            {accepting ? <Spinner /> : <CheckCircle2 size={14} />} Place order @ {cur} {deal.agreed_price ?? deal.latest_quote}
          </Button>
        </div>
      )}

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
        {(deal.transcript || []).map((m, i) => (
          <div key={i} className={`flex gap-2 ${m.role === "ai" ? "justify-end" : "justify-start"}`}>
            {m.role === "vendor" && <div className="w-7 h-7 rounded-full bg-white/10 flex items-center justify-center shrink-0"><User size={14} className="text-white/60" /></div>}
            <div className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm ${m.role === "ai" ? "bg-primary/15 border border-primary/25 text-white" : "bg-white/5 border border-white/10 text-white/80"}`}>
              {m.text}
            </div>
            {m.role === "ai" && <div className="w-7 h-7 rounded-full bg-primary/20 flex items-center justify-center shrink-0"><Bot size={14} className="text-primary" /></div>}
          </div>
        ))}
        {(!deal.transcript || deal.transcript.length === 0) && (
          <div className="text-center text-white/40 text-sm py-10">No messages yet.</div>
        )}
      </div>

      {deal.status === "ACTIVE" && (
        <div className="px-5 py-3 border-t hairline flex items-center justify-between">
          <span className="text-xs text-white/40 font-mono flex items-center gap-2">
            <Loader2 size={13} className="animate-spin" /> AI is negotiating — waiting for vendor replies…
          </span>
          <Button variant="danger" size="sm" onClick={stop} data-testid="stop-deal-btn">
            <StopCircle size={14} /> Stop
          </Button>
        </div>
      )}
    </Card>
  );
}

// ------------------------- Page ------------------------- //
export default function TelegramNegotiation() {
  const [status, setStatus] = useState(null);
  const [deals, setDeals] = useState([]);
  const [active, setActive] = useState(null);

  const loadStatus = useCallback(async () => {
    try { const { data } = await api.get("/telegram/status"); setStatus(data); }
    catch { setStatus({ authorized: false, linked: false }); }
  }, []);

  const loadDeals = useCallback(async () => {
    try { const { data } = await api.get("/telegram/deals"); setDeals(data); }
    catch { /* ignore */ }
  }, []);

  useEffect(() => { loadStatus(); loadDeals(); }, [loadStatus, loadDeals]);
  useEffect(() => {
    const t = setInterval(loadDeals, 5000);
    return () => clearInterval(t);
  }, [loadDeals]);

  const unlink = async () => {
    await api.post("/telegram/unlink");
    loadStatus();
  };

  return (
    <div className="max-w-6xl mx-auto px-5 sm:px-8 py-8">
      <motion.div {...fadeUp} className="mb-8">
        <div className="flex items-center gap-2 text-xs tracking-[0.3em] uppercase text-primary/80 font-mono mb-2">
          <Bot size={14} /> Telegram AI Negotiator
        </div>
        <h1 className="font-display text-3xl sm:text-4xl font-bold tracking-tight">Negotiate on Telegram</h1>
        <p className="text-white/50 mt-2 max-w-2xl">
          Give a vendor's @username, the material and your price limits. The AI messages them from your
          account and negotiates for real — no scripts, no simulation.
        </p>
      </motion.div>

      {!status ? (
        <div className="flex justify-center py-20"><Spinner className="w-7 h-7" /></div>
      ) : !status.authorized ? (
        <div className="max-w-lg"><LinkPanel status={status} onLinked={loadStatus} /></div>
      ) : (
        <div className="grid lg:grid-cols-2 gap-6">
          <div className="space-y-6">
            <Card className="p-4 border border-secondary/20 bg-secondary/5 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-full bg-secondary/15 border border-secondary/30 flex items-center justify-center">
                  <ShieldCheck size={16} className="text-secondary" />
                </div>
                <div>
                  <div className="text-sm font-medium">Telegram linked</div>
                  <div className="text-xs text-white/50">
                    {status.username ? `@${status.username}` : status.phone}
                  </div>
                </div>
              </div>
              <Button variant="ghost" size="sm" onClick={unlink} data-testid="tg-unlink-btn">Unlink</Button>
            </Card>
            <NewDealForm onCreated={(d) => { loadDeals(); setActive(d.id); }} />
          </div>

          <div>
            {active ? (
              <DealDetail dealId={active} onClose={() => setActive(null)} />
            ) : (
              <Card className="border border-white/10 p-2">
                <div className="px-4 py-3 flex items-center justify-between">
                  <span className="text-xs tracking-[0.2em] uppercase text-white/50 font-mono">Negotiations</span>
                  <Badge>{deals.length}</Badge>
                </div>
                <div className="space-y-1 max-h-[65vh] overflow-y-auto">
                  {deals.length === 0 && (
                    <div className="text-center text-white/40 text-sm py-16">No negotiations yet.</div>
                  )}
                  {deals.map((d) => (
                    <button key={d.id} onClick={() => setActive(d.id)} data-testid={`deal-row-${d.id}`}
                      className="w-full text-left px-4 py-3 rounded-xl hover:bg-white/5 transition-colors flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium truncate">@{d.vendor_username}</span>
                          <StatusChip status={d.status} />
                        </div>
                        <div className="text-xs text-white/45 truncate">{d.material}</div>
                      </div>
                      <div className="text-right shrink-0">
                        <div className="text-[10px] uppercase tracking-wider text-white/35 font-mono">quote</div>
                        <div className="text-sm font-semibold text-yellow-300">
                          {d.latest_quote != null ? `${d.currency} ${d.latest_quote}` : "—"}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

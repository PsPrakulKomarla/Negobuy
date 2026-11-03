import React, { useState, useEffect, useCallback } from "react";
import {
  Search, Send, Loader2, CheckCircle2, XCircle, Phone, MapPin, Bot, User,
  Sparkles, TrendingDown, AlertCircle, ArrowLeft,
} from "lucide-react";
import { Link } from "react-router-dom";
import api, { formatApiError } from "../lib/api";
import {
  Button, Input, Textarea, Card, SectionLabel, Spinner, Badge, motion, fadeUp,
} from "../components/ui";

const DEAL_META = {
  ACTIVE: { label: "Negotiating", cls: "text-yellow-300 border-yellow-400/30 bg-yellow-400/10" },
  DEAL_REACHED: { label: "Deal", cls: "text-secondary border-secondary/30 bg-secondary/10" },
  ORDER_PLACED: { label: "Ordered", cls: "text-secondary border-secondary/40 bg-secondary/15" },
  FAILED: { label: "No Deal", cls: "text-accent border-accent/30 bg-accent/10" },
  STOPPED: { label: "Stopped", cls: "text-white/50 border-white/15 bg-white/5" },
};

function DealChip({ status }) {
  const m = DEAL_META[status];
  if (!m) return null;
  return <span className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded-full border ${m.cls}`}>{m.label}</span>;
}

// ---------------- Discover form ---------------- //
function DiscoverForm({ onDone }) {
  const [f, setF] = useState({ material: "", specs: "", quantity: "", unit: "",
    target_price: "", max_price: "", currency: "INR", location: "", max_vendors: 10 });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const { data } = await api.post("/sourcing/discover", {
        material: f.material.trim(), specs: f.specs.trim() || null,
        quantity: f.quantity ? Number(f.quantity) : null, unit: f.unit.trim() || null,
        target_price: Number(f.target_price), max_price: Number(f.max_price),
        currency: f.currency, location: f.location.trim() || null,
        max_vendors: Number(f.max_vendors) || 10,
      });
      onDone(data);
    } catch (e2) {
      setErr(formatApiError(e2.response?.data?.detail) || e2.message);
    } finally { setBusy(false); }
  };

  return (
    <Card className="p-6 sm:p-8 border border-white/10">
      <SectionLabel>What do you need to buy?</SectionLabel>
      <form onSubmit={submit} className="space-y-4">
        <Input label="Material / product" value={f.material} onChange={set("material")}
          placeholder="e.g. Kajaria vitrified floor tiles" data-testid="src-material" required />
        <Textarea label="Specs (optional)" rows={2} value={f.specs} onChange={set("specs")}
          placeholder="size, grade, finish, brand…" data-testid="src-specs" />
        <div className="grid grid-cols-3 gap-4">
          <Input label="Quantity" value={f.quantity} onChange={set("quantity")} inputMode="decimal"
            placeholder="1000" data-testid="src-qty" />
          <Input label="Unit" value={f.unit} onChange={set("unit")} placeholder="sq ft" data-testid="src-unit" />
          <Input label="City / location" value={f.location} onChange={set("location")}
            placeholder="Bengaluru" data-testid="src-location" />
        </div>
        <div className="grid grid-cols-3 gap-4">
          <Input label="Target price" value={f.target_price} onChange={set("target_price")} inputMode="decimal"
            placeholder="420" data-testid="src-target" required />
          <Input label="Max price" value={f.max_price} onChange={set("max_price")} inputMode="decimal"
            placeholder="450" data-testid="src-max" required />
          <Input label="Max vendors" value={f.max_vendors} onChange={set("max_vendors")} inputMode="numeric"
            placeholder="10" data-testid="src-maxvendors" />
        </div>
        <Input label="Currency" value={f.currency} onChange={set("currency")} placeholder="INR" data-testid="src-currency" />
        {err && <div data-testid="src-error" className="text-sm text-accent bg-accent/10 border border-accent/20 rounded-xl px-4 py-3">{err}</div>}
        <Button type="submit" size="lg" className="w-full" disabled={busy} data-testid="src-discover-btn">
          {busy ? <><Spinner /> Searching the web for vendors…</> : <><Search size={16} /> Find vendors</>}
        </Button>
      </form>
    </Card>
  );
}

// ---------------- Campaign detail ---------------- //
function CampaignView({ campaignId, onBack }) {
  const [camp, setCamp] = useState(null);
  const [selected, setSelected] = useState({});
  const [launching, setLaunching] = useState(false);
  const [openDeal, setOpenDeal] = useState(null);
  const [confirmC, setConfirmC] = useState(null);
  const [accepting, setAccepting] = useState(false);
  const [actionErr, setActionErr] = useState("");

  const load = useCallback(async () => {
    try { const { data } = await api.get(`/sourcing/campaigns/${campaignId}`); setCamp(data); }
    catch { /* ignore */ }
  }, [campaignId]);

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  if (!camp) return <div className="flex justify-center py-20"><Spinner className="w-7 h-7" /></div>;

  const reachable = camp.candidates.filter((c) => c.telegram_reachable);
  const toggle = (phone) => setSelected((s) => ({ ...s, [phone]: !s[phone] }));
  const anyLaunched = camp.candidates.some((c) => c.deal_id);

  // Reverse auction: rank vendors that have a live quote, cheapest first.
  const ranked = camp.candidates
    .filter((c) => (c.agreed_price ?? c.latest_quote) != null)
    .map((c) => ({ ...c, q: c.agreed_price ?? c.latest_quote }))
    .sort((a, b) => a.q - b.q);

  const acceptOrder = async () => {
    if (!confirmC?.deal_id) return;
    setAccepting(true); setActionErr("");
    try {
      await api.post(`/telegram/deals/${confirmC.deal_id}/accept`);
      setConfirmC(null);
      await load();
    } catch (e) {
      setActionErr(formatApiError(e.response?.data?.detail) || e.message);
    }
    finally { setAccepting(false); }
  };

  const launch = async (phones) => {
    setLaunching(true); setActionErr("");
    try {
      await api.post(`/sourcing/campaigns/${campaignId}/launch`, { phones: phones || null });
      await load();
      setSelected({});
    } catch (e) {
      setActionErr(formatApiError(e.response?.data?.detail) || e.message);
    }
    finally { setLaunching(false); }
  };

  return (
    <div>
      <button onClick={onBack} className="flex items-center gap-2 text-white/50 hover:text-white text-sm mb-4" data-testid="src-back">
        <ArrowLeft size={16} /> Back to sourcing
      </button>

      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h2 className="font-display text-2xl font-bold">{camp.material}</h2>
          <p className="text-sm text-white/50">
            {camp.quantity ? `${camp.quantity} ${camp.unit || ""} · ` : ""}target {camp.currency} {camp.target_price} · max {camp.currency} {camp.max_price}
            {camp.location ? ` · ${camp.location}` : ""}
          </p>
        </div>
        {camp.best && (
          <div className="flex items-center gap-2 bg-secondary/10 border border-secondary/25 rounded-xl px-4 py-2" data-testid="src-best">
            <TrendingDown size={16} className="text-secondary" />
            <span className="text-sm">Best: <b className="text-secondary">{camp.currency} {camp.best.price}</b> — {camp.best.vendor}</span>
          </div>
        )}
      </div>

      {!camp.telegram_linked && (
        <Card className="p-4 border border-accent/25 bg-accent/5 mb-4 flex items-center gap-3" data-testid="src-link-warning">
          <AlertCircle size={18} className="text-accent shrink-0" />
          <div className="text-sm text-white/70">
            Link your Telegram account in the <Link to="/telegram" className="text-primary">Telegram AI</Link> tab to message these vendors.
          </div>
        </Card>
      )}

      {ranked.length > 0 && (
        <Card className="p-5 border border-primary/20 bg-primary/5 mb-4" data-testid="src-leaderboard">
          <div className="flex items-center gap-2 mb-3">
            <TrendingDown size={16} className="text-primary" />
            <span className="text-xs tracking-[0.25em] uppercase text-primary/80 font-mono">Final Comparison · Reverse Auction</span>
          </div>
          <div className="space-y-2">
            {ranked.map((c, i) => {
              const winner = i === 0;
              const ordered = c.deal_status === "ORDER_PLACED";
              const canAccept = c.deal_id && !ordered;
              return (
                <div key={c.id || c.phone} data-testid={`src-rank-${i}`}
                  className={`flex items-center justify-between gap-3 rounded-xl px-4 py-2.5 border ${winner ? "border-secondary/40 bg-secondary/10" : "border-white/10 bg-white/5"}`}>
                  <div className="flex items-center gap-3 min-w-0">
                    <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${winner ? "bg-secondary/25 text-secondary" : "bg-white/10 text-white/50"}`}>{i + 1}</span>
                    <span className="font-medium truncate">{c.name}</span>
                    {winner && !ordered && <Badge className="text-secondary border-secondary/30">best</Badge>}
                    <DealChip status={c.deal_status} />
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className={`text-sm font-bold ${winner ? "text-secondary" : "text-yellow-300"}`}>{camp.currency} {c.q}</span>
                    {canAccept && (
                      <Button size="sm" variant={winner ? "primary" : "secondary"}
                        onClick={() => setConfirmC(c)} data-testid={`src-accept-${c.id || c.phone}`}>
                        <CheckCircle2 size={14} /> Accept
                      </Button>
                    )}
                    {ordered && <Badge className="text-secondary border-secondary/40">order placed</Badge>}
                  </div>
                </div>
              );
            })}
          </div>
          <p className="text-[11px] text-white/40 mt-3">Nothing is ordered automatically. Review each vendor's final price and chat, then Accept to place the order.</p>
        </Card>
      )}

      {confirmC && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" data-testid="src-accept-modal">
          <Card className="w-full max-w-lg p-6 border border-white/15">
            <h3 className="font-display font-bold text-lg mb-1">Confirm order</h3>
            <p className="text-sm text-white/50 mb-4">You're placing a real order. A confirmation will be sent to the vendor on Telegram.</p>
            <div className="rounded-xl bg-white/5 border border-white/10 p-4 mb-4 space-y-1 text-sm">
              <div className="flex justify-between"><span className="text-white/50">Vendor</span><span className="font-medium">{confirmC.name}</span></div>
              <div className="flex justify-between"><span className="text-white/50">Material</span><span>{camp.material}</span></div>
              {camp.quantity && <div className="flex justify-between"><span className="text-white/50">Quantity</span><span>{camp.quantity} {camp.unit}</span></div>}
              <div className="flex justify-between"><span className="text-white/50">Final price</span><span className="font-bold text-secondary">{camp.currency} {confirmC.agreed_price ?? confirmC.latest_quote}{camp.unit ? `/${camp.unit}` : ""}</span></div>
              {camp.quantity && <div className="flex justify-between"><span className="text-white/50">Order total</span><span className="font-bold">{camp.currency} {((confirmC.agreed_price ?? confirmC.latest_quote) * camp.quantity).toLocaleString()}</span></div>}
            </div>
            {confirmC.transcript && confirmC.transcript.length > 0 && (
              <div className="max-h-40 overflow-y-auto rounded-xl bg-void/60 border border-white/10 p-3 mb-4 space-y-1.5">
                {confirmC.transcript.slice(-6).map((m, i) => (
                  <div key={i} className={`text-xs ${m.role === "ai" ? "text-primary/80" : "text-white/70"}`}>
                    <b>{m.role === "ai" ? "You" : "Vendor"}:</b> {m.text}
                  </div>
                ))}
              </div>
            )}
            {actionErr && <div className="text-sm text-accent bg-accent/10 border border-accent/20 rounded-xl px-4 py-2.5 mb-3" data-testid="src-accept-error">{actionErr}</div>}
            <div className="flex gap-3">
              <Button variant="ghost" onClick={() => { setConfirmC(null); setActionErr(""); }} data-testid="src-accept-cancel">Cancel</Button>
              <Button className="flex-1" onClick={acceptOrder} disabled={accepting} data-testid="src-accept-confirm">
                {accepting ? <Spinner /> : <CheckCircle2 size={16} />} Confirm & place order
              </Button>
            </div>
          </Card>
        </div>
      )}

      {actionErr && !confirmC && (
        <div className="text-sm text-accent bg-accent/10 border border-accent/20 rounded-xl px-4 py-2.5 mb-4" data-testid="src-action-error">{actionErr}</div>
      )}

      {camp.telegram_linked && reachable.length > 0 && !anyLaunched && (
        <div className="flex items-center gap-3 mb-4">
          <Button onClick={() => launch(null)} disabled={launching} data-testid="src-launch-all">
            {launching ? <Spinner /> : <Send size={15} />} Negotiate all {reachable.length} reachable
          </Button>
          <Button variant="secondary" disabled={launching || !Object.values(selected).some(Boolean)}
            onClick={() => launch(camp.candidates.filter((c) => selected[c.id]).map((c) => c.phone))} data-testid="src-launch-selected">
            Negotiate selected
          </Button>
        </div>
      )}

      <div className="space-y-2">
        {camp.candidates.length === 0 && (
          <Card className="p-8 text-center text-white/50">No vendors with usable mobile numbers were found. Try different keywords or a city.</Card>
        )}
        {camp.candidates.map((c) => (
          <Card key={c.id || c.phone} className="p-4 border border-white/10" data-testid={`src-vendor-${c.id || c.phone}`}>
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-3 min-w-0">
                {camp.telegram_linked && !c.deal_id && c.telegram_reachable && (
                  <input type="checkbox" checked={!!selected[c.id]} onChange={() => toggle(c.id)}
                    className="mt-1 accent-cyan-400" data-testid={`src-check-${c.id || c.phone}`} />
                )}
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium truncate">{c.name}</span>
                    {c.telegram_reachable === true && <Badge className="text-secondary border-secondary/30">on telegram</Badge>}
                    {c.telegram_reachable === false && <Badge className="text-white/40">not on telegram</Badge>}
                    {c.deal_status && <DealChip status={c.deal_status} />}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-white/50 mt-1 flex-wrap">
                    <span className="flex items-center gap-1"><Phone size={12} /> {c.phone}</span>
                    {c.location && <span className="flex items-center gap-1"><MapPin size={12} /> {c.location}</span>}
                    {c.url && <a href={c.url} target="_blank" rel="noreferrer" className="text-primary/70 hover:text-primary truncate max-w-[220px]">source</a>}
                  </div>
                  {c.note && <div className="text-xs text-white/40 mt-1">{c.note}</div>}
                </div>
              </div>
              <div className="text-right shrink-0">
                {c.latest_quote != null && (
                  <>
                    <div className="text-[10px] uppercase tracking-wider text-white/35 font-mono">quote</div>
                    <div className="text-sm font-semibold text-yellow-300">{camp.currency} {c.agreed_price ?? c.latest_quote}</div>
                  </>
                )}
                {c.deal_id && (
                  <button onClick={() => setOpenDeal(openDeal === c.id ? null : c.id)}
                    className="text-xs text-primary/80 hover:text-primary mt-1" data-testid={`src-view-${c.id || c.phone}`}>
                    {openDeal === c.id ? "hide chat" : "view chat"}
                  </button>
                )}
              </div>
            </div>

            {openDeal === c.id && c.transcript && (
              <div className="mt-3 pt-3 border-t hairline space-y-2 max-h-64 overflow-y-auto">
                {c.transcript.map((m, i) => (
                  <div key={i} className={`flex gap-2 ${m.role === "ai" ? "justify-end" : "justify-start"}`}>
                    {m.role === "vendor" && <div className="w-6 h-6 rounded-full bg-white/10 flex items-center justify-center shrink-0"><User size={12} className="text-white/60" /></div>}
                    <div className={`max-w-[75%] rounded-xl px-3 py-2 text-xs ${m.role === "ai" ? "bg-primary/15 border border-primary/25" : "bg-white/5 border border-white/10 text-white/80"}`}>{m.text}</div>
                    {m.role === "ai" && <div className="w-6 h-6 rounded-full bg-primary/20 flex items-center justify-center shrink-0"><Bot size={12} className="text-primary" /></div>}
                  </div>
                ))}
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}

// ---------------- Page ---------------- //
export default function AutoSourcing() {
  const [campaigns, setCampaigns] = useState([]);
  const [active, setActive] = useState(null);

  const load = useCallback(async () => {
    try { const { data } = await api.get("/sourcing/campaigns"); setCampaigns(data); }
    catch { /* ignore */ }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="max-w-5xl mx-auto px-5 sm:px-8 py-8">
      <motion.div {...fadeUp} className="mb-8">
        <div className="flex items-center gap-2 text-xs tracking-[0.3em] uppercase text-primary/80 font-mono mb-2">
          <Sparkles size={14} /> Auto-Sourcing Agent
        </div>
        <h1 className="font-display text-3xl sm:text-4xl font-bold tracking-tight">Find vendors & negotiate — automatically</h1>
        <p className="text-white/50 mt-2 max-w-2xl">
          Describe what you need. The AI searches the web for suppliers, pulls their mobile numbers,
          checks who's on Telegram, then negotiates with the ones you approve — all the way to a price.
        </p>
      </motion.div>

      {active ? (
        <CampaignView campaignId={active} onBack={() => { setActive(null); load(); }} />
      ) : (
        <div className="grid lg:grid-cols-2 gap-6">
          <DiscoverForm onDone={(c) => { load(); setActive(c.id); }} />
          <Card className="border border-white/10 p-2">
            <div className="px-4 py-3 flex items-center justify-between">
              <span className="text-xs tracking-[0.2em] uppercase text-white/50 font-mono">Sourcing runs</span>
              <Badge>{campaigns.length}</Badge>
            </div>
            <div className="space-y-1 max-h-[70vh] overflow-y-auto">
              {campaigns.length === 0 && <div className="text-center text-white/40 text-sm py-16">No sourcing runs yet.</div>}
              {campaigns.map((c) => {
                const reachable = (c.candidates || []).filter((x) => x.telegram_reachable).length;
                const negotiating = (c.candidates || []).filter((x) => x.deal_id).length;
                return (
                  <button key={c.id} onClick={() => setActive(c.id)} data-testid={`src-camp-${c.id}`}
                    className="w-full text-left px-4 py-3 rounded-xl hover:bg-white/5 transition-colors">
                    <div className="font-medium truncate">{c.material}</div>
                    <div className="text-xs text-white/45">
                      {(c.candidates || []).length} found · {reachable} on Telegram{negotiating ? ` · ${negotiating} negotiating` : ""}
                    </div>
                  </button>
                );
              })}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

import React, { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  MessagesSquare, Send, Bot, User, Cog, Plus, ShieldAlert, Radio,
  CheckCircle2, TrendingDown, ArrowLeft, X,
} from "lucide-react";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { Button, Card, Input, Spinner, SectionLabel, Badge } from "../components/ui";

const CHANNEL_META = {
  telegram: { label: "Telegram", color: "#29b6f6" },
  whatsapp: { label: "WhatsApp", color: "#25d366" },
  instagram: { label: "Instagram", color: "#e1306c" },
};
const STATE_COLOR = (s) =>
  s === "BUYER_APPROVAL_REQUIRED" ? "text-accent"
    : s === "APPROVED" ? "text-secondary"
    : s === "REJECTED" || s?.includes("FAILED") ? "text-white/40"
    : "text-primary";

export default function CommunicationHub() {
  const [convs, setConvs] = useState([]);
  const [providers, setProviders] = useState([]);
  const [active, setActive] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showStart, setShowStart] = useState(false);
  const pollRef = useRef(null);

  const loadList = useCallback(async () => {
    const [c, s] = await Promise.all([
      api.get("/communication/negotiations").then((r) => r.data),
      api.get("/communication/status").then((r) => r.data.providers),
    ]);
    setConvs(c);
    setProviders(s);
  }, []);

  const loadDetail = useCallback(async (id) => {
    const { data } = await api.get(`/communication/negotiations/${id}`);
    setDetail(data);
  }, []);

  useEffect(() => {
    loadList().finally(() => setLoading(false));
  }, [loadList]);

  useEffect(() => {
    if (!active) return;
    loadDetail(active);
    pollRef.current = setInterval(() => loadDetail(active), 5000);
    return () => clearInterval(pollRef.current);
  }, [active, loadDetail]);

  const decide = async (action) => {
    try {
      await api.post(`/communication/negotiations/${active}/approve`, { action });
      toast.success(`Recorded: ${action}`);
      await loadDetail(active);
      await loadList();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  if (loading)
    return <div className="min-h-[60vh] flex items-center justify-center"><Spinner className="w-8 h-8" /></div>;

  return (
    <div className="p-6 lg:p-10 max-w-6xl mx-auto" data-testid="comm-hub">
      <div className="flex items-start justify-between gap-4 mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/25 flex items-center justify-center">
            <MessagesSquare className="text-primary" size={20} />
          </div>
          <div>
            <div className="text-[10px] font-mono tracking-widest text-primary/80 uppercase">Communication hub</div>
            <h1 className="font-display text-3xl font-bold tracking-tight">Messaging negotiations</h1>
          </div>
        </div>
        <Button onClick={() => setShowStart(true)} data-testid="comm-start-btn"><Plus size={16} /> New negotiation</Button>
      </div>

      {/* provider status */}
      <div className="flex flex-wrap gap-2 mb-6" data-testid="comm-providers">
        {providers.map((p) => (
          <span key={p.channel} className={`text-[11px] font-mono px-2.5 py-1 rounded-lg border ${p.state === "READY" ? "border-secondary/30 text-secondary" : "border-white/12 text-white/40"}`}>
            {CHANNEL_META[p.channel]?.label || p.channel}: {p.state.replace(/_/g, " ")}
          </span>
        ))}
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* list */}
        <div className={active ? "hidden lg:block" : ""}>
          <SectionLabel>Conversations</SectionLabel>
          <Card className="divide-y divide-white/5" data-testid="comm-list">
            {convs.length ? convs.map((c) => (
              <button key={c.id} onClick={() => setActive(c.id)}
                className={`w-full text-left p-4 hover:bg-white/5 transition-colors ${active === c.id ? "bg-white/5" : ""}`}
                data-testid={`comm-conv-${c.id}`}>
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full" style={{ background: CHANNEL_META[c.channel]?.color || "#888" }} />
                  <span className="font-medium text-sm truncate flex-1">{c.vendor_name}</span>
                  <span className={`text-[9px] font-mono uppercase ${STATE_COLOR(c.comm_state)}`}>{(c.comm_state || "").replace(/_/g, " ")}</span>
                </div>
                <div className="text-xs text-white/40 truncate mt-1">{c.last_message}</div>
                <div className="text-[10px] text-white/30 mt-1 flex gap-3">
                  {c.latest_quote != null && <span>quote {c.currency} {c.latest_quote}</span>}
                  {c.target_price != null && <span>target {c.currency} {c.target_price}</span>}
                </div>
              </button>
            )) : <p className="text-white/40 text-sm text-center py-8">No conversations yet.</p>}
          </Card>
        </div>

        {/* detail */}
        <div className="lg:col-span-2">
          {active && detail ? (
            <>
              <button onClick={() => { setActive(null); setDetail(null); }} className="lg:hidden inline-flex items-center gap-2 text-white/40 text-sm mb-3"><ArrowLeft size={14} /> Back</button>
              <SectionLabel>Negotiation thread</SectionLabel>
              <Card className="p-5" data-testid="comm-detail">
                {/* metrics */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                  <Metric label="Stage" value={(detail.stage || "").replace(/_/g, " ")} accent={STATE_COLOR(detail.stage)} />
                  <Metric label="Latest quote" value={detail.latest_quote != null ? `${detail.currency} ${detail.latest_quote}` : "—"} />
                  <Metric label="Target" value={detail.target_price != null ? `${detail.currency} ${detail.target_price}` : "—"} accent="text-secondary" />
                  <Metric label="Max authority" value={detail.max_authority != null ? `${detail.currency} ${detail.max_authority}` : "—"} accent="text-accent" />
                </div>
                {detail.next_action && (
                  <div className="text-xs text-white/50 mb-3 flex items-center gap-1.5"><TrendingDown size={12} className="text-primary" /> Next: {detail.next_action} — {detail.decision_summary}</div>
                )}

                {/* approval gate */}
                {detail.approval_required && (
                  <div className="rounded-xl border border-accent/40 bg-accent/10 p-4 mb-4" data-testid="comm-approval">
                    <div className="flex items-center gap-2 text-accent font-medium text-sm mb-1"><ShieldAlert size={15} /> Action required</div>
                    <p className="text-xs text-white/60 mb-3">A human must approve any final commitment. Nothing is purchased automatically.</p>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                      <Button size="sm" variant="success" onClick={() => decide("ACCEPT")} data-testid="comm-accept"><CheckCircle2 size={13} /> Accept</Button>
                      <Button size="sm" variant="secondary" onClick={() => decide("COUNTER")}>Counter</Button>
                      <Button size="sm" variant="secondary" onClick={() => decide("CLARIFY")}>Clarify</Button>
                      <Button size="sm" variant="danger" onClick={() => decide("REJECT")}>Reject</Button>
                    </div>
                  </div>
                )}
                {detail.conversation?.human_decision && (
                  <div className="text-sm text-secondary mb-4 flex items-center gap-2"><CheckCircle2 size={15} /> Decision: {detail.conversation.human_decision.action}</div>
                )}

                {/* chat */}
                <div className="space-y-2 max-h-[440px] overflow-y-auto" data-testid="comm-messages">
                  {detail.messages.map((m) => {
                    const ai = m.direction === "OUTBOUND";
                    const meta = ai ? { I: Bot, c: "text-primary", l: "NEGOBUY AI", bg: "bg-primary/10 border-primary/20" }
                      : { I: User, c: "text-secondary", l: "VENDOR", bg: "bg-secondary/10 border-secondary/20" };
                    return (
                      <div key={m.id} className={`flex ${ai ? "justify-start" : "justify-end"}`}>
                        <div className={`max-w-[82%] rounded-xl border px-3 py-2 ${meta.bg}`}>
                          <div className={`flex items-center gap-1.5 text-[9px] font-mono uppercase mb-0.5 ${meta.c}`}>
                            <meta.I size={11} /> {meta.l}
                            {m.delivery_status && m.delivery_status !== "SENT" && m.delivery_status !== "RECEIVED" && (
                              <span className="text-white/30">· {m.delivery_status}</span>
                            )}
                          </div>
                          <div className="text-sm text-white/85">{m.content}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </Card>
            </>
          ) : (
            <div className="h-full flex items-center justify-center text-white/30 text-sm border border-dashed border-white/10 rounded-2xl py-20">
              Select a conversation
            </div>
          )}
        </div>
      </div>

      {showStart && <StartModal providers={providers} onClose={() => setShowStart(false)}
        onStarted={async (id) => { setShowStart(false); await loadList(); setActive(id); }} />}
    </div>
  );
}

function Metric({ label, value, accent = "text-white/85" }) {
  return (
    <div className="rounded-xl border border-white/8 bg-white/5 p-2.5">
      <div className="text-[9px] uppercase tracking-wider text-white/40">{label}</div>
      <div className={`text-sm font-medium truncate ${accent}`}>{value}</div>
    </div>
  );
}

function StartModal({ providers, onClose, onStarted }) {
  const [missions, setMissions] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [form, setForm] = useState({ mission_id: "", vendor_id: "", channel: "telegram", recipient: "" });
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.get("/missions").then((r) => setMissions(r.data)); }, []);
  useEffect(() => {
    if (form.mission_id) api.get(`/missions/${form.mission_id}/vendors`).then((r) => setVendors(r.data));
  }, [form.mission_id]);

  const start = async () => {
    if (!form.mission_id || !form.vendor_id || !form.recipient.trim()) {
      toast.error("Pick a mission, vendor and enter a recipient."); return;
    }
    setBusy(true);
    try {
      const { data } = await api.post("/communication/negotiations/start", form);
      if (data.provider_state !== "READY")
        toast.message(`${CHANNEL_META[form.channel]?.label} is ${data.provider_state} — outreach stored but not delivered.`);
      else toast.success("Outreach sent.");
      onStarted(data.conversation_id);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" data-testid="comm-start-modal">
      <motion.div initial={{ scale: 0.96, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="w-full max-w-lg">
        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-display text-xl font-bold">New messaging negotiation</h3>
            <button onClick={onClose} className="text-white/40 hover:text-white"><X size={18} /></button>
          </div>
          <div className="space-y-4">
            <div>
              <label className="text-xs text-white/50 mb-1 block">Mission</label>
              <select className="w-full bg-black/40 border border-white/12 rounded-xl px-3 py-2.5 text-sm text-white" value={form.mission_id} onChange={(e) => setForm((f) => ({ ...f, mission_id: e.target.value, vendor_id: "" }))} data-testid="comm-mission">
                <option value="">Select…</option>
                {missions.map((m) => <option key={m.id} value={m.id}>{m.title}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-white/50 mb-1 block">Vendor</label>
              <select className="w-full bg-black/40 border border-white/12 rounded-xl px-3 py-2.5 text-sm text-white" value={form.vendor_id} onChange={(e) => setForm((f) => ({ ...f, vendor_id: e.target.value }))} data-testid="comm-vendor">
                <option value="">Select…</option>
                {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-white/50 mb-1 block">Channel</label>
                <select className="w-full bg-black/40 border border-white/12 rounded-xl px-3 py-2.5 text-sm text-white" value={form.channel} onChange={(e) => setForm((f) => ({ ...f, channel: e.target.value }))} data-testid="comm-channel">
                  {providers.map((p) => <option key={p.channel} value={p.channel}>{CHANNEL_META[p.channel]?.label} ({p.state === "READY" ? "ready" : "not configured"})</option>)}
                </select>
              </div>
              <Input label="Recipient (chat ID / number)" value={form.recipient} onChange={(e) => setForm((f) => ({ ...f, recipient: e.target.value }))} data-testid="comm-recipient" />
            </div>
            <Button className="w-full" onClick={start} disabled={busy} data-testid="comm-start-submit">
              {busy ? <Spinner /> : <Send size={15} />} Start negotiation
            </Button>
          </div>
        </Card>
      </motion.div>
    </div>
  );
}

import React, { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  PhoneCall, Sparkles, ShieldAlert, Ban, Target, Radio, FlaskConical,
  MessageSquare, Clock, Bot, User, Cog, CheckCircle2, HelpCircle,
  TrendingDown, AlertTriangle, Send, ThumbsUp, ThumbsDown, RefreshCw,
  Edit3, FileText, Building2,
} from "lucide-react";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { Button, Card, Input, Textarea, Spinner, SectionLabel, Badge } from "../components/ui";

/* ---------- state-driven visual (communicates the negotiation, not decoration) ---------- */
function StageVisual({ stage }) {
  const phone = ["calling", "connected", "negotiating"].includes(stage);
  const wapp = ["no_answer", "whatsapp"].includes(stage);
  const done = ["offer", "approval"].includes(stage);
  const failed = stage === "no_answer";
  const color = failed ? "#ff5c7c" : wapp ? "#25d366" : done ? "#22e0a1" : "#00e5ff";
  const label = failed ? "no answer" : wapp ? "whatsapp" : phone ? "voice"
    : stage === "offer" ? "offer received" : stage === "approval" ? "approval" : "idle";
  return (
    <div className="relative h-40 flex items-center justify-between px-10" data-testid="stage-visual">
      <Node label="NegoBuy AI" color="#00e5ff" icon={Bot} pulse={phone || wapp} />
      <div className="flex-1 relative h-px mx-4">
        <div className="absolute inset-0 top-1/2 h-px" style={{ background: `${color}30` }} />
        {(phone || wapp) && (
          <motion.span
            className="absolute top-1/2 -mt-1 w-2 h-2 rounded-full"
            style={{ background: color, boxShadow: `0 0 12px ${color}` }}
            animate={{ left: wapp ? ["0%", "100%"] : ["0%", "100%", "0%"] }}
            transition={{ duration: wapp ? 1.6 : 2.4, repeat: Infinity, ease: "easeInOut" }}
          />
        )}
        {done && (
          <span className="absolute left-1/2 -translate-x-1/2 top-1/2 -mt-1 w-2.5 h-2.5 rounded-full"
                style={{ background: color, boxShadow: `0 0 12px ${color}` }} />
        )}
        <div className="absolute left-1/2 -translate-x-1/2 -top-6 text-[10px] font-mono uppercase tracking-widest"
             style={{ color }}>
          {label}
        </div>
      </div>
      <Node label="Business" color={color} icon={wapp ? MessageSquare : Building2} pulse={phone || wapp} failed={failed} />
    </div>
  );
}
function Node({ label, color, icon: Icon, pulse, failed }) {
  return (
    <div className="flex flex-col items-center gap-2">
      <motion.div
        className="w-16 h-16 rounded-2xl flex items-center justify-center border"
        style={{ borderColor: `${color}55`, background: `${color}12`,
                 boxShadow: pulse ? `0 0 24px ${color}40` : "none" }}
        animate={pulse ? { scale: [1, 1.06, 1] } : {}}
        transition={{ duration: 1.4, repeat: Infinity }}
      >
        <Icon size={26} style={{ color: failed ? "#ff5c7c" : color }} />
      </motion.div>
      <span className="text-[10px] font-mono uppercase tracking-wider text-white/50">{label}</span>
    </div>
  );
}

const TERM_STATUS = {
  CONFIRMED: "text-secondary border-secondary/30 bg-secondary/10",
  PROPOSED: "text-primary border-primary/30 bg-primary/10",
  UNCLEAR: "text-white/50 border-white/15 bg-white/5",
  REQUIRES_HUMAN_APPROVAL: "text-accent border-accent/30 bg-accent/10",
};

export default function DirectNegotiation() {
  const [phase, setPhase] = useState("form"); // form | review | run
  const [form, setForm] = useState({
    business_name: "", contact_name: "", phone_number: "", whatsapp_number: "",
    business_description: "", what_to_buy: "", product: "", quantity: "",
    target_price: "", max_authorized_price: "", currency: "INR",
    delivery_location: "", delivery_deadline_days: "", payment_preference: "",
    warranty_requirements: "", quality_requirements: "", other_instructions: "",
    test_mode: true, disclose_ai: true, recording_notice: true,
  });
  const [prep, setPrep] = useState(null);
  const [preparing, setPreparing] = useState(false);
  const [placing, setPlacing] = useState(false);
  const [callRef, setCallRef] = useState(null);
  const [callStatus, setCallStatus] = useState(null);
  const [full, setFull] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [stage, setStage] = useState("idle");
  const [waText, setWaText] = useState("");
  const [waSending, setWaSending] = useState(false);
  const [reportBusy, setReportBusy] = useState(false);
  const pollRef = useRef(null);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const num = (v) => (v === "" || v == null ? null : Number(v));
  const mid = prep?.mission_id;

  const refresh = useCallback(async () => {
    if (!mid) return;
    const [f, t] = await Promise.all([
      api.get(`/direct-negotiation/${mid}`).then((r) => r.data),
      api.get(`/direct-negotiation/${mid}/timeline`).then((r) => r.data.timeline),
    ]);
    setFull(f);
    setTimeline(t);
    return f;
  }, [mid]);

  useEffect(() => () => clearInterval(pollRef.current), []);

  const doPrepare = async () => {
    if (!form.business_name.trim() || !form.what_to_buy.trim()) {
      toast.error("Enter the business name and what you want to buy.");
      return;
    }
    setPreparing(true);
    try {
      const { data } = await api.post("/direct-negotiation/prepare", {
        business_name: form.business_name, contact_name: form.contact_name || null,
        phone_number: form.phone_number || null, whatsapp_number: form.whatsapp_number || null,
        business_description: form.business_description || null, what_to_buy: form.what_to_buy,
        product: form.product || null, quantity: num(form.quantity),
        target_price: num(form.target_price), max_authorized_price: num(form.max_authorized_price),
        currency: form.currency, delivery_location: form.delivery_location || null,
        delivery_deadline_days: num(form.delivery_deadline_days),
        payment_preference: form.payment_preference || null,
        warranty_requirements: form.warranty_requirements || null,
        quality_requirements: form.quality_requirements || null,
        other_instructions: form.other_instructions || null,
      });
      setPrep(data);
      setPhase("review");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setPreparing(false);
    }
  };

  const startCall = async () => {
    setPlacing(true);
    setStage("calling");
    try {
      const { data: cfg } = await api.post("/voice/console/config", {
        mission_id: prep.mission_id, vendor_id: prep.vendor_id,
        to_number: prep.phone_number || form.phone_number,
        supplier_name: form.business_name, product: prep.mission.product,
        quantity: num(form.quantity), target_price: num(form.target_price),
        max_authorized_price: num(form.max_authorized_price),
        delivery_location: form.delivery_location, delivery_deadline_days: num(form.delivery_deadline_days),
        warranty_requirements: form.warranty_requirements, payment_preferences: form.payment_preference,
        special_instructions: form.other_instructions, currency: form.currency,
        test_mode: form.test_mode, disclose_ai: form.disclose_ai, recording_notice: form.recording_notice,
      });
      setCallRef(cfg.session_ref);
      setPhase("run");
      setStage(form.test_mode ? "negotiating" : "calling");
      const { data } = await api.post(`/voice/console/approve/${cfg.session_ref}`);
      setCallStatus(data.status);
      if (data.status === "SIMULATED_COMPLETE") {
        setStage("offer");
        toast.success("AI test negotiation complete.");
      } else if (data.status === "failed" || data.status === "NOT_CONFIGURED") {
        setStage("no_answer");
        toast.message("Call not connected — you can trigger the WhatsApp fallback.");
      } else {
        toast.success("Call placed.");
      }
      await refresh();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
      setStage("idle");
    } finally {
      setPlacing(false);
    }
  };

  const triggerFallback = async () => {
    setStage("whatsapp");
    // Only reference the call when the provider actually reported a no-answer/failed
    // status; a completed/simulated call is not a fallback-eligible no-answer.
    const eligible = ["failed", "no-answer", "busy", "unreachable", "canceled", "call_dropped"]
      .includes(callStatus);
    try {
      const { data } = await api.post(`/direct-negotiation/${mid}/fallback`, {
        simulate: true, ...(eligible && callRef ? { call_ref: callRef } : {}),
      });
      if (data.status === "NOT_CONFIGURED") toast.error(data.message);
      else toast.success(`WhatsApp follow-up ${data.delivery?.state === "SENT" ? "sent" : "prepared (simulated)"}`);
      await refresh();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const sendReply = async () => {
    if (!waText.trim()) return;
    setWaSending(true);
    setStage("negotiating");
    try {
      await api.post(`/direct-negotiation/${mid}/whatsapp-reply`, { text: waText, simulate: true });
      setWaText("");
      setStage("offer");
      await refresh();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setWaSending(false);
    }
  };

  const genReport = async () => {
    setReportBusy(true);
    try {
      await api.post(`/direct-negotiation/${mid}/generate-report`);
      toast.success("Final report generated.");
      await refresh();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setReportBusy(false);
    }
  };

  const decide = async (action) => {
    try {
      await api.post(`/direct-negotiation/${mid}/decision`, { action });
      toast.success("Decision recorded");
      await refresh();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  /* --------------------------------- render --------------------------------- */
  return (
    <div className="p-6 lg:p-10 max-w-6xl mx-auto" data-testid="direct-negotiation">
      <div className="flex items-center gap-3 mb-1">
        <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/25 flex items-center justify-center">
          <PhoneCall className="text-primary" size={20} />
        </div>
        <div>
          <div className="text-[10px] font-mono tracking-widest text-primary/80 uppercase">Direct business negotiation</div>
          <h1 className="font-display text-3xl font-bold tracking-tight">Negotiate with a business</h1>
        </div>
      </div>
      <p className="text-white/45 text-sm mb-8 max-w-2xl">
        Enter a business contact and what you want to buy. NegoBuy prepares the plan, you approve,
        and the AI negotiates by phone — with a controlled WhatsApp fallback if the call isn't answered.
      </p>

      {/* ============================ FORM ============================ */}
      {phase === "form" && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
          <div>
            <SectionLabel>Business & contact</SectionLabel>
            <Card className="p-6 grid sm:grid-cols-2 gap-4">
              <Input label="Business / supplier name" value={form.business_name} onChange={set("business_name")} data-testid="dn-business" />
              <Input label="Contact person (optional)" value={form.contact_name} onChange={set("contact_name")} data-testid="dn-contact" />
              <Input label="Phone number" value={form.phone_number} onChange={set("phone_number")} placeholder="+91XXXXXXXXXX" data-testid="dn-phone" />
              <Input label="WhatsApp number (optional)" value={form.whatsapp_number} onChange={set("whatsapp_number")} placeholder="defaults to phone" data-testid="dn-whatsapp" />
              <div className="sm:col-span-2">
                <Input label="Business description (optional)" value={form.business_description} onChange={set("business_description")} data-testid="dn-desc" />
              </div>
            </Card>
          </div>
          <div>
            <SectionLabel>What you want to buy</SectionLabel>
            <Card className="p-6 space-y-4">
              <Textarea label="Describe the requirement" rows={2} value={form.what_to_buy} onChange={set("what_to_buy")} placeholder="e.g. Purchase floor tiles for a new showroom" data-testid="dn-requirement" />
              <div className="grid sm:grid-cols-2 gap-4">
                <Input label="Product / service" value={form.product} onChange={set("product")} data-testid="dn-product" />
                <Input label="Quantity" type="number" value={form.quantity} onChange={set("quantity")} data-testid="dn-quantity" />
                <Input label={`Target price (${form.currency})`} type="number" value={form.target_price} onChange={set("target_price")} data-testid="dn-target" />
                <Input label={`Maximum authorized price (${form.currency})`} type="number" value={form.max_authorized_price} onChange={set("max_authorized_price")} data-testid="dn-max" />
                <Input label="Currency" value={form.currency} onChange={set("currency")} data-testid="dn-currency" />
                <Input label="Delivery location" value={form.delivery_location} onChange={set("delivery_location")} data-testid="dn-location" />
                <Input label="Delivery deadline (days)" type="number" value={form.delivery_deadline_days} onChange={set("delivery_deadline_days")} data-testid="dn-deadline" />
                <Input label="Payment preference" value={form.payment_preference} onChange={set("payment_preference")} data-testid="dn-payment" />
                <Input label="Warranty requirements" value={form.warranty_requirements} onChange={set("warranty_requirements")} data-testid="dn-warranty" />
                <Input label="Quality / specifications" value={form.quality_requirements} onChange={set("quality_requirements")} data-testid="dn-quality" />
              </div>
              <Textarea label="Other negotiation instructions" rows={2} value={form.other_instructions} onChange={set("other_instructions")} placeholder="e.g. Be polite. Ask about delivery, loading and unloading charges." data-testid="dn-instructions" />
            </Card>
          </div>
          <div className="flex justify-end">
            <Button size="lg" onClick={doPrepare} disabled={preparing} data-testid="dn-prepare-btn">
              {preparing ? <Spinner /> : <Sparkles size={18} />} Prepare negotiation
            </Button>
          </div>
        </motion.div>
      )}

      {/* ============================ REVIEW ============================ */}
      {phase === "review" && prep && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-6" data-testid="dn-review">
          <div>
            <SectionLabel>What the AI understands</SectionLabel>
            <Card className="p-5 grid sm:grid-cols-2 gap-x-8 gap-y-3 text-sm">
              <Field label="Requirement" value={prep.requirement.summary || prep.mission.title} />
              <Field label="Product" value={prep.mission.product} />
              <Field label="Quantity" value={prep.mission.quantity} />
              <Field label="Deliver to" value={prep.mission.delivery_location} />
              <Field label="Target price" value={prep.authority.target_price_per_unit ? `${prep.authority.currency} ${prep.authority.target_price_per_unit}` : "—"} accent="text-secondary" />
              <Field label="Max authorized" value={prep.authority.max_price_per_unit ? `${prep.authority.currency} ${prep.authority.max_price_per_unit}` : "—"} accent="text-accent" />
              {prep.requirement.assumptions?.length > 0 && (
                <div className="sm:col-span-2">
                  <div className="text-[10px] uppercase tracking-wider text-white/40 mb-1">Assumptions</div>
                  <div className="flex flex-wrap gap-1.5">{prep.requirement.assumptions.map((a, i) => <Badge key={i}>{a}</Badge>)}</div>
                </div>
              )}
            </Card>
          </div>

          <div>
            <SectionLabel>Negotiation plan</SectionLabel>
            <Card className="p-5 space-y-4">
              <div>
                <div className="text-[10px] uppercase tracking-wider text-primary/70 mb-1">Primary objective</div>
                <p className="text-sm text-white/85">{prep.plan.primary_objective}</p>
              </div>
              <PlanList label="Key questions" items={prep.plan.key_questions} icon={HelpCircle} />
              <div className="grid sm:grid-cols-2 gap-4">
                <PlanList label="Delivery questions" items={prep.plan.delivery_questions} icon={Target} />
                <PlanList label="Payment questions" items={prep.plan.payment_questions} icon={Target} />
              </div>
              <PlanList label="Risks" items={prep.plan.risks} icon={AlertTriangle} color="text-yellow-300/80" />
              {prep.plan.opening_line && (
                <div className="rounded-xl border border-primary/15 bg-primary/5 p-3">
                  <div className="text-[10px] uppercase tracking-wider text-primary/70 mb-1">AI opening (identity disclosed)</div>
                  <p className="text-sm text-white/70 italic">“{prep.plan.opening_line}”</p>
                </div>
              )}
            </Card>
          </div>

          <div>
            <SectionLabel>Provider status</SectionLabel>
            <Card className="p-5 grid grid-cols-2 sm:grid-cols-4 gap-3">
              {Object.entries(prep.providers).map(([k, v]) => (
                <div key={k} className="rounded-xl border border-white/10 bg-white/5 p-3">
                  <div className="text-[10px] uppercase tracking-wider text-white/40">{k.replace(/_/g, " ")}</div>
                  <div className={`text-sm font-medium ${v.state === "READY" || v.state === "RECORDING_AVAILABLE" ? "text-secondary" : "text-yellow-300"}`}>
                    {(v.state || "").replace(/_/g, " ")}
                  </div>
                </div>
              ))}
            </Card>
          </div>

          <div>
            <SectionLabel>Mode & authority</SectionLabel>
            <Card className="p-5 space-y-4">
              <div className="flex gap-3">
                <ModeBtn active={form.test_mode} onClick={() => setForm((f) => ({ ...f, test_mode: true }))} icon={FlaskConical} title="Test call (simulated)" desc="Runs the full negotiation via the AI brain. No phone dialled." testid="dn-mode-test" />
                <ModeBtn active={!form.test_mode} onClick={() => setForm((f) => ({ ...f, test_mode: false }))} icon={Radio} title="Live call (real phone)" desc="Places a real Exotel call. Needs provider streaming config for in-call AI speech." testid="dn-mode-live" accent />
              </div>
              <div className="rounded-xl border border-accent/20 bg-accent/5 p-4">
                <div className="flex items-center gap-2 text-accent text-sm font-medium mb-2"><Ban size={15} /> The AI is NOT authorized to</div>
                <ul className="grid sm:grid-cols-2 gap-1 text-xs text-white/60">
                  <li>• Exceed {prep.authority.currency} {prep.authority.max_price_per_unit ?? "the max"}/unit</li>
                  <li>• Change specifications without approval</li>
                  <li>• Agree to unexpected payment terms</li>
                  <li>• Make binding commitments / place an order</li>
                </ul>
              </div>
            </Card>
          </div>

          <div className="flex justify-between gap-3">
            <Button variant="ghost" onClick={() => setPhase("form")} data-testid="dn-edit-btn">Edit</Button>
            <Button size="lg" variant={form.test_mode ? "primary" : "danger"} onClick={startCall} disabled={placing} data-testid="dn-start-btn">
              {placing ? <Spinner /> : <PhoneCall size={18} />}
              {form.test_mode ? "Review & start AI test call" : "Start AI negotiation call"}
            </Button>
          </div>
        </motion.div>
      )}

      {/* ============================ RUN ============================ */}
      {phase === "run" && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6" data-testid="dn-run">
          <Card glass className="p-4"><StageVisual stage={stage} /></Card>

          <div className="grid lg:grid-cols-3 gap-6">
            {/* timeline */}
            <div>
              <SectionLabel>Unified timeline</SectionLabel>
              <Card glass className="p-5 max-h-[520px] overflow-y-auto" data-testid="dn-timeline">
                {timeline.length ? (
                  <div className="space-y-4">
                    {timeline.map((e, i) => (
                      <div key={i} className="flex gap-3">
                        <div className="flex flex-col items-center">
                          <span className="w-2 h-2 rounded-full bg-primary mt-1.5" />
                          <span className="flex-1 w-px bg-white/10 my-1" />
                        </div>
                        <div className="min-w-0 pb-1">
                          <div className="text-sm text-white/85">{e.title}</div>
                          {e.detail && <div className="text-xs text-white/40 mt-0.5">{e.detail}</div>}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-white/40 text-sm text-center py-6">No events yet.</p>
                )}
              </Card>
              <div className="mt-4 flex flex-col gap-2">
                <Button variant="secondary" onClick={triggerFallback} disabled={(full?.messages || []).some((m) => m.kind === "fallback")} data-testid="dn-fallback-btn">
                  <MessageSquare size={15} /> {(full?.messages || []).some((m) => m.kind === "fallback") ? "WhatsApp fallback sent" : "Trigger WhatsApp fallback"}
                </Button>
              </div>
            </div>

            {/* conversation */}
            <div className="lg:col-span-2 space-y-6">
              {/* transcript from calls */}
              {full?.calls?.[0]?.transcript?.length > 0 && (
                <div>
                  <SectionLabel>Call transcript</SectionLabel>
                  <Card className="p-5 space-y-2" data-testid="dn-transcript">
                    {full.calls[0].transcript.map((t) => {
                      const spk = (t.speaker || "").toUpperCase();
                      const meta = spk === "AI" ? { c: "text-primary", I: Bot, l: "AI" }
                        : spk === "SUPPLIER" ? { c: "text-white/80", I: User, l: "Business" }
                        : { c: "text-white/40", I: Cog, l: "System" };
                      return (
                        <div key={t.id} className="text-sm">
                          <span className={`text-[10px] font-mono uppercase mr-2 ${meta.c}`}>{meta.l}</span>
                          <span className={spk === "SYSTEM" ? "text-white/40 italic" : "text-white/85"}>{t.text}</span>
                        </div>
                      );
                    })}
                  </Card>
                </div>
              )}

              {/* whatsapp thread */}
              <div>
                <SectionLabel>WhatsApp conversation</SectionLabel>
                <Card className="p-5" data-testid="dn-whatsapp">
                  {full?.messages?.length ? (
                    <div className="space-y-2 mb-4">
                      {full.messages.map((m) => (
                        <div key={m.id} className={`flex ${m.direction === "outbound" ? "justify-start" : "justify-end"}`}>
                          <div className={`max-w-[80%] rounded-xl px-3 py-2 text-sm ${m.direction === "outbound" ? "bg-primary/10 border border-primary/20 text-white/85" : "bg-secondary/10 border border-secondary/20 text-white/85"}`}>
                            <div className={`text-[9px] font-mono uppercase mb-0.5 ${m.direction === "outbound" ? "text-primary" : "text-secondary"}`}>
                              {m.direction === "outbound" ? "AI" : "Business"}{m.kind === "fallback" ? " · fallback" : ""}
                            </div>
                            {m.text}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-white/40 text-sm mb-4">No WhatsApp messages yet. Trigger the fallback, then simulate a reply.</p>
                  )}
                  <div className="flex gap-2">
                    <input
                      className="flex-1 bg-black/40 border border-white/12 rounded-xl px-4 py-2.5 text-sm text-white placeholder-white/30 outline-none focus:border-primary/60"
                      placeholder="Simulate a business reply…"
                      value={waText}
                      onChange={(e) => setWaText(e.target.value)}
                      data-testid="dn-wa-input"
                    />
                    <Button onClick={sendReply} disabled={waSending} data-testid="dn-wa-send">
                      {waSending ? <Spinner /> : <Send size={15} />}
                    </Button>
                  </div>
                </Card>
              </div>

              {/* offers */}
              {full?.offers?.length > 0 && (
                <div>
                  <SectionLabel>Offers</SectionLabel>
                  <Card className="p-5 space-y-2" data-testid="dn-offers">
                    {full.offers.map((o) => (
                      <div key={o.id} className="flex items-center justify-between text-sm">
                        <span className="text-white/80">{o.currency} {o.negotiated_price}/unit</span>
                        <div className="flex items-center gap-2">
                          {o.simulation && <Badge>sim</Badge>}
                          <span className={`text-[9px] font-mono px-2 py-1 rounded-md border ${o.status === "OUT_OF_AUTHORITY" ? "border-accent/30 text-accent" : "border-secondary/30 text-secondary"}`}>
                            {o.status === "OUT_OF_AUTHORITY" ? "exceeds max" : "within authority"}
                          </span>
                        </div>
                      </div>
                    ))}
                  </Card>
                </div>
              )}

              {/* report + decisions */}
              <div>
                <SectionLabel>Final report</SectionLabel>
                <Card className="p-5" data-testid="dn-report">
                  {full?.report ? (
                    <>
                      {(full.report.within_authority === false || full.report.requires_human_approval) && (
                        <div className="mb-4 rounded-xl border border-accent/40 bg-accent/10 p-3 flex gap-2" data-testid="dn-authority-warning">
                          <ShieldAlert size={16} className="text-accent shrink-0 mt-0.5" />
                          <div className="text-sm text-accent font-medium">Requires human approval — terms are outside the AI's authority.</div>
                        </div>
                      )}
                      <p className="text-sm text-white/85 leading-relaxed">{full.report.summary}</p>
                      {full.report.terms?.length > 0 && (
                        <div className="mt-4 space-y-2">
                          {full.report.terms.map((t, i) => (
                            <div key={i} className="flex items-center justify-between gap-3 text-sm">
                              <span className="text-white/50 text-[11px] uppercase tracking-wider">{t.field}</span>
                              <div className="flex items-center gap-2 min-w-0">
                                <span className="text-white/80 truncate">{t.value}</span>
                                <span className={`shrink-0 text-[9px] font-mono px-2 py-0.5 rounded-md border ${TERM_STATUS[t.status] || TERM_STATUS.UNCLEAR}`}>{(t.status || "").replace(/_/g, " ")}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                      {full.report.self_review?.recommended_next_step && (
                        <div className="mt-4 rounded-xl border border-primary/15 bg-primary/5 p-3">
                          <div className="text-[10px] uppercase tracking-wider text-primary/70 mb-1 flex items-center gap-1"><Sparkles size={11} /> Recommended next step</div>
                          <p className="text-sm text-white/80">{full.report.self_review.recommended_next_step}</p>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="flex items-center justify-between">
                      <p className="text-white/40 text-sm">Generate a report from the call + WhatsApp conversation.</p>
                      <Button variant="secondary" size="sm" onClick={genReport} disabled={reportBusy} data-testid="dn-gen-report">
                        {reportBusy ? <Spinner /> : <FileText size={14} />} Generate report
                      </Button>
                    </div>
                  )}

                  {full?.decision ? (
                    <div className="mt-4 pt-4 border-t hairline text-sm text-secondary flex items-center gap-2">
                      <CheckCircle2 size={15} /> Decision: {full.decision.action.replace(/_/g, " ")}
                    </div>
                  ) : full?.report ? (
                    <div className="mt-4 pt-4 border-t hairline grid grid-cols-2 sm:grid-cols-3 gap-2">
                      <Button variant="secondary" size="sm" onClick={() => decide("CONTINUE")} data-testid="dn-decide-continue"><RefreshCw size={13} /> Continue</Button>
                      <Button variant="secondary" size="sm" onClick={() => decide("COUNTEROFFER")} data-testid="dn-decide-counter"><Edit3 size={13} /> Counteroffer</Button>
                      <Button variant="secondary" size="sm" onClick={() => decide("REQUEST_HUMAN_REVIEW")}><HelpCircle size={13} /> Human review</Button>
                      <Button variant="success" size="sm" onClick={() => decide("APPROVE_NEXT")} data-testid="dn-decide-approve"><ThumbsUp size={13} /> Approve next</Button>
                      <Button variant="danger" size="sm" onClick={() => decide("REJECT")} data-testid="dn-decide-reject"><ThumbsDown size={13} /> Reject</Button>
                      <Button variant="ghost" size="sm" onClick={() => decide("END")}>End</Button>
                    </div>
                  ) : null}
                </Card>
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </div>
  );
}

function Field({ label, value, accent = "text-white/85" }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-white/40">{label}</div>
      <div className={`font-medium ${accent}`}>{value ?? "—"}</div>
    </div>
  );
}
function PlanList({ label, items, icon: Icon, color = "text-white/70" }) {
  if (!items?.length) return null;
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-white/40 mb-1.5">{label}</div>
      <ul className="space-y-1">
        {items.map((x, i) => (
          <li key={i} className={`text-sm flex gap-2 ${color}`}><Icon size={13} className="shrink-0 mt-0.5 opacity-60" /> {x}</li>
        ))}
      </ul>
    </div>
  );
}
function ModeBtn({ active, onClick, icon: Icon, title, desc, testid, accent }) {
  return (
    <button type="button" onClick={onClick} data-testid={testid}
      className={`flex-1 rounded-xl border p-4 text-left transition-colors ${active ? (accent ? "border-accent/50 bg-accent/10" : "border-primary/50 bg-primary/10") : "border-white/12 hover:bg-white/5"}`}>
      <div className="flex items-center gap-2 font-medium text-sm"><Icon size={16} className={accent ? "text-accent" : "text-primary"} /> {title}</div>
      <p className="text-xs text-white/45 mt-1">{desc}</p>
    </button>
  );
}

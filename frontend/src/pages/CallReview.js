import React, { useCallback, useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowLeft, Bot, User, Cog, Clock, Building2, Target, Radio, Mic,
  TrendingDown, AlertTriangle, CheckCircle2, HelpCircle, ShieldAlert,
  FileText, Sparkles, ThumbsUp, ThumbsDown, RefreshCw, Edit3,
} from "lucide-react";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { Button, Card, Spinner, SectionLabel, Badge, StatusPill } from "../components/ui";

const NON_TERMINAL = ["CONFIGURED", "SIMULATING", "initiating", "calling", "connected"];

const TERM_STATUS = {
  CONFIRMED: { cls: "text-secondary border-secondary/30 bg-secondary/10", icon: CheckCircle2 },
  PROPOSED: { cls: "text-primary border-primary/30 bg-primary/10", icon: Radio },
  UNCLEAR: { cls: "text-white/50 border-white/15 bg-white/5", icon: HelpCircle },
  REQUIRES_HUMAN_APPROVAL: { cls: "text-accent border-accent/30 bg-accent/10", icon: ShieldAlert },
};

const REC_LABEL = {
  RECORDING_REQUESTED: "Recording requested",
  RECORDING_ACTIVE: "Recording active",
  RECORDING_AVAILABLE: "Recording available",
  RECORDING_FAILED: "Recording failed",
  RECORDING_NOT_SUPPORTED: "Recording not enabled",
};

export default function CallReview() {
  const { id, ref } = useParams();
  const [call, setCall] = useState(null);
  const [loading, setLoading] = useState(true);
  const [savingOutcome, setSavingOutcome] = useState(false);
  const pollRef = useRef(null);

  const load = useCallback(async () => {
    const { data } = await api.get(`/voice/console/session/${ref}`);
    setCall(data);
    return data;
  }, [ref]);

  useEffect(() => {
    load().finally(() => setLoading(false));
    pollRef.current = setInterval(async () => {
      try {
        const d = await load();
        if (!NON_TERMINAL.includes(d.status)) clearInterval(pollRef.current);
      } catch (_) {}
    }, 4000);
    return () => clearInterval(pollRef.current);
  }, [load]);

  const setOutcome = async (decision) => {
    setSavingOutcome(true);
    try {
      await api.post(`/voice/console/outcome/${ref}`, { decision });
      toast.success("Decision recorded");
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setSavingOutcome(false);
    }
  };

  if (loading || !call)
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Spinner className="w-8 h-8" />
      </div>
    );

  const a = call.analysis || {};
  const rec = call.recording || {};
  const transcript = call.transcript || [];
  const busy = NON_TERMINAL.includes(call.status);

  return (
    <div className="p-6 lg:p-10 max-w-6xl mx-auto" data-testid="call-review">
      <Link to={`/missions/${id}`} className="inline-flex items-center gap-2 text-white/40 hover:text-white text-sm mb-6 transition-colors">
        <ArrowLeft size={15} /> Back to mission
      </Link>

      {/* Header / status */}
      <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <span className="text-[10px] font-mono tracking-widest text-primary/80 uppercase" data-testid="call-status">
              {(call.status || "").replace(/_/g, " ")}
            </span>
            {call.simulation && <Badge>simulated</Badge>}
            {busy && <span className="text-xs text-primary font-mono animate-pulseGlow">● live</span>}
          </div>
          <h1 className="font-display text-3xl font-bold tracking-tight">
            Call review · {call.vendor_name}
          </h1>
          <div className="text-sm text-white/45 mt-2 flex gap-4 flex-wrap">
            <span className="flex items-center gap-1"><Clock size={13} /> {call.duration != null ? `${call.duration}s` : "—"}</span>
            <span className="flex items-center gap-1"><Building2 size={13} /> {call.mission_title}</span>
            <span className="flex items-center gap-1"><Radio size={13} /> {call.to}</span>
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* LEFT: objective + recording + transcript */}
        <div className="lg:col-span-2 space-y-6">
          {/* Objective */}
          <div>
            <SectionLabel>Call objective</SectionLabel>
            <Card className="p-5 grid sm:grid-cols-2 gap-x-8 gap-y-3 text-sm">
              <Field label="Product" value={call.objective?.product} />
              <Field label="Quantity" value={call.objective?.quantity} />
              <Field label="Target price" value={call.authority?.target_price_per_unit ? `${call.authority.currency} ${call.authority.target_price_per_unit}` : "—"} accent="text-secondary" />
              <Field label="Max authorized" value={call.authority?.max_price_per_unit ? `${call.authority.currency} ${call.authority.max_price_per_unit}` : "—"} accent="text-accent" />
              <Field label="Deliver to" value={call.objective?.delivery_location} />
              <Field label="Deadline" value={call.objective?.delivery_deadline_days ? `${call.objective.delivery_deadline_days} days` : "—"} />
              {call.objective?.special_instructions && (
                <div className="sm:col-span-2">
                  <Field label="Special instructions" value={call.objective.special_instructions} />
                </div>
              )}
            </Card>
          </div>

          {/* Recording */}
          <div>
            <SectionLabel>Recording</SectionLabel>
            <Card className="p-5">
              <div className="flex items-center gap-2 text-sm">
                <Mic size={15} className={rec.state === "RECORDING_AVAILABLE" ? "text-secondary" : "text-white/40"} />
                <span className="text-white/80" data-testid="recording-state">{REC_LABEL[rec.state] || rec.state || "—"}</span>
              </div>
              {rec.state === "RECORDING_AVAILABLE" && rec.url ? (
                <audio controls src={rec.url} className="w-full mt-3" data-testid="recording-player" />
              ) : (
                <p className="text-xs text-white/40 mt-2">
                  {rec.state === "RECORDING_NOT_SUPPORTED"
                    ? "Recording was not enabled for this call."
                    : "No recording is available from the provider yet."}
                </p>
              )}
            </Card>
          </div>

          {/* Transcript */}
          <div>
            <SectionLabel>Conversation transcript</SectionLabel>
            <Card className="p-5" data-testid="transcript">
              {transcript.length ? (
                <div className="space-y-3">
                  {transcript.map((t) => {
                    const spk = (t.speaker || t.role || "").toUpperCase();
                    const meta =
                      spk === "AI"
                        ? { icon: Bot, color: "text-primary", label: "AI", bg: "bg-primary/5 border-primary/15" }
                        : spk === "SUPPLIER"
                        ? { icon: User, color: "text-white/80", label: "Supplier", bg: "bg-white/5 border-white/10" }
                        : { icon: Cog, color: "text-white/40", label: "System", bg: "bg-transparent border-white/5" };
                    const Icon = meta.icon;
                    return (
                      <div key={t.id} className={`rounded-xl border p-3 ${meta.bg}`} data-testid={`transcript-${spk.toLowerCase()}`}>
                        <div className="flex items-center gap-2 mb-1">
                          <Icon size={13} className={meta.color} />
                          <span className={`text-[10px] font-mono uppercase tracking-wider ${meta.color}`}>{meta.label}</span>
                          {t.timestamp && <span className="text-[10px] font-mono text-white/30 ml-auto">{t.timestamp}</span>}
                        </div>
                        <p className={`text-sm ${spk === "SYSTEM" ? "text-white/40 italic" : "text-white/85"}`}>{t.text}</p>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-white/40 text-sm text-center py-6" data-testid="transcript-unavailable">
                  {call.transcript_status === "PENDING" && busy
                    ? "Waiting for the conversation…"
                    : "Transcript unavailable."}
                </p>
              )}
            </Card>
          </div>
        </div>

        {/* RIGHT: analysis + self review + approval gate */}
        <div className="space-y-6">
          {/* Summary */}
          <div>
            <SectionLabel>Call summary</SectionLabel>
            <Card className="p-5" data-testid="call-summary">
              {a.summary ? (
                <>
                  {(a.within_authority === false || a.requires_human_approval) && (
                    <div className="mb-4 rounded-xl border border-accent/40 bg-accent/10 p-3 flex gap-2" data-testid="authority-warning">
                      <ShieldAlert size={16} className="text-accent shrink-0 mt-0.5" />
                      <div className="text-sm">
                        <div className="font-medium text-accent">
                          {a.within_authority === false
                            ? "Exceeds maximum authorized price"
                            : "Requires human approval"}
                        </div>
                        <p className="text-white/60 text-xs mt-0.5">
                          The discussed terms are outside the AI's authority. No commitment was made —
                          your explicit approval is required before proceeding.
                        </p>
                      </div>
                    </div>
                  )}
                  <p className="text-sm text-white/85 leading-relaxed">{a.summary}</p>
                  <div className="flex flex-wrap gap-2 mt-4">
                    {a.negotiation_result && (
                      <Badge className={a.within_authority === false ? "border-accent/30 text-accent" : "border-primary/30 text-primary"}>
                        <TrendingDown size={11} className="mr-1" /> {a.negotiation_result}
                      </Badge>
                    )}
                    {a.price_improvement_pct != null && a.within_authority !== false && (
                      <Badge className="border-secondary/30 text-secondary">
                        {a.price_improvement_pct}% improvement
                      </Badge>
                    )}
                    {a.price?.final_discussed != null && (
                      <Badge className={a.within_authority === false ? "border-accent/30 text-accent" : ""}>
                        final discussed {a.price.currency} {a.price.final_discussed}
                      </Badge>
                    )}
                  </div>
                </>
              ) : busy ? (
                <div className="flex items-center gap-2 text-white/50 text-sm"><Spinner /> Analysing…</div>
              ) : (
                <p className="text-white/40 text-sm">No analysis available.</p>
              )}
            </Card>
          </div>

          {/* Terms */}
          {a.terms?.length > 0 && (
            <div>
              <SectionLabel>Negotiated terms</SectionLabel>
              <Card className="p-5 space-y-2" data-testid="terms-list">
                {a.terms.map((t, i) => {
                  const st = TERM_STATUS[t.status] || TERM_STATUS.UNCLEAR;
                  const Icon = st.icon;
                  return (
                    <div key={i} className="flex items-start justify-between gap-3 text-sm">
                      <div className="min-w-0">
                        <div className="text-white/50 text-[11px] uppercase tracking-wider">{t.field}</div>
                        <div className="text-white/85">{t.value}</div>
                      </div>
                      <span className={`shrink-0 inline-flex items-center gap-1 text-[9px] font-mono px-2 py-1 rounded-md border ${st.cls}`}>
                        <Icon size={10} /> {t.status.replace(/_/g, " ")}
                      </span>
                    </div>
                  );
                })}
              </Card>
            </div>
          )}

          {/* Lists */}
          {[
            ["Supplier objections", a.supplier_objections, AlertTriangle, "text-yellow-300"],
            ["Unresolved items", a.unresolved_issues, HelpCircle, "text-white/60"],
            ["Differences from requirements", a.differences_from_requirements, ShieldAlert, "text-accent"],
            ["Risks", a.risks, AlertTriangle, "text-accent"],
          ].map(([label, items, Icon, color]) =>
            items?.length ? (
              <div key={label}>
                <SectionLabel>{label}</SectionLabel>
                <Card className="p-5">
                  <ul className="space-y-1.5">
                    {items.map((x, i) => (
                      <li key={i} className={`text-sm flex gap-2 ${color}`}>
                        <Icon size={13} className="shrink-0 mt-0.5" /> <span className="text-white/70">{x}</span>
                      </li>
                    ))}
                  </ul>
                </Card>
              </div>
            ) : null
          )}

          {/* AI self-review */}
          {a.self_review && (
            <div>
              <SectionLabel>AI self-review</SectionLabel>
              <Card className="p-5 space-y-3 border-primary/20" data-testid="self-review">
                <div className="flex items-center gap-2 text-primary text-sm font-medium mb-1">
                  <Sparkles size={15} /> Transparent review
                </div>
                {[
                  ["What was discussed", a.self_review.what_was_discussed],
                  ["What changed", a.self_review.what_changed],
                  ["What the AI agreed to discuss", a.self_review.what_ai_agreed_to_discuss],
                  ["What requires human approval", a.self_review.what_requires_human_approval],
                  ["Recommended next step", a.self_review.recommended_next_step],
                ].map(([l, v]) =>
                  v ? (
                    <div key={l}>
                      <div className="text-[10px] uppercase tracking-wider text-white/40">{l}</div>
                      <div className="text-sm text-white/80">{v}</div>
                    </div>
                  ) : null
                )}
              </Card>
            </div>
          )}

          {/* Human approval gate */}
          <div>
            <SectionLabel>Human approval gate</SectionLabel>
            <Card className="p-5 border-accent/20" data-testid="approval-gate">
              {call.outcome ? (
                <div className="text-sm">
                  <div className="flex items-center gap-2 text-secondary font-medium">
                    <CheckCircle2 size={15} /> Decision: {call.outcome.decision.replace(/_/g, " ")}
                  </div>
                  <p className="text-xs text-white/40 mt-1">by {call.outcome.by}</p>
                </div>
              ) : (
                <>
                  <p className="text-xs text-white/50 mb-4">
                    No material commitment has been made. Choose how to proceed — nothing becomes an
                    order until you approve the next step.
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    <Button variant="success" size="sm" onClick={() => setOutcome("APPROVE_NEXT")} disabled={savingOutcome} data-testid="outcome-approve">
                      <ThumbsUp size={14} /> Approve next step
                    </Button>
                    <Button variant="secondary" size="sm" onClick={() => setOutcome("REQUEST_CHANGES")} disabled={savingOutcome} data-testid="outcome-changes">
                      <Edit3 size={14} /> Request changes
                    </Button>
                    <Button variant="secondary" size="sm" onClick={() => setOutcome("CONTINUE_NEGOTIATION")} disabled={savingOutcome} data-testid="outcome-continue">
                      <RefreshCw size={14} /> Continue negotiation
                    </Button>
                    <Button variant="danger" size="sm" onClick={() => setOutcome("REJECT")} disabled={savingOutcome} data-testid="outcome-reject">
                      <ThumbsDown size={14} /> Reject
                    </Button>
                  </div>
                </>
              )}
            </Card>
          </div>
        </div>
      </div>
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

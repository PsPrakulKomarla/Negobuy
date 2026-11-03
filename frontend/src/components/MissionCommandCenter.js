import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Activity, AlertCircle, CheckCircle2, Circle, Loader2, ShieldAlert, Bot } from "lucide-react";
import api from "../lib/api";
import { Card, SectionLabel, Badge } from "./ui";

const STAGE_LABELS = {
  REQUIREMENT_CREATED: "Requirement", VENDOR_DISCOVERY: "Discovery",
  VENDOR_VERIFICATION: "Verification", SHORTLIST_READY: "Shortlist",
  NEGOTIATION: "Negotiation", OFFERS_COLLECTED: "Offers", OFFERS_COMPARED: "Analysis",
  RECOMMENDATION_READY: "Recommend", AWAITING_HUMAN_DECISION: "Approval",
  SUPPLIER_SELECTED: "Selected", CONTRACT_REVIEW: "Contract",
  AWAITING_CONTRACT_APPROVAL: "Contract", ORDER_AUTHORIZED: "Order",
  ORDER_TRACKING: "Tracking", DELIVERY_PENDING_VERIFICATION: "Delivery", COMPLETED: "Complete",
};

export default function MissionCommandCenter({ missionId }) {
  const [orch, setOrch] = useState(null);
  const [audit, setAudit] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = async () => {
    setError(false);
    try {
      const [o, a] = await Promise.all([
        api.get(`/missions/${missionId}/orchestrator`).then((r) => r.data),
        api.get(`/audit?mission_id=${missionId}`).then((r) => r.data).catch(() => []),
      ]);
      setOrch(o);
      setAudit(Array.isArray(a) ? a : []);
    } catch (e) {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line
  }, [missionId]);

  if (loading)
    return (
      <Card className="p-6 mb-6 flex items-center gap-3" data-testid="command-center-loading">
        <Loader2 className="w-5 h-5 animate-spin text-primary" />
        <span className="text-white/50 text-sm">Loading mission command center…</span>
      </Card>
    );

  if (error || !orch || orch.error)
    return (
      <Card className="p-6 mb-6" data-testid="command-center-error">
        <div className="flex items-center gap-3 text-accent">
          <AlertCircle size={18} /> <span className="text-sm">Could not load orchestrator state.</span>
          <button onClick={load} className="ml-auto text-xs underline text-white/60 hover:text-white">Retry</button>
        </div>
      </Card>
    );

  const stages = orch.lifecycle || [];
  const idx = orch.stage_index ?? -1;

  return (
    <div className="mb-8" data-testid="mission-command-center">
      {/* AI current activity + approval banner */}
      <Card glass className="p-6 mb-4 relative overflow-hidden">
        <div className="absolute -top-16 -right-16 w-56 h-56 bg-primary/10 blur-[90px] rounded-full" />
        <div className="relative z-10 flex flex-col lg:flex-row lg:items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center">
              <Bot size={20} className="text-primary" />
            </div>
            <div>
              <div className="text-[10px] font-mono tracking-widest uppercase text-primary/80">
                NegoBuy is {orch.human_action_required ? "waiting on you" : "working"}
              </div>
              <div className="font-medium text-white/90" data-testid="cc-status-summary">{orch.status_summary}</div>
              <div className="text-xs text-white/40 mt-0.5">
                Next agent: <span className="text-secondary">{orch.next_agent}</span> · Stage: {STAGE_LABELS[orch.stage] || orch.stage}
              </div>
            </div>
          </div>
          <div className="flex-1" />
          {orch.human_action_required && (
            <div className="flex items-center gap-2 rounded-xl border border-accent/30 bg-accent/10 px-4 py-2.5" data-testid="cc-approval-banner">
              <ShieldAlert size={18} className="text-accent" />
              <span className="text-sm text-accent font-medium">Action required — review below</span>
            </div>
          )}
        </div>
        {orch.available_actions?.length > 0 && (
          <div className="relative z-10 flex flex-wrap gap-2 mt-4">
            {orch.available_actions.map((a, i) => (
              <span key={i} className="inline-flex items-center gap-1.5 text-[11px] font-mono px-3 py-1.5 rounded-full border border-white/12 bg-white/5 text-white/70" data-testid={`cc-action-${i}`}>
                {a.requires_human ? <ShieldAlert size={11} className="text-accent" /> : <Activity size={11} className="text-primary" />}
                {a.action} · {a.agent}
              </span>
            ))}
          </div>
        )}
      </Card>

      {/* Lifecycle bar */}
      <SectionLabel>Procurement lifecycle</SectionLabel>
      <Card className="p-5 mb-4 overflow-x-auto" data-testid="cc-lifecycle">
        <div className="flex items-center gap-1 min-w-[720px]">
          {stages.map((s, i) => {
            const done = i < idx;
            const current = i === idx;
            const attention = current && orch.human_action_required;
            return (
              <React.Fragment key={s}>
                <div className="flex flex-col items-center gap-1.5 shrink-0" style={{ width: 74 }}>
                  <div className={`w-7 h-7 rounded-full flex items-center justify-center border ${
                    attention ? "bg-accent/20 border-accent text-accent" :
                    current ? "bg-primary/20 border-primary text-primary animate-pulse" :
                    done ? "bg-secondary/20 border-secondary/50 text-secondary" :
                    "bg-white/5 border-white/12 text-white/30"}`}>
                    {done ? <CheckCircle2 size={15} /> : current ? <Activity size={14} /> : <Circle size={11} />}
                  </div>
                  <span className={`text-[9px] uppercase tracking-wider text-center ${current ? "text-primary" : done ? "text-secondary/70" : "text-white/30"}`}>
                    {STAGE_LABELS[s] || s}
                  </span>
                </div>
                {i < stages.length - 1 && <div className={`h-0.5 flex-1 rounded ${i < idx ? "bg-secondary/40" : "bg-white/8"}`} />}
              </React.Fragment>
            );
          })}
        </div>
      </Card>

      {/* Audit timeline */}
      <SectionLabel>Mission audit timeline</SectionLabel>
      <Card className="p-5" data-testid="cc-audit">
        {audit.length ? (
          <div className="space-y-3 max-h-72 overflow-y-auto">
            {audit.map((e, i) => (
              <motion.div key={e.id || i} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.02 }}
                className="flex items-start gap-3 text-sm">
                <span className="text-[10px] font-mono text-white/30 mt-0.5 shrink-0 w-24">
                  {(e.created_at || "").slice(5, 16).replace("T", " ")}
                </span>
                <div>
                  <Badge>{(e.event_type || "").replace(/_/g, " ")}</Badge>
                  <span className="text-white/70 ml-2">{e.detail}</span>
                  {e.actor && <span className="text-white/35 ml-1">— {e.actor}</span>}
                </div>
              </motion.div>
            ))}
          </div>
        ) : (
          <p className="text-white/30 text-sm text-center py-6" data-testid="cc-audit-empty">
            No audit activity yet. Actions will appear here as the mission progresses.
          </p>
        )}
      </Card>
    </div>
  );
}

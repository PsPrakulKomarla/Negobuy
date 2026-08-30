import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PhoneCall, Clock, Mic, FileText, ChevronRight } from "lucide-react";
import api from "../lib/api";
import { Card, SectionLabel, Badge, Spinner } from "./ui";

const STATUS_COLOR = (s) => {
  if (["SIMULATED_COMPLETE", "completed"].includes(s)) return "text-secondary";
  if (["failed", "no-answer", "busy", "NOT_CONFIGURED"].includes(s)) return "text-accent";
  return "text-primary";
};

export default function CallHistory({ missionId }) {
  const [calls, setCalls] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get(`/voice/console/history?mission_id=${missionId}`)
      .then((r) => setCalls(r.data))
      .catch(() => setCalls([]))
      .finally(() => setLoading(false));
  }, [missionId]);

  if (loading)
    return (
      <div className="py-6 flex justify-center">
        <Spinner />
      </div>
    );
  if (!calls.length) return null;

  return (
    <div data-testid="call-history">
      <SectionLabel>Call history</SectionLabel>
      <Card className="divide-y divide-white/5">
        {calls.map((c) => (
          <Link
            key={c.session_ref}
            to={`/missions/${missionId}/call-review/${c.session_ref}`}
            className="flex items-center gap-4 p-4 hover:bg-white/5 transition-colors group"
            data-testid={`call-history-${c.session_ref}`}
          >
            <div className="w-9 h-9 rounded-full bg-primary/10 border border-primary/25 flex items-center justify-center shrink-0">
              <PhoneCall size={15} className="text-primary" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium text-sm truncate">{c.vendor_name}</span>
                {c.simulation && <Badge>sim</Badge>}
              </div>
              <div className="text-xs text-white/40 truncate">
                {c.key_outcome || c.objective?.product || "—"}
              </div>
            </div>
            <div className="hidden sm:flex items-center gap-4 text-[11px] text-white/40 shrink-0">
              <span className="flex items-center gap-1"><Clock size={11} /> {c.duration != null ? `${c.duration}s` : "—"}</span>
              <span className="flex items-center gap-1" title="Recording">
                <Mic size={11} className={c.recording_state === "RECORDING_AVAILABLE" ? "text-secondary" : ""} />
                {c.recording_state === "RECORDING_AVAILABLE" ? "rec" : "—"}
              </span>
              <span className="flex items-center gap-1" title="Transcript">
                <FileText size={11} className={c.transcript_status === "AVAILABLE" ? "text-secondary" : ""} />
                {c.transcript_status === "AVAILABLE" ? "txt" : "—"}
              </span>
            </div>
            <span className={`text-[10px] font-mono uppercase ${STATUS_COLOR(c.status)} shrink-0`}>
              {(c.status || "").replace(/_/g, " ")}
            </span>
            <ChevronRight size={16} className="text-white/20 group-hover:text-white/50 transition-colors shrink-0" />
          </Link>
        ))}
      </Card>
    </div>
  );
}

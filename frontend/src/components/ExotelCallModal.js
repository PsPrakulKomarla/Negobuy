import React, { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, PhoneCall, ShieldAlert, Radio, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { Button, Spinner, Badge, Input } from "./ui";

const TERMINAL = ["completed", "failed", "no-answer", "busy", "NOT_CONFIGURED", "INVALID_CREDENTIALS"];
const STEPS = ["initiating", "calling", "connected", "completed"];

function statusMeta(s) {
  if (["completed"].includes(s)) return { color: "text-secondary", icon: CheckCircle2 };
  if (["failed", "no-answer", "busy", "NOT_CONFIGURED", "INVALID_CREDENTIALS"].includes(s))
    return { color: "text-accent", icon: XCircle };
  return { color: "text-primary", icon: Loader2 };
}

export default function ExotelCallModal({ missionId, mission, vendor, defaultNumber, onClose }) {
  const [providerReady, setProviderReady] = useState(null);
  const [number, setNumber] = useState(
    defaultNumber || (vendor.contact_phones || [])[0] || "9008136500"
  );
  const [phase, setPhase] = useState("confirm"); // confirm | placing | tracking
  const [session, setSession] = useState(null);
  const [error, setError] = useState("");
  const pollRef = useRef(null);

  useEffect(() => {
    api
      .get("/voice/exotel/status")
      .then((r) => setProviderReady(r.data))
      .catch(() => setProviderReady({ state: "NOT_CONFIGURED" }));
    return () => clearInterval(pollRef.current);
  }, []);

  const poll = (ref) => {
    clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const { data } = await api.get(`/voice/exotel/session/${ref}`);
        setSession(data);
        if (TERMINAL.includes(data.status)) clearInterval(pollRef.current);
      } catch (_) {}
    }, 3000);
  };

  const placeCall = async () => {
    setPhase("placing");
    setError("");
    try {
      const { data } = await api.post("/voice/exotel/call", {
        mission_id: missionId,
        vendor_id: vendor.id,
        to_number: number,
      });
      setPhase("tracking");
      if (data.status === "NOT_CONFIGURED") {
        setSession({ status: "NOT_CONFIGURED", message: data.message });
        toast.error("Exotel is not configured to place the call.");
        return;
      }
      setSession({ status: data.status, session_ref: data.session_ref, call_sid: data.provider_call_sid });
      if (data.session_ref) poll(data.session_ref);
      if (data.accepted) toast.success("Call request accepted by Exotel");
      else toast.error(`Exotel did not accept the call (HTTP ${data.http_status || "?"})`);
    } catch (err) {
      setPhase("confirm");
      setError(formatApiError(err.response?.data?.detail) || "Could not place the call.");
    }
  };

  const meta = statusMeta(session?.status);
  const StatusIcon = meta.icon;

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 backdrop-blur-sm p-4 sm:p-8"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        data-testid="exotel-call-modal"
      >
        <motion.div
          className="glass-strong rounded-2xl w-full max-w-lg relative border border-white/10 my-8"
          initial={{ opacity: 0, y: 24, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 24 }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between p-5 border-b hairline">
            <div className="flex items-center gap-2">
              <PhoneCall size={18} className="text-primary" />
              <div>
                <div className="text-[10px] font-mono tracking-widest text-primary/80 uppercase">
                  Exotel voice call
                </div>
                <h3 className="font-display text-lg font-bold">{vendor.name}</h3>
              </div>
            </div>
            <button onClick={onClose} className="text-white/40 hover:text-white transition-colors" data-testid="exotel-close">
              <X size={20} />
            </button>
          </div>

          <div className="p-5 space-y-4">
            {providerReady && providerReady.state !== "READY" && (
              <div className="rounded-xl border border-yellow-400/25 bg-yellow-400/5 p-3 text-sm text-yellow-200" data-testid="exotel-not-ready">
                Exotel status: <b>{providerReady.state}</b>. {providerReady.message}
              </div>
            )}

            {phase === "confirm" && (
              <>
                <div className="rounded-xl border border-white/10 bg-white/5 p-4 space-y-2 text-sm">
                  <Row label="Mission" value={mission?.title} />
                  <Row label="Vendor" value={vendor.name} />
                </div>
                <Input
                  label="Destination number"
                  value={number}
                  onChange={(e) => setNumber(e.target.value)}
                  data-testid="exotel-destination"
                  placeholder="+919008136500"
                />
                <div className="rounded-xl border border-accent/20 bg-accent/5 p-3 text-xs text-white/60 flex gap-2">
                  <ShieldAlert size={14} className="text-accent shrink-0 mt-0.5" />
                  <span>
                    The AI negotiates within your authority limits only. This call will
                    <b className="text-white/80"> never</b> create an offer, order, purchase or approval — a human approves everything.
                  </span>
                </div>
                {error && <div className="text-sm text-accent">{error}</div>}
                <div className="flex justify-end gap-2">
                  <Button variant="ghost" onClick={onClose} data-testid="exotel-cancel">Cancel</Button>
                  <Button onClick={placeCall} data-testid="exotel-confirm-call">
                    <PhoneCall size={16} /> Confirm &amp; place call to {number}
                  </Button>
                </div>
              </>
            )}

            {phase === "placing" && (
              <div className="py-10 flex flex-col items-center gap-3">
                <Spinner className="w-8 h-8" />
                <p className="text-white/50 text-sm">Requesting Exotel to place the call…</p>
              </div>
            )}

            {phase === "tracking" && (
              <div className="space-y-4" data-testid="exotel-status-panel">
                <div className="flex items-center gap-3">
                  <StatusIcon size={22} className={`${meta.color} ${!TERMINAL.includes(session?.status) ? "animate-spin" : ""}`} />
                  <div>
                    <div className="text-[10px] font-mono uppercase tracking-widest text-white/40">Call status</div>
                    <div className={`font-display text-xl font-bold ${meta.color}`} data-testid="exotel-status-value">
                      {(session?.status || "…").replace(/_/g, " ")}
                    </div>
                  </div>
                  <div className="flex-1" />
                  <Radio size={16} className="text-primary animate-pulse" />
                </div>

                {/* progress rail */}
                <div className="flex items-center gap-1">
                  {STEPS.map((s, i) => {
                    const reached = STEPS.indexOf(session?.status) >= i || session?.status === "completed";
                    return (
                      <div key={s} className="flex-1">
                        <div className={`h-1.5 rounded-full ${reached ? "bg-primary" : "bg-white/10"}`} />
                        <div className={`mt-1 text-[9px] uppercase tracking-wider ${reached ? "text-primary/80" : "text-white/30"}`}>{s}</div>
                      </div>
                    );
                  })}
                </div>

                <div className="rounded-xl border border-white/10 bg-white/5 p-4 space-y-2 text-sm">
                  {session?.call_sid && <Row label="Provider call ID" value={session.call_sid} mono />}
                  {session?.to && <Row label="Destination" value={session.to} mono />}
                  {session?.duration && <Row label="Duration" value={`${session.duration}s`} />}
                  {session?.recording_url && (
                    <Row label="Recording" value={<a className="text-primary underline" href={session.recording_url} target="_blank" rel="noreferrer">listen</a>} />
                  )}
                  {session?.authority && (
                    <Row label="Authority (read-only)" value={`max ${session.authority.currency} ${session.authority.max_price_per_unit ?? "—"}/unit`} />
                  )}
                  {session?.message && <p className="text-white/50 text-xs">{session.message}</p>}
                </div>

                {session?.reported_offer && Object.keys(session.reported_offer).length > 0 && (
                  <div className="rounded-xl border border-secondary/20 bg-secondary/5 p-3 text-xs">
                    <div className="text-secondary font-medium mb-1">Reported by call (not applied)</div>
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(session.reported_offer).map(([k, v]) => (
                        <Badge key={k}>{k}: {String(v)}</Badge>
                      ))}
                    </div>
                    <p className="text-white/40 mt-2">Stored for your review — no offer/order was created automatically.</p>
                  </div>
                )}

                <div className="flex justify-end">
                  <Button variant="secondary" onClick={onClose} data-testid="exotel-done">Done</Button>
                </div>
              </div>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

function Row({ label, value, mono }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-white/40 text-xs uppercase tracking-wider shrink-0">{label}</span>
      <span className={`text-white/85 text-right ${mono ? "font-mono text-xs" : "font-medium"}`}>{value ?? "—"}</span>
    </div>
  );
}

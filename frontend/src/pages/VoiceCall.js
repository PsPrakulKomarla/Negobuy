import React, { useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, PhoneOff, Mic, Settings, Target, ShieldAlert, Radio } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import RealtimeAudioChat from "../lib/RealtimeAudioChat";
import { Button, Card, Spinner, SectionLabel, StatusPill } from "../components/ui";

function Waveform({ active }) {
  const bars = 40;
  return (
    <div className="flex items-center justify-center gap-1 h-24">
      {new Array(bars).fill(0).map((_, i) => (
        <motion.span
          key={i}
          className="w-1 rounded-full bg-primary"
          animate={active ? { height: [6, 10 + Math.random() * 60, 6] } : { height: 4 }}
          transition={{
            duration: 0.7 + Math.random() * 0.6,
            repeat: active ? Infinity : 0,
            ease: "easeInOut",
            delay: i * 0.02,
          }}
          style={{ opacity: active ? 0.5 + Math.random() * 0.5 : 0.2 }}
        />
      ))}
    </div>
  );
}

function fmt(sec) {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function VoiceCall() {
  const { id, vendorId } = useParams();
  const [status, setStatus] = useState(null);
  const [mission, setMission] = useState(null);
  const [vendor, setVendor] = useState(null);
  const [loading, setLoading] = useState(true);
  const [callState, setCallState] = useState("READY"); // READY|CONNECTING|CONNECTED|LISTENING|SPEAKING|ENDED|FAILED
  const [transcript, setTranscript] = useState([]);
  const [elapsed, setElapsed] = useState(0);
  const chatRef = useRef(null);
  const timerRef = useRef(null);
  const startRef = useRef(0);

  useEffect(() => {
    Promise.all([
      api.get("/voice/status").then((r) => r.data).catch(() => ({ configured: false })),
      api.get(`/missions/${id}`).then((r) => r.data),
      api.get(`/missions/${id}/vendors`).then((r) => r.data),
    ])
      .then(([s, m, vs]) => {
        setStatus(s);
        setMission(m);
        setVendor(vs.find((v) => v.id === vendorId));
      })
      .finally(() => setLoading(false));
    return () => {
      chatRef.current?.stop();
      clearInterval(timerRef.current);
    };
    // eslint-disable-next-line
  }, [id, vendorId]);

  if (loading)
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Spinner className="w-8 h-8" />
      </div>
    );

  const configured = status?.configured;
  const remaining = status?.minutes?.remaining;
  const qty = mission?.quantity || 1;
  const maxPrice = mission?.budget && qty ? Math.round(mission.budget / qty) : null;
  const target = maxPrice ? Math.round(maxPrice * 0.9) : null;
  const active = ["CONNECTED", "LISTENING", "SPEAKING"].includes(callState);

  const instructions =
    `You are NegoBuy's AI procurement buyer negotiating by voice with ${vendor?.name || "a supplier"}. ` +
    `Mission: procure ${mission?.quantity || ""} ${mission?.title || ""} delivered to ${mission?.delivery_location || "the buyer"}` +
    `${mission?.deadline_days ? ` within ${mission.deadline_days} days` : ""}. ` +
    `Negotiate professionally and naturally toward a target price of ${mission?.currency || ""} ${target || "the best possible"} per unit. ` +
    `You are NEVER authorized to exceed ${mission?.currency || ""} ${maxPrice || "the buyer's maximum"} per unit or to make binding commitments. ` +
    `Ask about pricing, MOQ, lead time, warranty and payment terms. Be concise and human.`;

  const startTimer = () => {
    startRef.current = Date.now();
    timerRef.current = setInterval(() => {
      setElapsed((Date.now() - startRef.current) / 1000);
    }, 500);
  };

  const startCall = async () => {
    if (remaining === 0) {
      toast.error("You're out of voice minutes on this plan. Upgrade to continue.");
      return;
    }
    setTranscript([]);
    setCallState("CONNECTING");
    const chat = new RealtimeAudioChat({
      instructions,
      onState: (s) => setCallState(s),
      onError: () => toast.error("Could not start the call. Check microphone permissions."),
      onTranscript: (t) => {
        if (!t.done) return;
        setTranscript((prev) => [...prev, { role: t.role, text: t.text }]);
      },
    });
    chatRef.current = chat;
    try {
      await chat.init();
      startTimer();
    } catch (_) {}
  };

  const endCall = async () => {
    chatRef.current?.stop();
    clearInterval(timerRef.current);
    setCallState("ENDED");
    const secs = elapsed;
    setElapsed(0);
    if (secs > 1) {
      try {
        const { data } = await api.post("/voice/usage", { seconds: secs });
        setStatus((s) => ({ ...s, minutes: data }));
      } catch (_) {}
    }
  };

  return (
    <div className="p-6 lg:p-10 max-w-6xl mx-auto">
      <Link to={`/missions/${id}`} className="inline-flex items-center gap-2 text-white/40 hover:text-white text-sm mb-6 transition-colors">
        <ArrowLeft size={15} /> Back to mission
      </Link>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <Card glass className="p-8 relative overflow-hidden">
            <div className="absolute -top-20 -right-20 w-72 h-72 bg-primary/10 blur-[100px] rounded-full" />
            <div className="relative z-10">
              <div className="flex items-center justify-between mb-8">
                <div className="flex items-center gap-2 text-xs font-mono tracking-widest text-primary/80">
                  <Radio size={13} /> LIVE CALL INTERFACE
                </div>
                <div className="flex items-center gap-3">
                  {active && <span className="text-xs font-mono text-primary" data-testid="call-timer">{fmt(elapsed)}</span>}
                  <StatusPill status={active ? "CONTACTING" : configured ? "REQUIREMENT_REVIEW" : "DRAFT"} />
                </div>
              </div>

              <div className="text-center mb-6">
                <div className="w-24 h-24 mx-auto rounded-full bg-primary/10 border border-primary/30 flex items-center justify-center mb-4 glow-primary">
                  <span className="font-display text-3xl font-bold text-primary">
                    {(vendor?.name || "V").slice(0, 1).toUpperCase()}
                  </span>
                </div>
                <h2 className="font-display text-2xl font-bold tracking-tight">{vendor?.name || "Vendor"}</h2>
                <p className="text-white/40 text-sm mt-1" data-testid="call-state">
                  {configured ? callState.replace(/_/g, " ").toLowerCase() : "Voice negotiation offline"}
                </p>
              </div>

              <Waveform active={active && callState !== "LISTENING"} />

              {!configured ? (
                <div className="mt-8 rounded-2xl border border-yellow-400/25 bg-yellow-400/5 p-5">
                  <div className="flex items-center gap-2 text-yellow-300 text-sm font-medium mb-2">
                    <Settings size={16} /> Requires configuration
                  </div>
                  <p className="text-sm text-white/60 leading-relaxed">
                    {status?.message || "Realtime voice needs an OpenAI Realtime API key."}
                  </p>
                </div>
              ) : (
                <div className="mt-8 flex flex-col items-center gap-3">
                  <div className="flex justify-center gap-4">
                    {!active ? (
                      <Button size="lg" onClick={startCall} disabled={callState === "CONNECTING"} data-testid="start-call-btn">
                        {callState === "CONNECTING" ? <Spinner /> : <Mic size={18} />} Start call
                      </Button>
                    ) : (
                      <Button size="lg" variant="danger" onClick={endCall} data-testid="end-call-btn">
                        <PhoneOff size={18} /> End call
                      </Button>
                    )}
                  </div>
                  <p className="text-[11px] text-white/40 font-mono">
                    {remaining != null ? `${remaining} voice min remaining on your plan` : "Unlimited voice minutes"}
                  </p>
                </div>
              )}
            </div>
          </Card>

          <div className="mt-6">
            <SectionLabel>Live transcript</SectionLabel>
            <Card className="p-6 min-h-[160px]" data-testid="transcript-panel">
              {transcript.length ? (
                <div className="space-y-3">
                  {transcript.map((t, i) => (
                    <div key={i} className={`text-sm ${t.role === "ai" ? "text-primary" : "text-white/80"}`}>
                      <span className="text-[10px] font-mono uppercase tracking-wider mr-2 opacity-60">
                        {t.role === "ai" ? "AI Buyer" : "Vendor"}
                      </span>
                      {t.text}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-white/30 text-sm text-center py-6">
                  {active ? "Listening… transcript will appear as you speak." : "Transcript will stream here during the call."}
                </p>
              )}
            </Card>
          </div>
        </div>

        <div className="space-y-6">
          <div>
            <SectionLabel>Negotiation objective</SectionLabel>
            <Card className="p-5 space-y-3 text-sm">
              <div className="flex items-center gap-2 text-primary mb-1">
                <Target size={15} /> <span className="font-medium">Mission</span>
              </div>
              <Row label="Item" value={mission?.title} />
              <Row label="Quantity" value={mission?.quantity} />
              <Row label="Deliver to" value={mission?.delivery_location} />
              <Row label="Deadline" value={mission?.deadline_days ? `${mission.deadline_days} days` : "—"} />
              <Row label="Warranty" value={mission?.warranty_requirements || "—"} />
            </Card>
          </div>

          <div>
            <SectionLabel>Authority boundary</SectionLabel>
            <Card className="p-5 space-y-3 text-sm border-accent/20">
              <div className="flex items-center gap-2 text-accent mb-1">
                <ShieldAlert size={15} /> <span className="font-medium">Hard limits</span>
              </div>
              <Row label="Target price" value={target ? `${mission.currency} ${target}/unit` : "—"} accent="text-secondary" />
              <Row label="Max authorized" value={maxPrice ? `${mission.currency} ${maxPrice}/unit` : "—"} accent="text-accent" />
              <p className="text-[11px] text-white/40 pt-2 border-t hairline">
                The AI negotiates toward target and never exceeds the authorized maximum without your explicit approval.
              </p>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, accent = "text-white/80" }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-white/40 text-xs uppercase tracking-wider">{label}</span>
      <span className={`font-medium ${accent}`}>{value ?? "—"}</span>
    </div>
  );
}

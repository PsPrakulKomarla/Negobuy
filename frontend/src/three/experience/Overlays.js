import React, { useState } from "react";
import { Link } from "react-router-dom";
import { motion, useTransform, useMotionValueEvent } from "framer-motion";
import {
  ChevronDown,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  ShieldCheck,
  Gavel,
  Trophy,
} from "lucide-react";
import { SCENES } from "./helpers";
import { STORY } from "./story";
import { Button } from "../../components/ui";

function Label({ children }) {
  return (
    <div className="flex items-center gap-3 mb-4">
      <span className="w-6 h-px bg-primary/60" />
      <span className="text-[11px] tracking-[0.3em] uppercase text-primary/80 font-mono">{children}</span>
    </div>
  );
}

function MotionNumber({ mv, fmt }) {
  const [txt, setTxt] = useState(() => fmt(mv.get()));
  useMotionValueEvent(mv, "change", (v) => setTxt(fmt(v)));
  return <span>{txt}</span>;
}

function StatGrid({ stats, cols = "grid-cols-2 sm:grid-cols-3" }) {
  return (
    <div className={`grid ${cols} gap-px bg-white/10 rounded-xl overflow-hidden border border-white/10`}>
      {stats.map((s) => (
        <div key={s.k} className="bg-[#0a0f1c] px-4 py-3">
          <div className="text-[10px] font-mono tracking-widest uppercase text-white/40">{s.k}</div>
          <div className="font-display text-lg mt-1">{s.v}</div>
        </div>
      ))}
    </div>
  );
}

function EnterContent({ data }) {
  return (
    <div className="text-center">
      <div className="inline-flex items-center gap-2 text-[11px] font-mono tracking-widest uppercase text-primary/90 border border-primary/25 rounded-full px-4 py-1.5 mb-8 bg-primary/5">
        <Sparkles size={13} /> AI Procurement Operator · Illustrative walkthrough
      </div>
      <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tighter leading-[1.05] max-w-4xl mx-auto">
        Your AI Buyer for the <span className="text-primary text-glow">real world.</span>
      </h1>
      <p className="mt-6 text-lg text-white/65 leading-relaxed max-w-xl mx-auto">{data.body}</p>
      <motion.div
        className="mt-14 flex flex-col items-center gap-2 text-white/45"
        animate={{ y: [0, 8, 0] }}
        transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
      >
        <span className="text-[11px] font-mono tracking-[0.3em] uppercase">Scroll to enter the mission</span>
        <ChevronDown size={20} />
      </motion.div>
    </div>
  );
}

function RequestContent({ data, spMV, i }) {
  const created = useTransform(spMV, [i + 0.15, i + 0.4], [0, 1]);
  return (
    <div className="max-w-lg">
      <Label>{data.label}</Label>
      <h2 className="font-display text-3xl lg:text-4xl font-bold tracking-tight mb-6">{data.title}</h2>
      <div className="glass rounded-2xl p-5 font-mono text-sm text-white/80 leading-relaxed border border-primary/20">
        <span className="text-primary/70">buyer@negobuy ~ $ </span>
        {data.request}
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        {data.shards.map((s) => (
          <span key={s} className="text-[11px] font-mono tracking-wider px-3 py-1.5 rounded-lg border border-primary/25 bg-primary/5 text-primary/90">
            {s}
          </span>
        ))}
      </div>
      <motion.div style={{ opacity: created }} className="mt-6 inline-flex items-center gap-2 text-secondary text-sm font-mono tracking-widest uppercase">
        <CheckCircle2 size={16} /> Mission created
      </motion.div>
    </div>
  );
}

function DiscoveryContent({ data }) {
  return (
    <div className="max-w-md ml-auto text-right">
      <Label>{data.label}</Label>
      <h2 className="font-display text-3xl lg:text-4xl font-bold tracking-tight mb-3">{data.title}</h2>
      <p className="text-white/60 text-sm mb-6">{data.body}</p>
      <div className="mt-2 space-y-2">
        {data.funnel.map((f, idx) => (
          <div key={f.k} className="flex items-center justify-end gap-3">
            <span className="text-sm text-white/50">{f.k}</span>
            <span className={`font-display tabular-nums w-24 text-right ${idx === data.funnel.length - 1 ? "text-4xl text-secondary text-glow" : idx === 0 ? "text-4xl text-primary text-glow" : "text-xl text-white/85"}`}>
              {f.v}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function IntelContent({ data }) {
  return (
    <div className="max-w-md">
      <Label>{data.label}</Label>
      <h2 className="font-display text-3xl lg:text-4xl font-bold tracking-tight mb-3">{data.title}</h2>
      <p className="text-white/60 text-sm mb-5">{data.body}</p>
      <div className="glass rounded-2xl p-5">
        <div className="flex items-center justify-between mb-4">
          <span className="font-display text-lg">Supplier A</span>
          <span className="text-[10px] font-mono tracking-widest uppercase text-secondary border border-secondary/30 bg-secondary/10 px-2.5 py-1 rounded-full">
            Evidence-backed
          </span>
        </div>
        <StatGrid stats={data.stats} />
      </div>
    </div>
  );
}

function VerifyContent({ data }) {
  return (
    <div className="max-w-md ml-auto">
      <Label>{data.label}</Label>
      <h2 className="font-display text-3xl lg:text-4xl font-bold tracking-tight mb-3">{data.title}</h2>
      <p className="text-white/60 text-sm mb-5">{data.body}</p>
      <div className="glass rounded-2xl p-5 space-y-2.5">
        {data.checks.map((c) => (
          <div key={c.k} className="flex items-center justify-between text-sm">
            <span className="text-white/75">{c.k}</span>
            {c.s === "verified" ? (
              <span className="inline-flex items-center gap-1.5 text-secondary text-xs font-mono uppercase tracking-wider">
                <CheckCircle2 size={14} /> Verified
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 text-yellow-300 text-xs font-mono uppercase tracking-wider">
                <AlertTriangle size={14} /> Review
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function NegotiationContent({ data, spMV }) {
  const price = useTransform(spMV, [4.8, 5.5], [900, 875]);
  return (
    <div className="max-w-lg">
      <Label>{data.label}</Label>
      <h2 className="font-display text-3xl lg:text-4xl font-bold tracking-tight mb-5">{data.title}</h2>
      <div className="glass rounded-2xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-mono tracking-widest uppercase text-white/40">Price / unit</span>
          <div className="font-display text-4xl font-bold text-primary tabular-nums">
            <MotionNumber mv={price} fmt={(v) => `₹${Math.round(v)}`} />
          </div>
        </div>
        <div className="text-sm text-white/70 border-l-2 border-primary/40 pl-3">
          “For a confirmed 500 units, can you improve that price?”
        </div>
        <div className="grid grid-cols-3 gap-px bg-white/10 rounded-lg overflow-hidden border border-white/10">
          {data.terms.map((t) => (
            <div key={t.k} className="bg-[#0a0f1c] px-3 py-2.5">
              <div className="text-[9px] font-mono tracking-widest uppercase text-white/40">{t.k}</div>
              <div className="text-sm mt-0.5">{t.v}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function WarRoomContent({ data }) {
  return (
    <div className="max-w-lg mx-auto text-center">
      <Label>{data.label}</Label>
      <h2 className="font-display text-3xl lg:text-4xl font-bold tracking-tight mb-2">{data.title}</h2>
      <p className="text-white/60 text-sm mb-6">{data.body}</p>
      <div className="grid grid-cols-2 gap-3 text-left">
        {data.vendors.map((v) => (
          <div key={v.k} className={`rounded-xl p-4 border ${v.lead ? "border-secondary/40 bg-secondary/10" : "border-white/10 bg-[#0a0f1c]"}`}>
            <div className="flex items-center justify-between">
              <span className="text-sm text-white/75">{v.k}</span>
              {v.lead && <Trophy size={14} className="text-secondary" />}
            </div>
            <div className={`font-display text-2xl mt-1 ${v.lead ? "text-secondary" : "text-white/90"}`}>{v.v}</div>
            <div className="text-[10px] font-mono tracking-wider uppercase text-white/35 mt-1">per unit</div>
          </div>
        ))}
      </div>
      <div className="text-[11px] font-mono tracking-widest uppercase text-white/40 mt-5">
        Lowest price ≠ winner · scored on landed cost, delivery, warranty, reliability & risk
      </div>
    </div>
  );
}

function LandedContent({ data }) {
  return (
    <div className="max-w-md ml-auto">
      <Label>{data.label}</Label>
      <h2 className="font-display text-3xl lg:text-4xl font-bold tracking-tight mb-3">{data.title}</h2>
      <p className="text-white/60 text-sm mb-5">{data.body}</p>
      <div className="glass rounded-2xl p-5 space-y-2">
        {data.cost.map((c, idx) => (
          <div key={c.k} className="flex items-center justify-between text-sm">
            <span className="text-white/60">
              {idx > 0 && <span className="text-primary/60 mr-1">+</span>}
              {c.k}
              {c.assumption && (
                <span className="ml-2 text-[9px] font-mono tracking-wider uppercase text-yellow-300 border border-yellow-400/30 bg-yellow-400/10 px-1.5 py-0.5 rounded">
                  Assumption
                </span>
              )}
            </span>
            <span className="font-mono text-white/85">{c.v}</span>
          </div>
        ))}
        <div className="border-t border-white/10 pt-3 mt-1 flex items-center justify-between">
          <span className="text-[11px] font-mono tracking-widest uppercase text-white/50">Total landed cost</span>
          <span className="font-display text-2xl text-primary">{data.total}</span>
        </div>
      </div>
    </div>
  );
}

function RecommendContent({ data }) {
  return (
    <div className="max-w-md">
      <Label>{data.label}</Label>
      <div className="glass rounded-2xl p-6 tracing-border">
        <div className="flex items-center gap-2 text-secondary text-[11px] font-mono tracking-widest uppercase mb-4">
          <ShieldCheck size={15} /> Recommended supplier
        </div>
        <h2 className="font-display text-3xl font-bold tracking-tight mb-5">Supplier B</h2>
        <StatGrid stats={data.stats} />
        <p className="text-sm text-white/60 leading-relaxed mt-5 border-l-2 border-secondary/40 pl-3">{data.body}</p>
      </div>
    </div>
  );
}

function DecisionContent({ data }) {
  return (
    <div className="max-w-lg mx-auto text-center">
      <Label>{data.label}</Label>
      <h2 className="font-display text-3xl lg:text-5xl font-bold tracking-tighter mb-4">
        AI recommends. <span className="text-primary text-glow">You decide.</span>
      </h2>
      <p className="text-white/60 mb-8">{data.body}</p>
      <div className="flex flex-wrap items-center justify-center gap-3 pointer-events-auto">
        <Link to="/register">
          <Button variant="success" size="lg" data-testid="story-approve-btn">
            <CheckCircle2 size={18} /> Approve procurement
          </Button>
        </Link>
        <Link to="/register">
          <Button variant="secondary" size="lg" data-testid="story-negotiate-btn">
            <Gavel size={18} /> Negotiate further
          </Button>
        </Link>
        <Link to="/register">
          <Button variant="danger" size="lg" data-testid="story-reject-btn">
            Reject
          </Button>
        </Link>
      </div>
    </div>
  );
}

function CompleteContent({ data }) {
  return (
    <div className="max-w-2xl mx-auto text-center">
      <Label>{data.label}</Label>
      <h2 className="font-display text-3xl lg:text-5xl font-bold tracking-tighter mb-4">
        Procurement <span className="text-secondary text-glow">complete.</span>
      </h2>
      <p className="text-white/60 mb-7">{data.body}</p>
      <div className="glass rounded-2xl p-5 mb-8">
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-px bg-white/10 rounded-xl overflow-hidden border border-white/10">
          {data.summary.map((x) => (
            <div key={x.k} className="bg-[#0a0f1c] px-3 py-3">
              <div className="text-[10px] font-mono tracking-widest uppercase text-white/40">{x.k}</div>
              <div className="font-display text-base mt-1 whitespace-nowrap">{x.v}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-3 pointer-events-auto">
        <Link to="/register">
          <Button size="lg" data-testid="story-final-cta">
            Deploy your AI Buyer <ArrowRight size={18} />
          </Button>
        </Link>
        <Link to="/pricing">
          <Button size="lg" variant="secondary" data-testid="story-pricing">
            View pricing
          </Button>
        </Link>
      </div>
    </div>
  );
}

function Content({ kind, data, spMV, i }) {
  switch (kind) {
    case "enter":
      return <EnterContent data={data} />;
    case "request":
      return <RequestContent data={data} spMV={spMV} i={i} />;
    case "discovery":
      return <DiscoveryContent data={data} />;
    case "intel":
      return <IntelContent data={data} />;
    case "verify":
      return <VerifyContent data={data} />;
    case "negotiation":
      return <NegotiationContent data={data} spMV={spMV} />;
    case "warroom":
      return <WarRoomContent data={data} />;
    case "landed":
      return <LandedContent data={data} />;
    case "recommend":
      return <RecommendContent data={data} />;
    case "decision":
      return <DecisionContent data={data} />;
    default:
      return <CompleteContent data={data} />;
  }
}

const ALIGN = [
  "items-center justify-center px-6 sm:px-12 lg:px-48",
  "items-center justify-start px-6 sm:px-12 lg:pl-24 lg:pr-48",
  "items-center justify-end px-6 sm:px-12 lg:pl-24 lg:pr-48",
  "items-center justify-start px-6 sm:px-12 lg:pl-24 lg:pr-48",
  "items-center justify-end px-6 sm:px-12 lg:pl-24 lg:pr-48",
  "items-center justify-start px-6 sm:px-12 lg:pl-24 lg:pr-48",
  "items-center justify-center px-6 sm:px-12 lg:px-48",
  "items-center justify-end px-6 sm:px-12 lg:pl-24 lg:pr-48",
  "items-center justify-start px-6 sm:px-12 lg:pl-24 lg:pr-48",
  "items-center justify-center px-6 sm:px-12 lg:px-48",
  "items-center justify-center px-6 sm:px-12 lg:px-48",
];

function Layer({ i, data, spMV }) {
  const opacity = useTransform(spMV, [i - 0.5, i - 0.16, i + 0.16, i + 0.5], [0, 1, 1, 0]);
  const y = useTransform(spMV, [i - 0.5, i, i + 0.5], [40, 0, -40]);
  return (
    <motion.div
      style={{ opacity, y }}
      className={`absolute inset-0 flex ${ALIGN[i]} drop-shadow-[0_4px_26px_rgba(0,0,0,0.6)]`}
      data-testid={`story-scene-${i}`}
    >
      <Content kind={data.kind} data={data} spMV={spMV} i={i} />
    </motion.div>
  );
}

export default function Overlays({ scroll }) {
  const spMV = useTransform(scroll, (v) => v * (SCENES - 1));
  return (
    <>
      {STORY.map((s, i) => (
        <Layer key={i} i={i} data={s} spMV={spMV} />
      ))}
    </>
  );
}

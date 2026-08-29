import React from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, AlertTriangle, ArrowRight, ShieldCheck } from "lucide-react";
import { STORY } from "./story";
import { Button, SectionLabel } from "../../components/ui";

function StaticBody({ s }) {
  switch (s.kind) {
    case "request":
      return (
        <>
          <div className="glass rounded-2xl p-5 font-mono text-sm text-white/80 border border-primary/20">
            <span className="text-primary/70">buyer@negobuy ~ $ </span>
            {s.request}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {s.shards.map((x) => (
              <span key={x} className="text-[11px] font-mono px-3 py-1.5 rounded-lg border border-primary/25 bg-primary/5 text-primary/90">
                {x}
              </span>
            ))}
          </div>
        </>
      );
    case "discovery":
      return (
        <div className="glass rounded-2xl p-5 space-y-1.5">
          {s.funnel.map((f) => (
            <div key={f.k} className="flex justify-between text-sm">
              <span className="text-white/55">{f.k}</span>
              <span className="font-mono text-white/85">{f.v}</span>
            </div>
          ))}
        </div>
      );
    case "intel":
    case "recommend":
      return (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-px bg-white/10 rounded-xl overflow-hidden border border-white/10">
          {s.stats.map((x) => (
            <div key={x.k} className="bg-[#0a0f1c] px-4 py-3">
              <div className="text-[10px] font-mono uppercase tracking-widest text-white/40">{x.k}</div>
              <div className="font-display text-lg mt-1">{x.v}</div>
            </div>
          ))}
        </div>
      );
    case "verify":
      return (
        <div className="glass rounded-2xl p-5 space-y-2.5">
          {s.checks.map((c) => (
            <div key={c.k} className="flex justify-between text-sm">
              <span className="text-white/75">{c.k}</span>
              {c.s === "verified" ? (
                <span className="inline-flex items-center gap-1.5 text-secondary text-xs font-mono uppercase"><CheckCircle2 size={14} /> Verified</span>
              ) : (
                <span className="inline-flex items-center gap-1.5 text-yellow-300 text-xs font-mono uppercase"><AlertTriangle size={14} /> Review</span>
              )}
            </div>
          ))}
        </div>
      );
    case "negotiation":
      return (
        <div className="glass rounded-2xl p-5">
          <div className="flex justify-between items-center mb-3">
            <span className="text-[11px] font-mono uppercase tracking-widest text-white/40">Price / unit</span>
            <span className="font-display text-3xl text-primary">₹900 → ₹875</span>
          </div>
          <div className="grid grid-cols-3 gap-3">
            {s.terms.map((t) => (
              <div key={t.k}><div className="text-[9px] font-mono uppercase text-white/40">{t.k}</div><div className="text-sm">{t.v}</div></div>
            ))}
          </div>
        </div>
      );
    case "warroom":
      return (
        <div className="grid grid-cols-2 gap-3">
          {s.vendors.map((v) => (
            <div key={v.k} className={`rounded-xl p-4 border ${v.lead ? "border-secondary/40 bg-secondary/10" : "border-white/10 bg-[#0a0f1c]"}`}>
              <div className="text-sm text-white/75">{v.k}</div>
              <div className={`font-display text-2xl mt-1 ${v.lead ? "text-secondary" : "text-white/90"}`}>{v.v}</div>
            </div>
          ))}
        </div>
      );
    case "landed":
      return (
        <div className="glass rounded-2xl p-5 space-y-2">
          {s.cost.map((c) => (
            <div key={c.k} className="flex justify-between text-sm">
              <span className="text-white/60">{c.k}{c.assumption && <span className="ml-2 text-[9px] text-yellow-300">(assumption)</span>}</span>
              <span className="font-mono text-white/85">{c.v}</span>
            </div>
          ))}
          <div className="border-t border-white/10 pt-3 flex justify-between">
            <span className="text-[11px] font-mono uppercase tracking-widest text-white/50">Total landed cost</span>
            <span className="font-display text-2xl text-primary">{s.total}</span>
          </div>
        </div>
      );
    case "decision":
      return (
        <div className="flex flex-wrap gap-3">
          <Link to="/register"><Button variant="success">Approve procurement</Button></Link>
          <Link to="/register"><Button variant="secondary">Negotiate further</Button></Link>
          <Link to="/register"><Button variant="danger">Reject</Button></Link>
        </div>
      );
    case "complete":
      return (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-px bg-white/10 rounded-xl overflow-hidden border border-white/10 mb-6">
            {s.summary.map((x) => (
              <div key={x.k} className="bg-[#0a0f1c] px-4 py-3">
                <div className="text-[10px] font-mono uppercase tracking-widest text-white/40">{x.k}</div>
                <div className="font-display text-base mt-1">{x.v}</div>
              </div>
            ))}
          </div>
          <Link to="/register"><Button size="lg">Deploy your AI Buyer <ArrowRight size={18} /></Button></Link>
        </>
      );
    default:
      return null;
  }
}

export default function ReducedStory() {
  return (
    <div className="bg-void text-white max-w-3xl mx-auto px-6 py-24 space-y-24">
      <div className="text-center">
        <div className="inline-flex items-center gap-2 text-[11px] font-mono tracking-widest uppercase text-primary/90 border border-primary/25 rounded-full px-4 py-1.5 mb-8 bg-primary/5">
          <ShieldCheck size={13} /> AI Procurement Operator · Illustrative walkthrough
        </div>
        <h1 className="font-display text-4xl sm:text-5xl font-bold tracking-tighter">
          Your AI Buyer for the <span className="text-primary text-glow">real world.</span>
        </h1>
        <p className="mt-5 text-white/65">{STORY[0].body}</p>
      </div>
      {STORY.slice(1).map((s, i) => (
        <section key={i} data-testid={`reduced-scene-${i + 1}`}>
          <SectionLabel>{s.label}</SectionLabel>
          <h2 className="font-display text-2xl sm:text-3xl font-bold tracking-tight mb-3">{s.title}</h2>
          <p className="text-white/60 mb-5">{s.body}</p>
          <StaticBody s={s} />
        </section>
      ))}
    </div>
  );
}

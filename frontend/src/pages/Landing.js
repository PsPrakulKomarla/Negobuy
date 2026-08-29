import React from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowRight,
  Search,
  ShieldCheck,
  Phone,
  Scale,
  CheckCircle2,
  Brain,
  Radio,
  Lock,
  Layers,
} from "lucide-react";
import BuyerScene from "../three/BuyerScene";
import { Button, SectionLabel } from "../components/ui";

const PIPELINE = ["DEFINE", "DISCOVER", "VERIFY", "NEGOTIATE", "COMPARE", "APPROVE"];

const STEPS = [
  { icon: Brain, title: "Define", desc: "Describe your requirement in plain language. The AI structures a full procurement spec." },
  { icon: Search, title: "Discover", desc: "Real web discovery finds and deduplicates candidate suppliers across the market." },
  { icon: ShieldCheck, title: "Verify", desc: "Every candidate is scored on evidence, credibility and fit — never fabricated." },
  { icon: Phone, title: "Negotiate", desc: "Natural voice + text negotiation, always inside your authority limits." },
  { icon: Scale, title: "Compare", desc: "True landed-cost comparison with a reasoned recommendation — not just cheapest." },
  { icon: CheckCircle2, title: "Approve", desc: "Nothing material happens without your explicit human approval." },
];

function Nav() {
  return (
    <header className="fixed top-0 inset-x-0 z-50">
      <div className="max-w-7xl mx-auto px-5 sm:px-8 h-20 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-primary/15 border border-primary/40 flex items-center justify-center glow-primary">
            <span className="font-display font-black text-primary text-lg">N</span>
          </div>
          <span className="font-display font-bold text-lg tracking-tight">NegoBuy</span>
        </Link>
        <nav className="hidden md:flex items-center gap-8 text-sm text-white/60">
          <a href="#how" className="hover:text-white transition-colors">How it works</a>
          <a href="#voice" className="hover:text-white transition-colors">Voice</a>
          <a href="#trust" className="hover:text-white transition-colors">Trust</a>
          <Link to="/pricing" className="hover:text-white transition-colors">Pricing</Link>
        </nav>
        <div className="flex items-center gap-3">
          <Link to="/login">
            <Button variant="ghost" size="sm" data-testid="nav-login">Sign in</Button>
          </Link>
          <Link to="/register">
            <Button size="sm" data-testid="nav-get-started">Get started</Button>
          </Link>
        </div>
      </div>
    </header>
  );
}

export default function Landing() {
  return (
    <div className="bg-void text-white relative">
      <Nav />

      {/* HERO */}
      <section className="relative min-h-screen flex items-center overflow-hidden">
        <BuyerScene className="absolute inset-0 w-full h-full" />
        <div className="absolute inset-0 bg-gradient-to-b from-void/30 via-transparent to-void pointer-events-none" />
        <div className="absolute inset-0 bg-gradient-to-r from-void via-void/70 to-void/10 pointer-events-none" />

        <div className="relative z-10 max-w-7xl mx-auto px-5 sm:px-8 w-full pt-20">
          <div className="max-w-2xl">
            <div
              className="inline-flex items-center gap-2 text-xs font-mono tracking-widest uppercase text-primary/90 border border-primary/25 rounded-full px-4 py-1.5 mb-8 bg-primary/5"
            >
              <Radio size={13} /> AI Procurement Operator
            </div>

            <h1
              className="font-display text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tighter leading-[1.05]"
            >
              Your AI Buyer for the{" "}
              <span className="text-primary text-glow">real world.</span>
            </h1>

            <p
              className="mt-6 text-lg text-white/65 leading-relaxed max-w-xl"
            >
              From requirement to negotiation to the best purchasing decision —
              NegoBuy discovers suppliers, verifies them, negotiates within your
              limits, and hands you a decision you can approve.
            </p>

            <div
              className="mt-10 flex flex-wrap items-center gap-4"
            >
              <Link to="/register">
                <Button size="lg" data-testid="hero-cta">
                  Deploy your AI Buyer <ArrowRight size={18} />
                </Button>
              </Link>
              <Link to="/pricing">
                <Button size="lg" variant="secondary">View pricing</Button>
              </Link>
            </div>

            <div
              className="mt-14 flex flex-wrap items-center gap-x-2 gap-y-3"
            >
              {PIPELINE.map((p, i) => (
                <React.Fragment key={p}>
                  <span className="text-xs font-mono tracking-widest text-white/50">
                    {p}
                  </span>
                  {i < PIPELINE.length - 1 && (
                    <ArrowRight size={12} className="text-primary/50" />
                  )}
                </React.Fragment>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* PROBLEM */}
      <section className="relative py-28 max-w-7xl mx-auto px-5 sm:px-8">
        <SectionLabel>The problem</SectionLabel>
        <div className="grid lg:grid-cols-2 gap-12 items-end">
          <h2 className="font-display text-3xl lg:text-4xl font-bold tracking-tight leading-tight">
            Procurement is slow, manual, and impossible to compare fairly.
          </h2>
          <p className="text-white/60 text-lg leading-relaxed">
            Buyers spend weeks chasing suppliers, collecting inconsistent quotes,
            and guessing at true cost. NegoBuy operates the entire journey as a
            single AI employee — with evidence, memory, and hard authority limits.
          </p>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section id="how" className="relative py-24 max-w-7xl mx-auto px-5 sm:px-8">
        <SectionLabel>How it works</SectionLabel>
        <h2 className="font-display text-3xl lg:text-4xl font-bold tracking-tight mb-14 max-w-2xl">
          A full procurement pipeline, operated end-to-end.
        </h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {STEPS.map((s, i) => (
            <motion.div
              key={s.title}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.5, delay: i * 0.06 }}
              className="card-solid rounded-2xl p-7 hover:border-primary/30 transition-colors duration-300 group"
            >
              <div className="w-11 h-11 rounded-xl bg-primary/10 border border-primary/25 flex items-center justify-center mb-5 group-hover:bg-primary/20 transition-colors">
                <s.icon size={20} className="text-primary" strokeWidth={1.7} />
              </div>
              <div className="text-[11px] font-mono text-white/30 mb-1">
                0{i + 1}
              </div>
              <h3 className="font-display text-xl font-semibold mb-2">{s.title}</h3>
              <p className="text-white/55 text-sm leading-relaxed">{s.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* VOICE */}
      <section id="voice" className="relative py-24 max-w-7xl mx-auto px-5 sm:px-8">
        <div className="glass rounded-3xl p-8 lg:p-14 grid lg:grid-cols-2 gap-12 items-center overflow-hidden relative">
          <div className="absolute -right-20 -top-20 w-80 h-80 bg-primary/10 blur-[100px] rounded-full" />
          <div className="relative z-10">
            <SectionLabel>Natural voice negotiation</SectionLabel>
            <h2 className="font-display text-3xl lg:text-4xl font-bold tracking-tight mb-5">
              Not an IVR. A negotiator.
            </h2>
            <p className="text-white/60 leading-relaxed mb-6">
              No “press 1 for sales.” NegoBuy holds a natural, two-way
              conversation — it listens, handles interruptions, understands
              objections, and negotiates pricing, delivery and warranty inside
              the limits you set.
            </p>
            <ul className="space-y-3">
              {[
                "Realtime speech, natural pauses and tone",
                "Records every commitment and offer",
                "Never exceeds your authorized price",
              ].map((t) => (
                <li key={t} className="flex items-center gap-3 text-sm text-white/70">
                  <CheckCircle2 size={16} className="text-secondary shrink-0" />
                  {t}
                </li>
              ))}
            </ul>
          </div>
          <div className="relative z-10 space-y-3">
            {[
              { who: "AI", text: "Hi, I'm calling on behalf of a buyer looking for 500 ergonomic office chairs. What pricing and delivery can you offer?" },
              { who: "Vendor", text: "We can supply them — around ₹900 each." },
              { who: "AI", text: "Understood. For a confirmed 500 units, is there room to improve that price?" },
              { who: "Vendor", text: "Maybe. How quickly do you need them?" },
              { who: "AI", text: "Delivered to Bangalore within ten days. Does that timeline work?" },
            ].map((m, i) => (
              <div
                key={i}
                className={`max-w-[85%] px-4 py-3 rounded-2xl text-sm ${
                  m.who === "AI"
                    ? "bg-primary/12 border border-primary/25 ml-auto text-white"
                    : "bg-white/5 border border-white/10 text-white/75"
                }`}
              >
                <span className="block text-[10px] font-mono tracking-widest uppercase mb-1 opacity-50">
                  {m.who === "AI" ? "NegoBuy AI" : "Vendor"}
                </span>
                {m.text}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* TRUST */}
      <section id="trust" className="relative py-24 max-w-7xl mx-auto px-5 sm:px-8">
        <SectionLabel>Security & trust</SectionLabel>
        <div className="grid md:grid-cols-3 gap-5">
          {[
            { icon: Lock, t: "Controlled autonomy", d: "Hard authority limits. The AI can negotiate but never approve a purchase alone." },
            { icon: ShieldCheck, t: "No fabricated data", d: "Vendors, prices and evidence are real or clearly marked unavailable — never invented." },
            { icon: Layers, t: "Full audit trail", d: "Every agent action is timestamped, traceable and explained with evidence." },
          ].map((c) => (
            <div key={c.t} className="card-solid rounded-2xl p-7">
              <c.icon size={22} className="text-primary mb-4" strokeWidth={1.7} />
              <h3 className="font-display text-lg font-semibold mb-2">{c.t}</h3>
              <p className="text-white/55 text-sm leading-relaxed">{c.d}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="relative py-28 max-w-5xl mx-auto px-5 sm:px-8 text-center">
        <div className="glass rounded-3xl p-12 lg:p-20 relative overflow-hidden">
          <div className="absolute inset-0 bg-primary/5" />
          <div className="relative z-10">
            <h2 className="font-display text-3xl lg:text-5xl font-bold tracking-tighter mb-6">
              Give your next purchase an operator.
            </h2>
            <p className="text-white/60 text-lg mb-10 max-w-xl mx-auto">
              Create your first procurement mission in minutes.
            </p>
            <Link to="/register">
              <Button size="lg" data-testid="footer-cta">
                Start now <ArrowRight size={18} />
              </Button>
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t hairline py-10 text-center text-white/30 text-sm">
        NegoBuy · Your AI Buyer for the real world.
      </footer>
    </div>
  );
}

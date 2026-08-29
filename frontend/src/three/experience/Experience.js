import React, { useRef, useState, useEffect, Suspense, Component } from "react";
import { Link } from "react-router-dom";
import { Canvas } from "@react-three/fiber";
import { useScroll, useTransform, useMotionValueEvent } from "framer-motion";
import { SkipForward } from "lucide-react";
import World from "./World";
import CameraRig from "./CameraRig";
import Overlays from "./Overlays";
import ReducedStory from "./ReducedStory";
import { SCENES } from "./helpers";
import { STORY } from "./story";

function usePrefersReducedMotion() {
  const [r, setR] = useState(false);
  useEffect(() => {
    const m = window.matchMedia("(prefers-reduced-motion: reduce)");
    setR(m.matches);
    const h = (e) => setR(e.matches);
    m.addEventListener("change", h);
    return () => m.removeEventListener("change", h);
  }, []);
  return r;
}

class WebGLBoundary extends Component {
  constructor(p) {
    super(p);
    this.state = { failed: false };
  }
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {}
  render() {
    if (this.state.failed) return this.props.fallback;
    return this.props.children;
  }
}

function TopNav() {
  return (
    <header className="fixed top-0 inset-x-0 z-30 pointer-events-none">
      <div className="max-w-[1600px] mx-auto px-5 sm:px-8 h-20 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-3 pointer-events-auto" data-testid="brand-home">
          <div className="w-9 h-9 rounded-xl bg-primary/15 border border-primary/40 flex items-center justify-center glow-primary">
            <span className="font-display font-black text-primary text-lg">N</span>
          </div>
          <span className="font-display font-bold text-lg tracking-tight">NegoBuy</span>
        </Link>
        <div className="flex items-center gap-2 sm:gap-4 pointer-events-auto">
          <Link to="/pricing" className="hidden sm:inline text-sm text-white/60 hover:text-white transition-colors">
            Pricing
          </Link>
          <Link to="/login" className="text-sm text-white/70 hover:text-white transition-colors" data-testid="nav-login">
            Sign in
          </Link>
          <Link
            to="/register"
            className="inline-flex items-center gap-1.5 text-xs font-mono tracking-widest uppercase text-white/80 hover:text-white border border-white/15 hover:border-primary/40 rounded-full px-3.5 py-2 transition-colors"
            data-testid="skip-intro"
          >
            <SkipForward size={13} /> Skip intro
          </Link>
        </div>
      </div>
    </header>
  );
}

function ProgressRail({ spMV }) {
  const [active, setActive] = useState(0);
  useMotionValueEvent(spMV, "change", (v) => {
    const idx = Math.max(0, Math.min(SCENES - 1, Math.round(v)));
    setActive((a) => (a === idx ? a : idx));
  });
  return (
    <div className="fixed right-5 sm:right-8 top-1/2 -translate-y-1/2 z-30 hidden md:flex flex-col items-end gap-3 pointer-events-none" data-testid="progress-rail">
      <div className="text-[10px] font-mono tracking-[0.25em] uppercase text-primary/80 mb-1" data-testid="progress-rail-index">
        {String(active).padStart(2, "0")} / {String(SCENES - 1).padStart(2, "0")}
      </div>
      {STORY.map((s, i) => (
        <div key={i} className="flex items-center gap-2.5" data-testid={`progress-rail-item-${i}`}>
          <span
            className={`text-[10px] font-mono tracking-wider uppercase transition-colors duration-300 ${
              i === active ? "text-white/80" : "text-white/0"
            }`}
          >
            {s.label.split("·").pop().trim()}
          </span>
          <span
            className={`h-px transition-all duration-300 ${
              i === active ? "w-6 bg-primary" : "w-3 bg-white/20"
            }`}
          />
        </div>
      ))}
    </div>
  );
}

export default function Experience() {
  const ref = useRef(null);
  const reduced = usePrefersReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end end"] });
  const spMV = useTransform(scrollYProgress, (v) => v * (SCENES - 1));

  if (reduced) return <ReducedStory />;

  return (
    <div ref={ref} style={{ height: `${SCENES * 100}vh`, position: "relative" }} className="bg-void" data-testid="experience-root">
      <WebGLBoundary fallback={<div className="fixed inset-0 overflow-auto"><ReducedStory /></div>}>
        <div className="fixed inset-0 z-0 pointer-events-none">
          <Canvas
            dpr={[1, 1.75]}
            gl={{ antialias: true, alpha: false, powerPreference: "high-performance" }}
            camera={{ position: [0.6, 5.2, 23], fov: 42 }}
          >
            <Suspense fallback={null}>
              <World scroll={scrollYProgress} />
              <CameraRig scroll={scrollYProgress} />
            </Suspense>
          </Canvas>
        </div>
        <div className="fixed inset-0 z-20 pointer-events-none">
          <Overlays scroll={scrollYProgress} />
        </div>
        <TopNav />
        <ProgressRail spMV={spMV} />
      </WebGLBoundary>
    </div>
  );
}

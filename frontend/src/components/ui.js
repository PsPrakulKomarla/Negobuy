import React from "react";
import { motion } from "framer-motion";

export function Button({
  children,
  variant = "primary",
  size = "md",
  className = "",
  ...props
}) {
  const base =
    "inline-flex items-center justify-center gap-2 font-medium rounded-full transition-[transform,background-color,border-color,box-shadow,color] duration-200 disabled:opacity-40 disabled:cursor-not-allowed select-none";
  const sizes = {
    sm: "text-xs px-4 py-2",
    md: "text-sm px-5 py-2.5",
    lg: "text-base px-7 py-3.5",
  };
  const variants = {
    primary:
      "bg-primary text-black hover:bg-cyan-300 hover:-translate-y-0.5 glow-primary",
    secondary:
      "bg-white/5 text-white border border-white/12 hover:bg-white/10 hover:border-white/25 hover:-translate-y-0.5",
    ghost: "bg-transparent text-white/70 hover:text-white hover:bg-white/5",
    danger:
      "bg-accent/15 text-accent border border-accent/30 hover:bg-accent/25 hover:-translate-y-0.5",
    success:
      "bg-secondary/15 text-secondary border border-secondary/30 hover:bg-secondary/25 hover:-translate-y-0.5",
  };
  return (
    <button
      className={`${base} ${sizes[size]} ${variants[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

export function Card({ children, className = "", glass = false, ...props }) {
  return (
    <div
      className={`${glass ? "glass" : "card-solid"} rounded-2xl ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export function Input({ label, className = "", ...props }) {
  return (
    <label className="block">
      {label && (
        <span className="block mb-2 text-xs tracking-[0.2em] uppercase text-white/50">
          {label}
        </span>
      )}
      <input
        className={`w-full bg-black/40 border border-white/12 rounded-xl px-4 py-3 text-white placeholder-white/30 outline-none transition-[border-color,box-shadow] duration-200 focus:border-primary/60 focus:shadow-[0_0_0_3px_rgba(0,229,255,0.12)] ${className}`}
        {...props}
      />
    </label>
  );
}

export function Textarea({ label, className = "", ...props }) {
  return (
    <label className="block">
      {label && (
        <span className="block mb-2 text-xs tracking-[0.2em] uppercase text-white/50">
          {label}
        </span>
      )}
      <textarea
        className={`w-full bg-black/40 border border-white/12 rounded-xl px-4 py-3 text-white placeholder-white/30 outline-none transition-[border-color,box-shadow] duration-200 focus:border-primary/60 focus:shadow-[0_0_0_3px_rgba(0,229,255,0.12)] resize-none ${className}`}
        {...props}
      />
    </label>
  );
}

const STATUS_COLORS = {
  DRAFT: "text-white/50 border-white/15 bg-white/5",
  REQUIREMENT_REVIEW: "text-primary border-primary/30 bg-primary/10",
  DISCOVERING: "text-primary border-primary/30 bg-primary/10",
  VERIFYING: "text-primary border-primary/30 bg-primary/10",
  CONTACTING: "text-primary border-primary/30 bg-primary/10",
  NEGOTIATING: "text-yellow-300 border-yellow-400/30 bg-yellow-400/10",
  COMPARING: "text-yellow-300 border-yellow-400/30 bg-yellow-400/10",
  AWAITING_APPROVAL: "text-accent border-accent/30 bg-accent/10",
  APPROVED: "text-secondary border-secondary/30 bg-secondary/10",
  COMPLETED: "text-secondary border-secondary/30 bg-secondary/10",
  REJECTED: "text-accent border-accent/30 bg-accent/10",
  CANCELLED: "text-white/40 border-white/15 bg-white/5",
  VERIFIED: "text-secondary border-secondary/30 bg-secondary/10",
  UNVERIFIED: "text-white/50 border-white/15 bg-white/5",
  UNDER_REVIEW: "text-yellow-300 border-yellow-400/30 bg-yellow-400/10",
};

export function StatusPill({ status, className = "" }) {
  const cls = STATUS_COLORS[status] || STATUS_COLORS.DRAFT;
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-[10px] font-mono tracking-wider uppercase px-3 py-1 rounded-full border ${cls} ${className}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulseGlow" />
      {(status || "").replace(/_/g, " ")}
    </span>
  );
}

export function Badge({ children, className = "", ...rest }) {
  return (
    <span
      className={`inline-flex items-center text-[10px] font-mono tracking-wider uppercase px-2.5 py-1 rounded-md border border-white/12 bg-white/5 text-white/60 ${className}`}
      {...rest}
    >
      {children}
    </span>
  );
}

export function Spinner({ className = "" }) {
  return (
    <span
      className={`inline-block w-4 h-4 border-2 border-white/20 border-t-primary rounded-full animate-spin ${className}`}
    />
  );
}

export function SectionLabel({ children }) {
  return (
    <div className="flex items-center gap-3 mb-4">
      <span className="w-6 h-px bg-primary/60" />
      <span className="text-xs tracking-[0.3em] uppercase text-primary/80 font-mono">
        {children}
      </span>
    </div>
  );
}

export function AnimatedNumber({ value, prefix = "", suffix = "", decimals = 0 }) {
  const [display, setDisplay] = React.useState(0);
  React.useEffect(() => {
    let raf;
    const start = performance.now();
    const from = display;
    const to = Number(value) || 0;
    const dur = 900;
    const tick = (now) => {
      const p = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      setDisplay(from + (to - from) * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line
  }, [value]);
  return (
    <span>
      {prefix}
      {display.toLocaleString(undefined, {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })}
      {suffix}
    </span>
  );
}

export const fadeUp = {
  initial: { opacity: 0, y: 18 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.6, ease: [0.16, 1, 0.3, 1] },
};

export { motion };

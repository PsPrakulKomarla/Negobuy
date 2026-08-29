import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Target,
  TrendingUp,
  Building2,
  Phone,
  Clock,
  Plus,
  ArrowRight,
  Activity,
} from "lucide-react";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import {
  Button,
  Card,
  StatusPill,
  AnimatedNumber,
  Spinner,
  SectionLabel,
} from "../components/ui";

const STAT_CARDS = [
  { key: "active_missions", label: "Active Missions", icon: Target, color: "text-primary" },
  { key: "estimated_savings", label: "Est. Savings", icon: TrendingUp, color: "text-secondary", prefix: "₹" },
  { key: "vendors_discovered", label: "Vendors Discovered", icon: Building2, color: "text-white" },
  { key: "negotiations_active", label: "Negotiations", icon: Phone, color: "text-yellow-300" },
  { key: "pending_approvals", label: "Pending Approvals", icon: Clock, color: "text-accent" },
  { key: "completed_missions", label: "Completed", icon: Activity, color: "text-secondary" },
];

export default function Dashboard() {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get("/dashboard/stats").then((r) => r.data),
      api.get("/dashboard/analytics").then((r) => r.data).catch(() => null),
    ])
      .then(([s, a]) => {
        setStats(s);
        setAnalytics(a);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading)
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Spinner className="w-8 h-8" />
      </div>
    );

  return (
    <div className="p-6 lg:p-10 max-w-7xl mx-auto">
      <div className="flex flex-wrap items-end justify-between gap-4 mb-10">
        <div>
          <div className="text-xs tracking-[0.3em] uppercase text-primary/80 font-mono mb-2">
            Command Center
          </div>
          <h1 className="font-display text-3xl lg:text-4xl font-bold tracking-tight">
            Welcome, {user?.name?.split(" ")[0]}
          </h1>
          <p className="text-white/50 mt-2">
            {user?.organization_name} · Your AI Buyer is standing by.
          </p>
        </div>
        <Link to="/missions/new">
          <Button size="lg" data-testid="new-mission-btn">
            <Plus size={18} /> New Mission
          </Button>
        </Link>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-10">
        {STAT_CARDS.map((c, i) => (
          <motion.div
            key={c.key}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: i * 0.05 }}
          >
            <Card className="p-6 h-full hover:border-white/15 transition-colors" data-testid={`stat-${c.key}`}>
              <div className="flex items-center justify-between mb-4">
                <c.icon size={20} className={c.color} strokeWidth={1.7} />
              </div>
              <div className={`font-display text-3xl font-bold ${c.color}`}>
                <AnimatedNumber value={stats?.[c.key] || 0} prefix={c.prefix || ""} />
              </div>
              <div className="text-xs text-white/45 mt-1 tracking-wide">{c.label}</div>
            </Card>
          </motion.div>
        ))}
      </div>

      {/* Analytics */}
      {analytics && (analytics.status_breakdown?.length > 0 || analytics.savings_over_time?.length > 0) && (
        <div className="mb-10">
          <SectionLabel>Procurement analytics</SectionLabel>
          <div className="grid lg:grid-cols-2 gap-4">
            <Card className="p-6" data-testid="analytics-savings">
              <div className="flex items-center justify-between mb-4">
                <div className="text-sm text-white/60">Savings vs spend</div>
                <div className="text-xs font-mono text-secondary">
                  ₹<AnimatedNumber value={analytics.total_savings || 0} /> saved
                </div>
              </div>
              {analytics.savings_over_time?.length ? (
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={analytics.savings_over_time}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                    <XAxis dataKey="month" stroke="rgba(255,255,255,0.4)" fontSize={11} />
                    <YAxis stroke="rgba(255,255,255,0.4)" fontSize={11} />
                    <Tooltip contentStyle={{ background: "#0a0e14", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, color: "#fff" }} />
                    <Line type="monotone" dataKey="spend" stroke="#00e5ff" strokeWidth={2} dot={false} name="Spend" />
                    <Line type="monotone" dataKey="savings" stroke="#0f9d6a" strokeWidth={2} dot={false} name="Savings" />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-white/30 text-sm text-center py-16">Approve a purchase to see savings accrue here.</p>
              )}
            </Card>

            <Card className="p-6" data-testid="analytics-status">
              <div className="text-sm text-white/60 mb-4">Missions by stage</div>
              {analytics.status_breakdown?.length ? (
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={analytics.status_breakdown}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                    <XAxis dataKey="status" stroke="rgba(255,255,255,0.4)" fontSize={9} interval={0} angle={-20} textAnchor="end" height={60} />
                    <YAxis allowDecimals={false} stroke="rgba(255,255,255,0.4)" fontSize={11} />
                    <Tooltip contentStyle={{ background: "#0a0e14", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, color: "#fff" }} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
                    <Bar dataKey="count" fill="#00e5ff" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-white/30 text-sm text-center py-16">No missions yet.</p>
              )}
            </Card>
          </div>
          {analytics.top_vendors?.length > 0 && (
            <Card className="p-6 mt-4" data-testid="analytics-vendors">
              <div className="text-sm text-white/60 mb-4">Remembered suppliers ({analytics.vendors_remembered})</div>
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {analytics.top_vendors.map((v, i) => (
                  <div key={i} className="flex items-center justify-between rounded-xl border border-white/8 bg-white/5 px-4 py-3">
                    <div className="min-w-0">
                      <div className="text-sm truncate">{v.name}</div>
                      <div className="text-[11px] text-white/40">{v.negotiations} negotiation(s)</div>
                    </div>
                    {v.best_price != null && <div className="text-xs font-mono text-secondary shrink-0">best {v.best_price}</div>}
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}

      <div className="grid lg:grid-cols-5 gap-6">
        {/* Missions */}
        <div className="lg:col-span-3">
          <SectionLabel>Recent missions</SectionLabel>
          {stats?.missions?.length ? (
            <div className="space-y-3">
              {stats.missions.map((m) => (
                <Link key={m.id} to={`/missions/${m.id}`} data-testid={`mission-card-${m.id}`}>
                  <Card className="p-5 flex items-center justify-between hover:border-primary/30 transition-colors group">
                    <div className="min-w-0">
                      <div className="font-medium truncate group-hover:text-primary transition-colors">
                        {m.title}
                      </div>
                      <div className="text-xs text-white/40 mt-1">
                        {m.quantity ? `${m.quantity} units · ` : ""}
                        {m.delivery_location || "—"}
                      </div>
                    </div>
                    <div className="flex items-center gap-4 shrink-0">
                      <StatusPill status={m.status} />
                      <ArrowRight
                        size={16}
                        className="text-white/30 group-hover:text-primary group-hover:translate-x-1 transition-[transform,color]"
                      />
                    </div>
                  </Card>
                </Link>
              ))}
            </div>
          ) : (
            <Card className="p-10 text-center">
              <Target size={28} className="text-white/20 mx-auto mb-4" />
              <p className="text-white/50 mb-6">No missions yet.</p>
              <Link to="/missions/new">
                <Button data-testid="empty-new-mission">
                  <Plus size={16} /> Create your first mission
                </Button>
              </Link>
            </Card>
          )}
        </div>

        {/* Activity feed */}
        <div className="lg:col-span-2">
          <SectionLabel>Live activity</SectionLabel>
          <Card glass className="p-5">
            {stats?.recent_activity?.length ? (
              <div className="space-y-4 max-h-[420px] overflow-y-auto pr-1">
                {stats.recent_activity.map((a) => (
                  <div key={a.id} className="flex gap-3">
                    <div className="flex flex-col items-center">
                      <span className="w-2 h-2 rounded-full bg-primary mt-1.5 animate-pulseGlow" />
                      <span className="flex-1 w-px bg-white/10 my-1" />
                    </div>
                    <div className="pb-1 min-w-0">
                      <div className="text-[11px] font-mono text-primary/70">
                        {a.agent}
                      </div>
                      <div className="text-sm text-white/85">{a.action}</div>
                      {a.result && (
                        <div className="text-xs text-white/40 mt-0.5">{a.result}</div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-white/40 text-sm text-center py-8">
                Activity from your AI Buyer will appear here.
              </p>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Target, ArrowRight, Search } from "lucide-react";
import api from "../lib/api";
import { Button, Card, StatusPill, Spinner, Input } from "../components/ui";

export default function Missions() {
  const [missions, setMissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");

  useEffect(() => {
    api
      .get("/missions")
      .then((r) => setMissions(r.data))
      .finally(() => setLoading(false));
  }, []);

  const filtered = missions.filter((m) =>
    (m.title || "").toLowerCase().includes(q.toLowerCase())
  );

  return (
    <div className="p-6 lg:p-10 max-w-6xl mx-auto">
      <div className="flex flex-wrap items-end justify-between gap-4 mb-8">
        <div>
          <div className="text-xs tracking-[0.3em] uppercase text-primary/80 font-mono mb-2">
            Procurement
          </div>
          <h1 className="font-display text-3xl lg:text-4xl font-bold tracking-tight">
            Missions
          </h1>
        </div>
        <Link to="/missions/new">
          <Button size="lg" data-testid="missions-new-btn">
            <Plus size={18} /> New Mission
          </Button>
        </Link>
      </div>

      <div className="relative mb-6 max-w-md">
        <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-white/30" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search missions…"
          data-testid="missions-search"
          className="w-full bg-black/40 border border-white/12 rounded-xl pl-11 pr-4 py-3 text-white placeholder-white/30 outline-none focus:border-primary/60 transition-colors"
        />
      </div>

      {loading ? (
        <div className="py-20 flex justify-center">
          <Spinner className="w-8 h-8" />
        </div>
      ) : filtered.length ? (
        <div className="space-y-3">
          {filtered.map((m) => (
            <Link key={m.id} to={`/missions/${m.id}`} data-testid={`mission-row-${m.id}`}>
              <Card className="p-5 flex items-center justify-between hover:border-primary/30 transition-colors group">
                <div className="min-w-0">
                  <div className="font-medium truncate group-hover:text-primary transition-colors">
                    {m.title}
                  </div>
                  <div className="text-xs text-white/40 mt-1 flex gap-3 flex-wrap">
                    <span>{m.category || "—"}</span>
                    {m.quantity && <span>· {m.quantity} units</span>}
                    {m.budget && (
                      <span>· {m.currency} {Number(m.budget).toLocaleString()}</span>
                    )}
                    {m.delivery_location && <span>· {m.delivery_location}</span>}
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
        <Card className="p-14 text-center">
          <Target size={28} className="text-white/20 mx-auto mb-4" />
          <p className="text-white/50 mb-6">No missions found.</p>
          <Link to="/missions/new">
            <Button data-testid="missions-empty-new">
              <Plus size={16} /> Create a mission
            </Button>
          </Link>
        </Card>
      )}
    </div>
  );
}

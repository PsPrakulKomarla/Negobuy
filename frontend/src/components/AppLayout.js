import React from "react";
import { NavLink, Outlet, useNavigate, Link } from "react-router-dom";
import {
  LayoutDashboard,
  CreditCard,
  LogOut,
  Send,
  Sparkles,
  ClipboardList,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";

const NAV = [
  { to: "/dashboard", label: "Command Center", icon: LayoutDashboard },
  { to: "/sourcing", label: "Auto-Sourcing", icon: Sparkles },
  { to: "/telegram", label: "Telegram AI", icon: Send },
  { to: "/orders", label: "Orders", icon: ClipboardList },
  { to: "/plans", label: "Plans", icon: CreditCard },
];

export default function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const initials = (user?.name || user?.email || "U")
    .split(" ")
    .map((s) => s[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="min-h-screen bg-void flex">
      {/* Sidebar */}
      <aside className="hidden lg:flex flex-col w-64 shrink-0 border-r hairline glass-strong sticky top-0 h-screen z-20">
        <Link to="/" className="flex items-center gap-3 px-6 h-20 border-b hairline">
          <div className="w-9 h-9 rounded-xl bg-primary/15 border border-primary/40 flex items-center justify-center glow-primary">
            <span className="font-display font-black text-primary text-lg">N</span>
          </div>
          <div>
            <div className="font-display font-bold tracking-tight leading-none">
              NegoBuy
            </div>
            <div className="text-[10px] text-white/40 font-mono tracking-widest">
              AI PROCUREMENT
            </div>
          </div>
        </Link>

        <nav className="flex-1 px-3 py-6 space-y-1">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/missions"}
              data-testid={`nav-${item.label.toLowerCase().replace(/\s/g, "-")}`}
              className={({ isActive }) =>
                `group flex items-center gap-3 px-4 py-3 rounded-xl text-sm transition-[background-color,color] duration-200 ${
                  isActive
                    ? "bg-primary/10 text-primary border border-primary/25"
                    : "text-white/55 hover:text-white hover:bg-white/5 border border-transparent"
                }`
              }
            >
              <item.icon size={18} strokeWidth={1.7} />
              <span className="font-medium">{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="p-3 border-t hairline">
          <div className="flex items-center gap-3 px-3 py-3 rounded-xl bg-white/5">
            <div className="w-9 h-9 rounded-full bg-primary/20 border border-primary/30 flex items-center justify-center text-xs font-bold text-primary shrink-0 overflow-hidden">
              {user?.avatar ? (
                <img src={user.avatar} alt="" className="w-full h-full object-cover" />
              ) : (
                initials
              )}
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium truncate">{user?.name}</div>
              <div className="text-[11px] text-white/40 truncate">
                {user?.organization_name}
              </div>
            </div>
            <button
              data-testid="logout-btn"
              onClick={() => logout().then(() => navigate("/"))}
              className="text-white/40 hover:text-accent transition-colors"
              title="Logout"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 min-w-0 flex flex-col">
        {/* Mobile top bar */}
        <header className="lg:hidden flex items-center justify-between h-16 px-5 border-b hairline glass-strong sticky top-0 z-20">
          <Link to="/dashboard" className="font-display font-bold">
            NegoBuy
          </Link>
          <button onClick={() => logout().then(() => navigate("/"))}>
            <LogOut size={18} className="text-white/50" />
          </button>
        </header>

        <main className="flex-1 relative z-10">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

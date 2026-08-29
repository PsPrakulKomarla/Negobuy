import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { UserPlus, Shield, Trash2, Mail, Copy, Check } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Button, Card, Spinner, SectionLabel, Badge, Input } from "../components/ui";

const ROLES = ["admin", "buyer", "viewer"];
const ROLE_COLOR = {
  owner: "text-secondary border-secondary/30 bg-secondary/10",
  admin: "text-primary border-primary/30 bg-primary/10",
  buyer: "text-white/70 border-white/15 bg-white/5",
  viewer: "text-white/50 border-white/12 bg-white/5",
};

export default function Team() {
  const { user } = useAuth();
  const [members, setMembers] = useState([]);
  const [invites, setInvites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("buyer");
  const [inviting, setInviting] = useState(false);
  const [copied, setCopied] = useState("");

  const canManage = ["owner", "admin"].includes(user?.role);

  const load = async () => {
    const [m, i] = await Promise.all([
      api.get("/team/members").then((r) => r.data),
      api.get("/team/invites").then((r) => r.data).catch(() => []),
    ]);
    setMembers(m);
    setInvites(i);
  };

  useEffect(() => {
    load().finally(() => setLoading(false));
  }, []);

  const invite = async (e) => {
    e.preventDefault();
    setInviting(true);
    try {
      const { data } = await api.post("/team/invite", { email, role });
      const sent = data?.email_result?.ok;
      toast.success(sent ? `Invitation emailed to ${email}` : `Invite created for ${email}`);
      if (!sent) {
        navigator.clipboard?.writeText(data.accept_link);
        toast.info("Invite link copied to clipboard (email not delivered — verify your SendGrid sender).");
      }
      setEmail("");
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setInviting(false);
    }
  };

  const changeRole = async (uid, newRole) => {
    try {
      await api.patch(`/team/members/${uid}`, { role: newRole });
      toast.success("Role updated");
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const removeMember = async (uid) => {
    try {
      await api.delete(`/team/members/${uid}`);
      toast.success("Member removed");
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const revoke = async (inviteId) => {
    await api.delete(`/team/invites/${inviteId}`);
    await load();
  };

  const copyLink = (token, id) => {
    const link = `${window.location.origin}/accept-invite?token=${token}`;
    navigator.clipboard?.writeText(link);
    setCopied(id);
    setTimeout(() => setCopied(""), 1500);
  };

  if (loading)
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Spinner className="w-8 h-8" />
      </div>
    );

  return (
    <div className="p-6 lg:p-10 max-w-5xl mx-auto">
      <div className="mb-8">
        <div className="text-xs tracking-[0.3em] uppercase text-primary/80 font-mono mb-2">Organization</div>
        <h1 className="font-display text-3xl lg:text-4xl font-bold tracking-tight">Team & roles</h1>
        <p className="text-white/50 mt-2">{user?.organization_name} · manage who can operate your AI Buyer.</p>
      </div>

      {canManage && (
        <Card className="p-6 mb-8" data-testid="invite-card">
          <SectionLabel>Invite a teammate</SectionLabel>
          <form onSubmit={invite} className="flex flex-col sm:flex-row gap-3 sm:items-end">
            <div className="flex-1">
              <Input
                label="Email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="teammate@company.com"
                data-testid="invite-email"
                required
              />
            </div>
            <div>
              <span className="block mb-2 text-xs tracking-[0.2em] uppercase text-white/50">Role</span>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                data-testid="invite-role"
                className="bg-black/40 border border-white/12 rounded-xl px-4 py-3 text-white outline-none focus:border-primary/60 h-[50px]"
              >
                {ROLES.map((r) => (
                  <option key={r} value={r} className="bg-void">
                    {r}
                  </option>
                ))}
              </select>
            </div>
            <Button type="submit" size="lg" disabled={inviting} data-testid="invite-submit">
              {inviting ? <Spinner /> : <UserPlus size={18} />} Send invite
            </Button>
          </form>
        </Card>
      )}

      <SectionLabel>Members ({members.length})</SectionLabel>
      <div className="space-y-3 mb-10">
        {members.map((m, i) => (
          <motion.div key={m.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
            <Card className="p-4 flex items-center gap-4" data-testid={`member-${m.id}`}>
              <div className="w-10 h-10 rounded-full bg-primary/15 border border-primary/30 flex items-center justify-center text-sm font-bold text-primary shrink-0 overflow-hidden">
                {m.avatar ? <img src={m.avatar} alt="" className="w-full h-full object-cover" /> : (m.name || m.email)[0]?.toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <div className="font-medium truncate">
                  {m.name} {m.id === user?.id && <span className="text-white/30 text-xs">(you)</span>}
                </div>
                <div className="text-xs text-white/40 truncate">{m.email}</div>
              </div>
              <span className={`inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider px-3 py-1 rounded-full border ${ROLE_COLOR[m.role] || ROLE_COLOR.viewer}`}>
                <Shield size={10} /> {m.role}
              </span>
              {canManage && m.role !== "owner" && m.id !== user?.id && (
                <div className="flex items-center gap-2">
                  <select
                    value={m.role}
                    onChange={(e) => changeRole(m.id, e.target.value)}
                    data-testid={`role-select-${m.id}`}
                    className="bg-black/40 border border-white/12 rounded-lg px-2 py-1.5 text-xs text-white outline-none focus:border-primary/60"
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r} className="bg-void">
                        {r}
                      </option>
                    ))}
                  </select>
                  <button onClick={() => removeMember(m.id)} className="text-white/30 hover:text-accent transition-colors" data-testid={`remove-${m.id}`}>
                    <Trash2 size={15} />
                  </button>
                </div>
              )}
            </Card>
          </motion.div>
        ))}
      </div>

      {invites.length > 0 && (
        <>
          <SectionLabel>Pending invites ({invites.length})</SectionLabel>
          <div className="space-y-3">
            {invites.map((inv) => (
              <Card key={inv.id} className="p-4 flex items-center gap-3" data-testid={`invite-${inv.id}`}>
                <Mail size={16} className="text-white/40 shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm truncate">{inv.email}</div>
                  <div className="text-[11px] text-white/40">invited as {inv.role}</div>
                </div>
                <Badge>{inv.role}</Badge>
                <button onClick={() => copyLink(inv.token, inv.id)} className="text-white/40 hover:text-primary transition-colors" title="Copy invite link">
                  {copied === inv.id ? <Check size={15} className="text-secondary" /> : <Copy size={15} />}
                </button>
                <button onClick={() => revoke(inv.id)} className="text-white/30 hover:text-accent transition-colors">
                  <Trash2 size={15} />
                </button>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

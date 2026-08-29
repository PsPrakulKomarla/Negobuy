import React, { useEffect, useState } from "react";
import { useSearchParams, useNavigate, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Sparkles, ArrowLeft } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import api, { setToken, formatApiError } from "../lib/api";
import { Button, Input, Spinner } from "../components/ui";

export default function AcceptInvite() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!token) {
      setError("Missing invite token.");
      setLoading(false);
      return;
    }
    api
      .get(`/team/invite/${token}`)
      .then((r) => setInfo(r.data))
      .catch((e) => setError(formatApiError(e.response?.data?.detail) || "Invite not found."))
      .finally(() => setLoading(false));
  }, [token]);

  const accept = async (e) => {
    e?.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const { data } = await api.post("/team/accept", {
        token,
        name: name || undefined,
        password: password || undefined,
      });
      if (data.access_token) setToken(data.access_token);
      setUser(data);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail) || "Could not accept invite.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-void flex items-center justify-center px-5 relative overflow-hidden">
      <div className="absolute top-[-20%] left-[-10%] w-[500px] h-[500px] rounded-full bg-primary/10 blur-[120px]" />
      <Link to="/" className="absolute top-6 left-6 flex items-center gap-2 text-white/50 hover:text-white text-sm transition-colors">
        <ArrowLeft size={16} /> Home
      </Link>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        className="w-full max-w-md glass rounded-3xl p-8 sm:p-10 relative z-10"
        data-testid="accept-invite-card"
      >
        {loading ? (
          <div className="py-10 flex justify-center">
            <Spinner className="w-8 h-8" />
          </div>
        ) : error && !info ? (
          <div className="text-center">
            <p className="text-accent mb-6" data-testid="accept-error">{error}</p>
            <Link to="/login">
              <Button variant="secondary">Go to sign in</Button>
            </Link>
          </div>
        ) : (
          <>
            <div className="text-xs tracking-[0.3em] uppercase text-primary/80 font-mono mb-3">
              You're invited
            </div>
            <h1 className="font-display text-3xl font-bold tracking-tight mb-2">
              Join {info?.organization_name}
            </h1>
            <p className="text-white/50 mb-8 text-sm">
              {info?.invited_by ? `${info.invited_by} invited ` : "You've been invited "} you to
              join as <span className="text-primary font-medium">{info?.role}</span> ({info?.email}).
            </p>

            <form onSubmit={accept} className="space-y-4">
              {!info?.has_account && (
                <>
                  <Input label="Full name" value={name} onChange={(e) => setName(e.target.value)} data-testid="accept-name" required />
                  <Input label="Create password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} data-testid="accept-password" required />
                </>
              )}
              {info?.has_account && (
                <p className="text-sm text-white/50">You already have a NegoBuy account — accept to switch into this organization.</p>
              )}
              {error && <div className="text-sm text-accent bg-accent/10 border border-accent/20 rounded-xl px-4 py-3">{error}</div>}
              <Button type="submit" size="lg" className="w-full" disabled={submitting} data-testid="accept-submit">
                {submitting ? <Spinner /> : <Sparkles size={18} />} Accept invitation
              </Button>
            </form>
          </>
        )}
      </motion.div>
    </div>
  );
}

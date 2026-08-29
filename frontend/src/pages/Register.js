import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, Sparkles } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { Button, Input, Spinner } from "../components/ui";
import { formatApiError } from "../lib/api";

const GOOGLE_AUTH = "https://auth.emergentagent.com/";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    name: "",
    email: "",
    password: "",
    organization_name: "",
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await register(form);
      navigate("/dashboard");
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail) || err.message);
    } finally {
      setLoading(false);
    }
  };

  const google = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirect = `${window.location.origin}/dashboard`;
    window.location.href = `${GOOGLE_AUTH}?redirect=${encodeURIComponent(redirect)}`;
  };

  return (
    <div className="min-h-screen bg-void flex items-center justify-center px-5 relative overflow-hidden">
      <div className="absolute top-[-20%] right-[-10%] w-[500px] h-[500px] rounded-full bg-primary/10 blur-[120px]" />
      <div className="absolute bottom-[-20%] left-[-10%] w-[500px] h-[500px] rounded-full bg-accent/5 blur-[120px]" />

      <Link
        to="/"
        className="absolute top-6 left-6 flex items-center gap-2 text-white/50 hover:text-white text-sm transition-colors"
      >
        <ArrowLeft size={16} /> Back
      </Link>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        className="w-full max-w-md glass rounded-3xl p-8 sm:p-10 relative z-10"
      >
        <div className="mb-8">
          <div className="text-xs tracking-[0.3em] uppercase text-primary/80 font-mono mb-3">
            Get started
          </div>
          <h1 className="font-display text-3xl font-bold tracking-tight">
            Deploy your AI Buyer
          </h1>
        </div>

        <button
          data-testid="google-register-btn"
          onClick={google}
          className="w-full flex items-center justify-center gap-3 bg-white text-black rounded-full py-3 font-medium hover:bg-white/90 transition-colors mb-6"
        >
          <img
            src="https://www.svgrepo.com/show/475656/google-color.svg"
            alt=""
            className="w-5 h-5"
          />
          Continue with Google
        </button>

        <div className="flex items-center gap-4 mb-6">
          <span className="flex-1 h-px bg-white/10" />
          <span className="text-xs text-white/30 font-mono">OR</span>
          <span className="flex-1 h-px bg-white/10" />
        </div>

        <form onSubmit={submit} className="space-y-4">
          <Input label="Full name" value={form.name} onChange={set("name")} data-testid="register-name" required />
          <Input label="Work email" type="email" value={form.email} onChange={set("email")} data-testid="register-email" required />
          <Input label="Organization (optional)" value={form.organization_name} onChange={set("organization_name")} data-testid="register-org" />
          <Input label="Password" type="password" value={form.password} onChange={set("password")} data-testid="register-password" required />
          {error && (
            <div data-testid="register-error" className="text-sm text-accent bg-accent/10 border border-accent/20 rounded-xl px-4 py-3">
              {error}
            </div>
          )}
          <Button type="submit" size="lg" className="w-full" disabled={loading} data-testid="register-submit">
            {loading ? <Spinner /> : <Sparkles size={18} />}
            Create account
          </Button>
        </form>

        <p className="mt-6 text-sm text-white/50 text-center">
          Already have an account?{" "}
          <Link to="/login" className="text-primary hover:text-cyan-300">
            Sign in
          </Link>
        </p>
      </motion.div>
    </div>
  );
}

import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, Mail } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { Button, Input, Spinner } from "../components/ui";
import { formatApiError } from "../lib/api";

const GOOGLE_AUTH = "https://auth.emergentagent.com/";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("buyer@test.com");
  const [password, setPassword] = useState("test123");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await login(email, password);
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
      <div className="absolute top-[-20%] left-[-10%] w-[500px] h-[500px] rounded-full bg-primary/10 blur-[120px]" />
      <div className="absolute bottom-[-20%] right-[-10%] w-[500px] h-[500px] rounded-full bg-secondary/5 blur-[120px]" />

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
            Welcome back
          </div>
          <h1 className="font-display text-3xl font-bold tracking-tight">
            Enter the command center
          </h1>
        </div>

        <button
          data-testid="google-login-btn"
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
          <Input
            label="Email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            data-testid="login-email"
            required
          />
          <Input
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            data-testid="login-password"
            required
          />
          {error && (
            <div
              data-testid="login-error"
              className="text-sm text-accent bg-accent/10 border border-accent/20 rounded-xl px-4 py-3"
            >
              {error}
            </div>
          )}
          <Button
            type="submit"
            size="lg"
            className="w-full"
            disabled={loading}
            data-testid="login-submit"
          >
            {loading ? <Spinner /> : <Mail size={18} />}
            Sign in
          </Button>
        </form>

        <p className="mt-6 text-sm text-white/50 text-center">
          No account?{" "}
          <Link to="/register" className="text-primary hover:text-cyan-300">
            Create one
          </Link>
        </p>
      </motion.div>
    </div>
  );
}

import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Spinner } from "../components/ui";

// Module-level guard: survives React StrictMode's mount→unmount→remount cycle (a fresh
// component instance gets a fresh useRef, which would exchange the single-use session_id
// twice and make the 2nd call fail). Keyed by session_id so each is processed exactly once.
const processedSessions = new Set();

export default function AuthCallback() {
  const { googleSession } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");

  useEffect(() => {
    const hash = window.location.hash || "";
    const params = new URLSearchParams(hash.replace(/^#/, ""));
    const sid = params.get("session_id");
    if (!sid) {
      setError("No session found. Please try again.");
      setTimeout(() => navigate("/login"), 1800);
      return;
    }
    if (processedSessions.has(sid)) return;
    processedSessions.add(sid);
    googleSession(sid)
      .then(() => navigate("/dashboard", { replace: true }))
      .catch((err) => {
        processedSessions.delete(sid);
        const detail = err?.response?.data?.detail;
        // Developer diagnostics (no secrets) — visible in the browser console / network tab.
        console.error("[google-auth] session exchange failed:", {
          status: err?.response?.status,
          detail,
        });
        const expired = typeof detail === "string" && detail.startsWith("SESSION_INVALID_OR_EXPIRED");
        setError(expired
          ? "That sign-in link expired. Redirecting you to sign in again…"
          : "Google sign-in failed. Redirecting…");
        setTimeout(() => navigate("/login"), 1800);
      });
    // eslint-disable-next-line
  }, []);

  return (
    <div className="min-h-screen bg-void flex flex-col items-center justify-center gap-4">
      <Spinner className="w-8 h-8" />
      <p className="text-white/50 text-sm font-mono" data-testid="auth-callback-status">
        {error || "Establishing secure session…"}
      </p>
    </div>
  );
}

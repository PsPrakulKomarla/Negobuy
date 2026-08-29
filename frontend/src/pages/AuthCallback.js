import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Spinner } from "../components/ui";

export default function AuthCallback() {
  const { googleSession } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;
    const hash = window.location.hash || "";
    const params = new URLSearchParams(hash.replace(/^#/, ""));
    const sid = params.get("session_id");
    if (!sid) {
      setError("No session found. Please try again.");
      setTimeout(() => navigate("/login"), 1800);
      return;
    }
    googleSession(sid)
      .then(() => navigate("/dashboard", { replace: true }))
      .catch(() => {
        setError("Google sign-in failed.");
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

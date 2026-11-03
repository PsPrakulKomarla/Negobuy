import React, { createContext, useContext, useEffect, useState } from "react";
import api, { setToken, getToken } from "../lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null = checking, false = logged out
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    // If returning from OAuth callback, skip /me check; AuthCallback exchanges the session_id first.
    if (window.location.hash?.includes("session_id=")) {
      setChecked(true);
      return;
    }
    if (!getToken()) {
      setUser(false);
      setChecked(true);
      return;
    }
    api
      .get("/auth/me")
      .then((r) => setUser(r.data))
      .catch(() => {
        setToken(null);
        setUser(false);
      })
      .finally(() => setChecked(true));
  }, []);

  const persist = (data) => {
    if (data.access_token) setToken(data.access_token);
    setUser(data);
    return data;
  };

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    return persist(data);
  };

  const register = async (payload) => {
    const { data } = await api.post("/auth/register", payload);
    return persist(data);
  };

  const googleSession = async (session_id) => {
    const { data } = await api.post("/auth/google/session", { session_id });
    return persist(data);
  };

  const refreshUser = async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
      return data;
    } catch (e) {
      return null;
    }
  };

  const logout = async () => {
    try {
      await api.post("/auth/logout");
    } catch (e) {}
    setToken(null);
    setUser(false);
  };

  return (
    <AuthContext.Provider
      value={{ user, checked, setUser, login, register, logout, googleSession, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);

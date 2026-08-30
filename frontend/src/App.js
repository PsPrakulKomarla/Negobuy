import React from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import { useAuth } from "./context/AuthContext";
import { Spinner } from "./components/ui";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Register from "./pages/Register";
import AuthCallback from "./pages/AuthCallback";
import AppLayout from "./components/AppLayout";
import Dashboard from "./pages/Dashboard";
import Missions from "./pages/Missions";
import NewMission from "./pages/NewMission";
import MissionDetail from "./pages/MissionDetail";
import VoiceCall from "./pages/VoiceCall";
import CallConsole from "./pages/CallConsole";
import CallReview from "./pages/CallReview";
import DirectNegotiation from "./pages/DirectNegotiation";
import CommunicationHub from "./pages/CommunicationHub";
import TelegramNegotiation from "./pages/TelegramNegotiation";
import Pricing from "./pages/Pricing";
import Team from "./pages/Team";
import AcceptInvite from "./pages/AcceptInvite";

function FullLoader() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-void">
      <Spinner className="w-8 h-8" />
    </div>
  );
}

function Protected({ children }) {
  const { user, checked } = useAuth();
  if (!checked) return <FullLoader />;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function PublicOnly({ children }) {
  const { user, checked } = useAuth();
  if (!checked) return <FullLoader />;
  if (user) return <Navigate to="/dashboard" replace />;
  return children;
}

export default function App() {
  const location = useLocation();
  // Detect OAuth session_id synchronously during render (before ProtectedRoute runs)
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
  return (
    <div className="grain min-h-screen">
      <AnimatePresence mode="wait">
        <Routes location={location} key={location.pathname}>
          <Route path="/" element={<Landing />} />
          <Route path="/pricing" element={<Pricing />} />
          <Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
          <Route path="/register" element={<PublicOnly><Register /></PublicOnly>} />
          <Route path="/auth/callback" element={<AuthCallback />} />
          <Route path="/accept-invite" element={<AcceptInvite />} />

          <Route
            element={
              <Protected>
                <AppLayout />
              </Protected>
            }
          >
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/missions" element={<Missions />} />
            <Route path="/missions/new" element={<NewMission />} />
            <Route path="/direct" element={<DirectNegotiation />} />
            <Route path="/communications" element={<CommunicationHub />} />
            <Route path="/telegram" element={<TelegramNegotiation />} />
            <Route path="/missions/:id" element={<MissionDetail />} />
            <Route path="/missions/:id/call/:vendorId" element={<VoiceCall />} />
            <Route path="/missions/:id/call-console/:vendorId" element={<CallConsole />} />
            <Route path="/missions/:id/call-review/:ref" element={<CallReview />} />
            <Route path="/team" element={<Team />} />
            <Route path="/plans" element={<Pricing embedded />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AnimatePresence>
    </div>
  );
}

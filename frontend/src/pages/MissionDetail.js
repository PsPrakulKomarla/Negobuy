import React, { useCallback, useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  ShieldCheck,
  Building2,
  Phone,
  Handshake,
  Scale,
  CheckCircle2,
  ExternalLink,
  MapPin,
  Trophy,
  AlertTriangle,
  ArrowLeft,
  Radio,
  Mail,
  FileDown,
  PhoneCall,
} from "lucide-react";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import BuyerScene from "../three/BuyerScene";
import OutreachModal from "../components/OutreachModal";
import CallHistory from "../components/CallHistory";
import MissionCommandCenter from "../components/MissionCommandCenter";
import {
  Button,
  Card,
  StatusPill,
  Spinner,
  Badge,
  SectionLabel,
  AnimatedNumber,
} from "../components/ui";

const PIPELINE = [
  { key: "REQUIREMENT", label: "Requirement", icon: Search, statuses: ["DRAFT", "REQUIREMENT_REVIEW"] },
  { key: "DISCOVERY", label: "Discovery", icon: Building2, statuses: ["DISCOVERING"] },
  { key: "VERIFICATION", label: "Verification", icon: ShieldCheck, statuses: ["VERIFYING"] },
  { key: "NEGOTIATION", label: "Negotiation", icon: Handshake, statuses: ["CONTACTING", "NEGOTIATING"] },
  { key: "COMPARISON", label: "Comparison", icon: Scale, statuses: ["COMPARING"] },
  { key: "APPROVAL", label: "Approval", icon: CheckCircle2, statuses: ["AWAITING_APPROVAL", "APPROVED", "REJECTED", "COMPLETED"] },
];

const ORDER = ["DRAFT", "REQUIREMENT_REVIEW", "DISCOVERING", "VERIFYING", "CONTACTING", "NEGOTIATING", "COMPARING", "AWAITING_APPROVAL", "APPROVED"];

function Pipeline({ status }) {
  const currentIdx = ORDER.indexOf(status);
  return (
    <div className="flex items-center gap-1 overflow-x-auto pb-2">
      {PIPELINE.map((stage, i) => {
        const active = stage.statuses.includes(status);
        const stageMinIdx = ORDER.indexOf(stage.statuses[0]);
        const done = currentIdx > stageMinIdx && !active;
        return (
          <React.Fragment key={stage.key}>
            <div
              className={`flex items-center gap-2 px-3 py-2 rounded-xl border shrink-0 transition-colors ${
                active
                  ? "border-primary/40 bg-primary/10 text-primary"
                  : done
                  ? "border-secondary/30 bg-secondary/5 text-secondary"
                  : "border-white/10 text-white/35"
              }`}
            >
              <stage.icon size={15} />
              <span className="text-xs font-medium whitespace-nowrap">{stage.label}</span>
              {active && <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulseGlow" />}
            </div>
            {i < PIPELINE.length - 1 && (
              <span className={`w-4 h-px shrink-0 ${done ? "bg-secondary/40" : "bg-white/10"}`} />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

function ScoreBar({ label, value }) {
  return (
    <div>
      <div className="flex justify-between text-[10px] text-white/40 mb-1">
        <span className="uppercase tracking-wider">{label}</span>
        <span className="font-mono">{Math.round(value || 0)}</span>
      </div>
      <div className="h-1 rounded-full bg-white/10 overflow-hidden">
        <div
          className="h-full bg-primary rounded-full transition-[width] duration-700"
          style={{ width: `${value || 0}%` }}
        />
      </div>
    </div>
  );
}

export default function MissionDetail() {
  const { id } = useParams();
  const [mission, setMission] = useState(null);
  const [vendors, setVendors] = useState([]);
  const [activity, setActivity] = useState([]);
  const [offers, setOffers] = useState([]);
  const [comparison, setComparison] = useState(null);
  const [loading, setLoading] = useState(true);
  const [discovering, setDiscovering] = useState(false);
  const [negotiatingId, setNegotiatingId] = useState(null);
  const [comparing, setComparing] = useState(false);
  const [approving, setApproving] = useState(false);
  const [outreachVendor, setOutreachVendor] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const pollRef = useRef(null);

  const load = useCallback(async () => {
    const [m, v, a, o] = await Promise.all([
      api.get(`/missions/${id}`),
      api.get(`/missions/${id}/vendors`),
      api.get(`/missions/${id}/activity`),
      api.get(`/missions/${id}/offers`),
    ]);
    setMission(m.data);
    setVendors(v.data);
    setActivity(a.data);
    setOffers(o.data);
    api.get(`/missions/${id}/comparison`).then((c) => setComparison(c.data)).catch(() => {});
    return m.data;
  }, [id]);

  useEffect(() => {
    load().finally(() => setLoading(false));
    return () => clearInterval(pollRef.current);
    // eslint-disable-next-line
  }, [id]);

  useEffect(() => {
    if (!mission) return;
    const busy = ["DISCOVERING", "VERIFYING"].includes(mission.status);
    if (busy && !pollRef.current) {
      pollRef.current = setInterval(async () => {
        const m = await load();
        if (!["DISCOVERING", "VERIFYING"].includes(m.status)) {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setDiscovering(false);
        }
      }, 3000);
    }
    return () => {};
    // eslint-disable-next-line
  }, [mission?.status]);

  const runDiscovery = async () => {
    setDiscovering(true);
    try {
      await api.post(`/missions/${id}/discover`);
      toast.success("Discovery started — searching the web for suppliers");
      setTimeout(load, 1500);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
      setDiscovering(false);
    }
  };

  const negotiate = async (vendorId) => {
    setNegotiatingId(vendorId);
    try {
      const { data } = await api.post(`/missions/${id}/vendors/${vendorId}/negotiate`, { rounds: 3 });
      toast.success(
        data.final_price
          ? `Negotiation preview complete · indicative ${mission.currency} ${data.final_price}/unit`
          : "Negotiation preview complete"
      );
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setNegotiatingId(null);
    }
  };

  const compare = async () => {
    setComparing(true);
    try {
      const { data } = await api.post(`/missions/${id}/compare`);
      setComparison(data);
      toast.success("Comparison ready");
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setComparing(false);
    }
  };

  const approve = async (action, offerId) => {    setApproving(true);
    try {
      await api.post(`/missions/${id}/approve`, { action, offer_id: offerId });
      toast.success(
        action === "APPROVE" ? "Purchase approved" : action === "REJECT" ? "Rejected" : "Sent back to negotiation"
      );
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setApproving(false);
    }
  };

  const downloadReport = async () => {
    setDownloading(true);
    try {
      const res = await api.get(`/missions/${id}/report`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `NegoBuy-${(mission.title || "report").replace(/\s+/g, "_")}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error("Could not generate the report.");
    } finally {
      setDownloading(false);
    }
  };

  if (loading || !mission)
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Spinner className="w-8 h-8" />
      </div>
    );

  const verified = vendors.filter((v) => v.verification_status === "VERIFIED").length;
  const negotiated = offers.length;
  const stage = {
    candidates: Math.max(vendors.length, activity.length ? 30 : 12),
    shortlisted: vendors.length,
    verified,
    negotiating: negotiated,
  };
  const recId = comparison?.recommendation?.recommended_offer_id;
  const busy = ["DISCOVERING", "VERIFYING"].includes(mission.status);

  return (
    <div className="p-6 lg:p-10 max-w-7xl mx-auto">
      <Link to="/missions" className="inline-flex items-center gap-2 text-white/40 hover:text-white text-sm mb-6 transition-colors">
        <ArrowLeft size={15} /> All missions
      </Link>

      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
        <div className="min-w-0">
          <div className="flex items-center gap-3 mb-2">
            <StatusPill status={mission.status} />
            {busy && <span className="text-xs text-primary font-mono animate-pulseGlow">● operating</span>}
          </div>
          <h1 className="font-display text-3xl lg:text-4xl font-bold tracking-tight">{mission.title}</h1>
          <div className="text-sm text-white/45 mt-2 flex gap-4 flex-wrap">
            {mission.quantity && <span>{mission.quantity} units</span>}
            {mission.budget && <span>Budget {mission.currency} {Number(mission.budget).toLocaleString()}</span>}
            {mission.delivery_location && <span className="flex items-center gap-1"><MapPin size={13} /> {mission.delivery_location}</span>}
            {mission.deadline_days && <span>{mission.deadline_days} day deadline</span>}
          </div>
        </div>
        <Button variant="secondary" size="sm" onClick={downloadReport} disabled={downloading} data-testid="download-report-btn">
          {downloading ? <Spinner /> : <FileDown size={15} />} Download report
        </Button>
      </div>

      <MissionCommandCenter missionId={id} />

      <Card glass className="p-4 mb-6">
        <Pipeline status={mission.status} />
      </Card>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* 3D + activity */}
        <div className="space-y-6">
          <Card className="overflow-hidden relative h-72">
            <BuyerScene stage={stage} active={busy} className="absolute inset-0" />
            <div className="absolute top-4 left-4 text-xs font-mono text-primary/80 tracking-widest">
              AI BUYER · ORCHESTRATOR
            </div>
            <div className="absolute bottom-4 left-4 right-4 grid grid-cols-4 gap-2 text-center">
              {[
                ["Candidates", stage.candidates, "text-white/60"],
                ["Shortlist", stage.shortlisted, "text-primary"],
                ["Verified", stage.verified, "text-secondary"],
                ["Offers", stage.negotiating, "text-accent"],
              ].map(([l, v, c]) => (
                <div key={l} className="glass rounded-lg py-1.5">
                  <div className={`font-display font-bold text-lg ${c}`}>
                    <AnimatedNumber value={v} />
                  </div>
                  <div className="text-[9px] text-white/40 uppercase tracking-wider">{l}</div>
                </div>
              ))}
            </div>
          </Card>

          <div>
            <SectionLabel>Audit trail</SectionLabel>
            <Card glass className="p-5 max-h-[400px] overflow-y-auto">
              {activity.length ? (
                <div className="space-y-4">
                  {activity.map((a) => (
                    <div key={a.id} className="flex gap-3">
                      <div className="flex flex-col items-center">
                        <span className="w-2 h-2 rounded-full bg-primary mt-1.5" />
                        <span className="flex-1 w-px bg-white/10 my-1" />
                      </div>
                      <div className="min-w-0 pb-1">
                        <div className="text-[11px] font-mono text-primary/70">{a.agent}</div>
                        <div className="text-sm text-white/85">{a.action}</div>
                        {a.result && <div className="text-xs text-white/40 mt-0.5">{a.result}</div>}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-white/40 text-sm text-center py-6">No activity yet.</p>
              )}
            </Card>
          </div>

          <CallHistory missionId={id} />
        </div>

        {/* Main */}
        <div className="lg:col-span-2 space-y-6">
          {/* Discovery action */}
          {vendors.length === 0 && (
            <Card className="p-8 text-center tracing-border">
              <Building2 size={30} className="text-primary/50 mx-auto mb-4" />
              <h3 className="font-display text-xl font-semibold mb-2">Find the best suppliers</h3>
              <p className="text-white/50 text-sm mb-6 max-w-md mx-auto">
                The Discovery Agent will search real web sources, deduplicate candidates,
                score them on evidence and produce a verified shortlist.
              </p>
              <Button size="lg" onClick={runDiscovery} disabled={discovering || busy} data-testid="run-discovery-btn">
                {discovering || busy ? <Spinner /> : <Search size={18} />}
                {busy ? "Discovering…" : "Run discovery"}
              </Button>
            </Card>
          )}

          {/* Vendors */}
          {vendors.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-4">
                <SectionLabel>Supplier shortlist</SectionLabel>
                <div className="flex gap-2">
                  <Button variant="ghost" size="sm" onClick={runDiscovery} disabled={busy} data-testid="rerun-discovery">
                    <Search size={14} /> Re-run
                  </Button>
                  {offers.length > 0 && (
                    <Button size="sm" onClick={compare} disabled={comparing} data-testid="compare-btn">
                      {comparing ? <Spinner /> : <Scale size={14} />} Compare offers
                    </Button>
                  )}
                </div>
              </div>
              <div className="grid sm:grid-cols-2 gap-4">
                {vendors.map((v, i) => {
                  const offer = offers.find((o) => o.vendor_id === v.id);
                  return (
                    <motion.div
                      key={v.id}
                      initial={{ opacity: 0, y: 16 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.4, delay: i * 0.04 }}
                    >
                      <Card className="p-5 h-full flex flex-col" data-testid={`vendor-${v.id}`}>
                        <div className="flex items-start justify-between gap-2 mb-3">
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-[10px] font-mono text-white/30">#{v.rank || i + 1}</span>
                              <StatusPill status={v.verification_status} />
                            </div>
                            <h4 className="font-medium mt-1.5 truncate">{v.name}</h4>
                            {v.location && (
                              <div className="text-xs text-white/40 flex items-center gap-1 mt-0.5">
                                <MapPin size={11} /> {v.location}
                              </div>
                            )}
                          </div>
                          <div className="text-right shrink-0">
                            <div className="font-display font-bold text-xl text-primary">
                              {Math.round(v.weighted_score)}
                            </div>
                            <div className="text-[9px] text-white/40 uppercase">score</div>
                          </div>
                        </div>

                        <p className="text-xs text-white/50 mb-3 line-clamp-2">{v.reasoning || v.description}</p>

                        <div className="space-y-2 mb-4">
                          <ScoreBar label="Category" value={v.scores?.category_match} />
                          <ScoreBar label="Credibility" value={v.scores?.credibility} />
                          <ScoreBar label="Evidence" value={v.scores?.evidence_quality} />
                        </div>

                        {offer && (
                          <div className="text-xs bg-secondary/10 border border-secondary/20 rounded-lg px-3 py-2 mb-3">
                            <span className="text-secondary font-medium">
                              Offer: {mission.currency} {offer.negotiated_price}/unit
                            </span>
                            {offer.simulation && (
                              <span className="text-white/40 ml-1">(preview)</span>
                            )}
                          </div>
                        )}

                        <div className="mt-auto flex items-center gap-2 pt-2">
                          <a href={v.website} target="_blank" rel="noreferrer" className="text-white/40 hover:text-primary transition-colors" title="Evidence source">
                            <ExternalLink size={15} />
                          </a>
                          {v.memory && (
                            <span className="text-[10px] font-mono text-secondary/80" title={`Known supplier · best ${mission.currency} ${v.memory.best_price ?? "?"}`}>
                              ★ known
                            </span>
                          )}
                          <div className="flex-1" />
                          <Button variant="ghost" size="sm" onClick={() => setOutreachVendor(v)} data-testid={`outreach-${v.id}`}>
                            <Mail size={14} />
                          </Button>
                          <Button variant="secondary" size="sm" onClick={() => negotiate(v.id)} disabled={negotiatingId === v.id} data-testid={`negotiate-${v.id}`}>
                            {negotiatingId === v.id ? <Spinner /> : <Handshake size={14} />} Negotiate
                          </Button>
                          <Link to={`/missions/${id}/call-console/${v.id}`}>
                            <Button variant="ghost" size="sm" data-testid={`exotel-call-${v.id}`} title="AI negotiation call">
                              <PhoneCall size={14} />
                            </Button>
                          </Link>
                          <Link to={`/missions/${id}/call/${v.id}`}>
                            <Button variant="ghost" size="sm" data-testid={`call-${v.id}`}>
                              <Phone size={14} />
                            </Button>
                          </Link>
                        </div>
                      </Card>
                    </motion.div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Comparison + recommendation */}
          <AnimatePresence>
            {comparison && (
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
                <SectionLabel>Comparison & recommendation</SectionLabel>

                {comparison.recommendation && (
                  <Card className="p-5 mb-4 border-secondary/25 bg-secondary/5">
                    <div className="flex items-center gap-2 mb-2 text-secondary">
                      <Trophy size={16} />
                      <span className="font-medium text-sm">AI Recommendation</span>
                      <Badge className="ml-auto">
                        score {Math.round(comparison.recommendation.recommendation_score)}
                      </Badge>
                    </div>
                    <p className="text-sm text-white/80 leading-relaxed">
                      {comparison.recommendation.reasoning}
                    </p>
                    {comparison.recommendation.risks?.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {comparison.recommendation.risks.map((r, i) => (
                          <span key={i} className="text-[11px] text-yellow-300/80 flex items-center gap-1">
                            <AlertTriangle size={11} /> {r}
                          </span>
                        ))}
                      </div>
                    )}
                  </Card>
                )}

                <Card className="overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-[10px] uppercase tracking-wider text-white/40 border-b hairline">
                          <th className="p-3">Vendor</th>
                          <th className="p-3">Unit</th>
                          <th className="p-3">Landed cost</th>
                          <th className="p-3">Delivery</th>
                          <th className="p-3">Warranty</th>
                          <th className="p-3"></th>
                        </tr>
                      </thead>
                      <tbody>
                        {comparison.offers.map((o) => {
                          const isRec = o.id === recId;
                          return (
                            <tr key={o.id} className={`border-b hairline last:border-0 ${isRec ? "bg-secondary/5" : ""}`} data-testid={`compare-row-${o.id}`}>
                              <td className="p-3 font-medium">
                                <div className="flex items-center gap-2">
                                  {isRec && <Trophy size={13} className="text-secondary" />}
                                  {o.vendor_name}
                                </div>
                              </td>
                              <td className="p-3 text-white/70">{mission.currency} {o.negotiated_price}</td>
                              <td className="p-3 font-mono text-primary">{mission.currency} {o.total_cost?.toLocaleString()}</td>
                              <td className="p-3 text-white/60">{o.delivery_time || "—"}</td>
                              <td className="p-3 text-white/60">{o.warranty || "—"}</td>
                              <td className="p-3">
                                <Button
                                  size="sm"
                                  variant={isRec ? "success" : "secondary"}
                                  onClick={() => approve("APPROVE", o.id)}
                                  disabled={approving || mission.status === "APPROVED"}
                                  data-testid={`approve-${o.id}`}
                                >
                                  {mission.status === "APPROVED" ? "Approved" : "Approve"}
                                </Button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </Card>

                {mission.status === "AWAITING_APPROVAL" && (
                  <div className="flex flex-wrap gap-3 mt-4 justify-end">
                    <Button variant="danger" onClick={() => approve("REJECT")} disabled={approving} data-testid="reject-btn">
                      Reject
                    </Button>
                    <Button variant="secondary" onClick={() => approve("NEGOTIATE_FURTHER")} disabled={approving} data-testid="negotiate-further-btn">
                      Negotiate further
                    </Button>
                    {recId && (
                      <Button variant="success" onClick={() => approve("APPROVE", recId)} disabled={approving} data-testid="approve-recommended-btn">
                        <CheckCircle2 size={16} /> Approve recommended
                      </Button>
                    )}
                  </div>
                )}

                <p className="text-[11px] text-white/30 mt-3 flex items-center gap-1.5">
                  <Radio size={11} /> Offers marked "preview" come from AI negotiation simulation, not a live vendor call. Enable voice to negotiate for real.
                </p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {outreachVendor && (
        <OutreachModal
          missionId={id}
          vendor={outreachVendor}
          currency={mission.currency}
          onClose={() => setOutreachVendor(null)}
          onOfferApplied={load}
        />
      )}
    </div>
  );
}

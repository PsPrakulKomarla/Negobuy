import React, { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowLeft, PhoneCall, ShieldAlert, Ban, Target, FlaskConical,
  Radio, Mic, Info,
} from "lucide-react";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { Button, Card, Input, Textarea, Spinner, SectionLabel } from "../components/ui";

function Toggle({ label, hint, checked, onChange, testid }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      data-testid={testid}
      className="flex items-start gap-3 text-left w-full"
    >
      <span
        className={`mt-0.5 w-10 h-6 rounded-full shrink-0 relative transition-colors ${
          checked ? "bg-primary" : "bg-white/15"
        }`}
      >
        <span
          className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-[left] ${
            checked ? "left-[18px]" : "left-0.5"
          }`}
        />
      </span>
      <span>
        <span className="text-sm font-medium text-white/90">{label}</span>
        {hint && <span className="block text-xs text-white/40">{hint}</span>}
      </span>
    </button>
  );
}

export default function CallConsole() {
  const { id, vendorId } = useParams();
  const nav = useNavigate();
  const [mission, setMission] = useState(null);
  const [vendor, setVendor] = useState(null);
  const [providerReady, setProviderReady] = useState(null);
  const [loading, setLoading] = useState(true);
  const [step, setStep] = useState("configure"); // configure | approve
  const [config, setConfig] = useState(null);
  const [placing, setPlacing] = useState(false);

  const [form, setForm] = useState({
    supplier_name: "", to_number: "", product: "", quantity: "",
    current_price: "", target_price: "", max_authorized_price: "",
    delivery_location: "", delivery_deadline_days: "", warranty_requirements: "",
    payment_preferences: "", negotiation_priorities: "", special_instructions: "",
    currency: "INR", test_mode: true, disclose_ai: true, recording_notice: true,
  });

  useEffect(() => {
    Promise.all([
      api.get(`/missions/${id}`).then((r) => r.data),
      api.get(`/missions/${id}/vendors`).then((r) => r.data),
      api.get("/voice/exotel/status").then((r) => r.data).catch(() => ({ state: "NOT_CONFIGURED" })),
    ])
      .then(([m, vs, ex]) => {
        setMission(m);
        setProviderReady(ex);
        const v = vs.find((x) => x.id === vendorId);
        setVendor(v);
        setForm((f) => ({
          ...f,
          supplier_name: v?.name || "",
          to_number: (v?.contact_phones || [])[0] || "",
          product: m?.title || "",
          quantity: m?.quantity || "",
          delivery_location: m?.delivery_location || "",
          delivery_deadline_days: m?.deadline_days || "",
          warranty_requirements: m?.warranty_requirements || "",
          payment_preferences: m?.payment_requirements || "",
          currency: m?.currency || "INR",
        }));
      })
      .finally(() => setLoading(false));
  }, [id, vendorId]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const num = (v) => (v === "" || v == null ? null : Number(v));

  const buildPayload = () => ({
    mission_id: id,
    vendor_id: vendorId,
    to_number: form.to_number.trim(),
    supplier_name: form.supplier_name || null,
    product: form.product || null,
    quantity: num(form.quantity),
    current_price: num(form.current_price),
    target_price: num(form.target_price),
    max_authorized_price: num(form.max_authorized_price),
    delivery_location: form.delivery_location || null,
    delivery_deadline_days: num(form.delivery_deadline_days),
    warranty_requirements: form.warranty_requirements || null,
    payment_preferences: form.payment_preferences || null,
    negotiation_priorities: form.negotiation_priorities
      ? form.negotiation_priorities.split(",").map((s) => s.trim()).filter(Boolean)
      : [],
    special_instructions: form.special_instructions || null,
    currency: form.currency || "INR",
    test_mode: form.test_mode,
    disclose_ai: form.disclose_ai,
    recording_notice: form.recording_notice,
  });

  const review = async () => {
    if (!form.to_number.trim()) {
      toast.error("Enter the destination phone number you are authorized to call.");
      return;
    }
    try {
      const { data } = await api.post("/voice/console/config", buildPayload());
      setConfig(data);
      setStep("approve");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const startCall = async () => {
    setPlacing(true);
    try {
      const { data } = await api.post(`/voice/console/approve/${config.session_ref}`);
      if (data.status === "NOT_CONFIGURED") {
        toast.error("Exotel is not ready to place the call.");
      } else if (data.status === "failed") {
        toast.error("The provider did not accept the call.");
      } else if (data.status === "SIMULATED_COMPLETE") {
        toast.success("Test call complete — opening review.");
      } else {
        toast.success("Call placed — opening review.");
      }
      nav(`/missions/${id}/call-review/${config.session_ref}`);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
      setPlacing(false);
    }
  };

  if (loading || !mission)
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Spinner className="w-8 h-8" />
      </div>
    );

  return (
    <div className="p-6 lg:p-10 max-w-4xl mx-auto" data-testid="call-console">
      <Link
        to={`/missions/${id}`}
        className="inline-flex items-center gap-2 text-white/40 hover:text-white text-sm mb-6 transition-colors"
      >
        <ArrowLeft size={15} /> Back to mission
      </Link>

      <div className="flex items-center gap-3 mb-2">
        <PhoneCall className="text-primary" size={22} />
        <h1 className="font-display text-3xl font-bold tracking-tight">Call Test Console</h1>
      </div>
      <p className="text-white/45 text-sm mb-8">
        Configure and explicitly approve an AI negotiation call. Nothing is dialled until you
        press <b className="text-white/70">Start AI Negotiation Call</b>.
      </p>

      {step === "configure" && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
          <div>
            <SectionLabel>Call objective</SectionLabel>
            <Card className="p-6 grid sm:grid-cols-2 gap-4">
              <Input label="Supplier name" value={form.supplier_name} onChange={set("supplier_name")} data-testid="cc-supplier" />
              <Input label="Phone number (you are authorized to call)" value={form.to_number} onChange={set("to_number")} placeholder="+91XXXXXXXXXX" data-testid="cc-number" />
              <Input label="Product" value={form.product} onChange={set("product")} data-testid="cc-product" />
              <Input label="Quantity" type="number" value={form.quantity} onChange={set("quantity")} data-testid="cc-quantity" />
              <Input label={`Current quoted price (${form.currency})`} type="number" value={form.current_price} onChange={set("current_price")} data-testid="cc-current-price" />
              <Input label={`Target price (${form.currency})`} type="number" value={form.target_price} onChange={set("target_price")} data-testid="cc-target-price" />
              <Input label={`Maximum authorized price (${form.currency})`} type="number" value={form.max_authorized_price} onChange={set("max_authorized_price")} data-testid="cc-max-price" />
              <Input label="Currency" value={form.currency} onChange={set("currency")} data-testid="cc-currency" />
              <Input label="Delivery location" value={form.delivery_location} onChange={set("delivery_location")} data-testid="cc-location" />
              <Input label="Delivery deadline (days)" type="number" value={form.delivery_deadline_days} onChange={set("delivery_deadline_days")} data-testid="cc-deadline" />
              <Input label="Warranty requirements" value={form.warranty_requirements} onChange={set("warranty_requirements")} data-testid="cc-warranty" />
              <Input label="Payment preferences" value={form.payment_preferences} onChange={set("payment_preferences")} data-testid="cc-payment" />
              <div className="sm:col-span-2">
                <Input label="Negotiation priorities (comma separated)" value={form.negotiation_priorities} onChange={set("negotiation_priorities")} placeholder="price, delivery, loading & unloading charges" data-testid="cc-priorities" />
              </div>
              <div className="sm:col-span-2">
                <Textarea label="Special instructions" rows={3} value={form.special_instructions} onChange={set("special_instructions")} placeholder="e.g. Be polite. Ask about delivery, loading and unloading charges. Confirm delivery time." data-testid="cc-instructions" />
              </div>
            </Card>
          </div>

          <div>
            <SectionLabel>Mode & transparency</SectionLabel>
            <Card className="p-6 space-y-5">
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => setForm((f) => ({ ...f, test_mode: true }))}
                  data-testid="cc-mode-test"
                  className={`flex-1 rounded-xl border p-4 text-left transition-colors ${
                    form.test_mode ? "border-primary/50 bg-primary/10" : "border-white/12 hover:bg-white/5"
                  }`}
                >
                  <div className="flex items-center gap-2 font-medium text-sm">
                    <FlaskConical size={16} className="text-primary" /> Test call (simulated)
                  </div>
                  <p className="text-xs text-white/45 mt-1">
                    Runs the full negotiation through the AI brain and produces a transcript &
                    analysis to review. No phone is dialled.
                  </p>
                </button>
                <button
                  type="button"
                  onClick={() => setForm((f) => ({ ...f, test_mode: false }))}
                  data-testid="cc-mode-live"
                  className={`flex-1 rounded-xl border p-4 text-left transition-colors ${
                    !form.test_mode ? "border-accent/50 bg-accent/10" : "border-white/12 hover:bg-white/5"
                  }`}
                >
                  <div className="flex items-center gap-2 font-medium text-sm">
                    <Radio size={16} className="text-accent" /> Live call (real phone)
                  </div>
                  <p className="text-xs text-white/45 mt-1">
                    Places a real call via Exotel to the number above. Requires provider streaming
                    config for in-call AI speech.
                  </p>
                </button>
              </div>
              <Toggle label="Disclose AI identity at the start of the call" hint="Required for transparency — the supplier is told they are speaking with an AI assistant." checked={form.disclose_ai} onChange={(v) => setForm((f) => ({ ...f, disclose_ai: v }))} testid="cc-disclose" />
              <Toggle label="Play a recording notice" hint="Where required by law/policy, notify that the call may be recorded." checked={form.recording_notice} onChange={(v) => setForm((f) => ({ ...f, recording_notice: v }))} testid="cc-recording" />
            </Card>
          </div>

          {!form.test_mode && providerReady?.state !== "READY" && (
            <div className="rounded-xl border border-yellow-400/25 bg-yellow-400/5 p-3 text-sm text-yellow-200 flex gap-2" data-testid="cc-provider-warn">
              <Info size={15} className="shrink-0 mt-0.5" />
              <span>Exotel status: <b>{providerReady?.state}</b>. {providerReady?.message}</span>
            </div>
          )}

          <div className="flex justify-end">
            <Button size="lg" onClick={review} data-testid="cc-review-btn">
              Review before calling
            </Button>
          </div>
        </motion.div>
      )}

      {step === "approve" && config && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-6" data-testid="cc-approval">
          <Card className="p-6 border-primary/25 bg-primary/5">
            <div className="flex items-center gap-2 text-primary mb-4">
              <ShieldAlert size={18} /> <span className="font-medium">Confirm this call before it is placed</span>
            </div>
            <div className="grid sm:grid-cols-2 gap-x-8 gap-y-3 text-sm">
              <Field label="Who will be called" value={`${config.objective.supplier_name} · ${config.to}`} />
              <Field label="Mode" value={config.test_mode ? "TEST (simulated)" : "LIVE phone call"} />
              <Field label="Why the AI is calling" value={`Negotiate ${config.objective.product || "the purchase"}`} />
              <Field label="Quantity" value={config.objective.quantity ?? "—"} />
              <Field label="Target price" value={config.authority.target_price_per_unit ? `${config.authority.currency} ${config.authority.target_price_per_unit}` : "—"} />
              <Field label="Maximum authorized" value={config.authority.max_price_per_unit ? `${config.authority.currency} ${config.authority.max_price_per_unit}` : "—"} accent="text-accent" />
              <Field label="Deliver to" value={config.objective.delivery_location || "—"} />
              <Field label="Delivery deadline" value={config.objective.delivery_deadline_days ? `${config.objective.delivery_deadline_days} days` : "—"} />
            </div>
          </Card>

          {config.disclosure_script && (
            <Card className="p-5">
              <div className="flex items-center gap-2 text-white/70 mb-2 text-sm font-medium">
                <Mic size={15} className="text-primary" /> AI opening disclosure
              </div>
              <p className="text-sm text-white/70 italic">“{config.disclosure_script}”</p>
            </Card>
          )}

          <Card className="p-5 border-accent/20">
            <div className="flex items-center gap-2 text-accent mb-3 text-sm font-medium">
              <Ban size={15} /> The AI is NOT authorized to
            </div>
            <ul className="space-y-1.5">
              {config.not_authorized.map((r, i) => (
                <li key={i} className="text-sm text-white/60 flex gap-2">
                  <span className="text-accent">•</span> {r}
                </li>
              ))}
            </ul>
            <p className="text-[11px] text-white/40 mt-3 pt-3 border-t hairline flex items-center gap-1.5">
              <Target size={12} /> No material commitment happens without your approval.
            </p>
          </Card>

          <div className="flex justify-between gap-3">
            <Button variant="ghost" onClick={() => setStep("configure")} data-testid="cc-back-btn">
              Edit configuration
            </Button>
            <Button size="lg" variant={config.test_mode ? "primary" : "danger"} onClick={startCall} disabled={placing} data-testid="cc-start-call-btn">
              {placing ? <Spinner /> : <PhoneCall size={18} />}
              {config.test_mode ? "Start AI Test Call" : "Start AI Negotiation Call"}
            </Button>
          </div>
        </motion.div>
      )}
    </div>
  );
}

function Field({ label, value, accent = "text-white/85" }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-white/40">{label}</div>
      <div className={`font-medium ${accent}`}>{value}</div>
    </div>
  );
}

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Sparkles, ArrowRight, Wand2, HelpCircle, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { Button, Card, Input, Textarea, Spinner, SectionLabel, Badge } from "../components/ui";

const EXAMPLE =
  "I need 500 ergonomic office chairs under ₹5 lakh delivered to Bangalore within 10 days, with at least 3 year warranty.";

export default function NewMission() {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [extracting, setExtracting] = useState(false);
  const [creating, setCreating] = useState(false);
  const [spec, setSpec] = useState(null);

  const extract = async () => {
    if (!text.trim()) return;
    setExtracting(true);
    try {
      const { data } = await api.post("/missions/extract", { text });
      setSpec({
        title: data.title || "",
        category: data.category || "",
        quantity: data.quantity || "",
        budget: data.budget || "",
        currency: data.currency || "INR",
        delivery_location: data.delivery_location || "",
        deadline_days: data.deadline_days || "",
        warranty_requirements: data.warranty_requirements || "",
        payment_requirements: data.payment_requirements || "",
        specifications: data.specifications || [],
        quality_requirements: data.quality_requirements || [],
        clarifying_questions: data.clarifying_questions || [],
        missing_info: data.missing_info || [],
        summary: data.summary || "",
        ready_for_discovery: data.ready_for_discovery,
      });
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail) || "Extraction failed");
    } finally {
      setExtracting(false);
    }
  };

  const set = (k) => (e) => setSpec({ ...spec, [k]: e.target.value });

  const create = async () => {
    setCreating(true);
    try {
      const payload = {
        title: spec.title,
        description: spec.summary,
        category: spec.category,
        quantity: spec.quantity ? Number(spec.quantity) : null,
        budget: spec.budget ? Number(spec.budget) : null,
        currency: spec.currency,
        delivery_location: spec.delivery_location,
        deadline_days: spec.deadline_days ? Number(spec.deadline_days) : null,
        warranty_requirements: spec.warranty_requirements,
        payment_requirements: spec.payment_requirements,
        specifications: spec.specifications,
        quality_requirements: spec.quality_requirements,
        raw_request: text,
      };
      const { data } = await api.post("/missions", payload);
      toast.success("Mission created");
      navigate(`/missions/${data.id}`);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail) || "Could not create mission");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="p-6 lg:p-10 max-w-4xl mx-auto">
      <div className="mb-8">
        <div className="text-xs tracking-[0.3em] uppercase text-primary/80 font-mono mb-2">
          New procurement mission
        </div>
        <h1 className="font-display text-3xl lg:text-4xl font-bold tracking-tight">
          What do you need to buy?
        </h1>
        <p className="text-white/50 mt-2">
          Describe it naturally. The AI Requirement Agent will structure it for you.
        </p>
      </div>

      <Card glass className="p-6 mb-6 tracing-border">
        <Textarea
          label="Your requirement"
          rows={4}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={EXAMPLE}
          data-testid="requirement-input"
        />
        <div className="flex items-center justify-between mt-4 flex-wrap gap-3">
          <button
            onClick={() => setText(EXAMPLE)}
            className="text-xs text-white/40 hover:text-primary transition-colors font-mono"
            data-testid="use-example"
          >
            ↳ Use example
          </button>
          <Button onClick={extract} disabled={extracting || !text.trim()} data-testid="extract-btn">
            {extracting ? <Spinner /> : <Wand2 size={16} />}
            Structure requirement
          </Button>
        </div>
      </Card>

      {spec && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <SectionLabel>AI-structured specification</SectionLabel>

          {spec.summary && (
            <Card className="p-5 mb-4 flex gap-3">
              <Sparkles size={18} className="text-primary shrink-0 mt-0.5" />
              <p className="text-sm text-white/80">{spec.summary}</p>
            </Card>
          )}

          <Card className="p-6 space-y-4 mb-4">
            <Input label="Mission title" value={spec.title} onChange={set("title")} data-testid="spec-title" />
            <div className="grid sm:grid-cols-2 gap-4">
              <Input label="Category" value={spec.category} onChange={set("category")} data-testid="spec-category" />
              <Input label="Quantity" type="number" value={spec.quantity} onChange={set("quantity")} data-testid="spec-quantity" />
              <Input label="Budget" type="number" value={spec.budget} onChange={set("budget")} data-testid="spec-budget" />
              <Input label="Currency" value={spec.currency} onChange={set("currency")} data-testid="spec-currency" />
              <Input label="Delivery location" value={spec.delivery_location} onChange={set("delivery_location")} data-testid="spec-location" />
              <Input label="Deadline (days)" type="number" value={spec.deadline_days} onChange={set("deadline_days")} data-testid="spec-deadline" />
              <Input label="Warranty" value={spec.warranty_requirements} onChange={set("warranty_requirements")} data-testid="spec-warranty" />
              <Input label="Payment terms" value={spec.payment_requirements} onChange={set("payment_requirements")} data-testid="spec-payment" />
            </div>
            {spec.specifications?.length > 0 && (
              <div>
                <span className="block mb-2 text-xs tracking-[0.2em] uppercase text-white/50">
                  Specifications
                </span>
                <div className="flex flex-wrap gap-2">
                  {spec.specifications.map((s, i) => (
                    <Badge key={i}>{s}</Badge>
                  ))}
                </div>
              </div>
            )}
          </Card>

          {spec.clarifying_questions?.length > 0 && (
            <Card className="p-5 mb-4 border-yellow-400/20">
              <div className="flex items-center gap-2 mb-3 text-yellow-300 text-sm font-medium">
                <HelpCircle size={16} /> The AI suggests clarifying
              </div>
              <ul className="space-y-2 text-sm text-white/60">
                {spec.clarifying_questions.map((q, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-yellow-300/60">·</span> {q}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-white/35 mt-3">
                Optional — you can still proceed and refine later.
              </p>
            </Card>
          )}

          {spec.missing_info?.length > 0 && (
            <Card className="p-5 mb-4 border-white/10">
              <div className="flex items-center gap-2 mb-2 text-white/50 text-xs font-mono uppercase tracking-widest">
                <AlertTriangle size={14} /> Missing info
              </div>
              <div className="flex flex-wrap gap-2">
                {spec.missing_info.map((m, i) => (
                  <Badge key={i}>{m}</Badge>
                ))}
              </div>
            </Card>
          )}

          <div className="flex justify-end gap-3">
            <Button variant="secondary" onClick={() => setSpec(null)} data-testid="spec-reset">
              Start over
            </Button>
            <Button onClick={create} disabled={creating} size="lg" data-testid="create-mission-btn">
              {creating ? <Spinner /> : <ArrowRight size={16} />}
              Create mission
            </Button>
          </div>
        </motion.div>
      )}
    </div>
  );
}

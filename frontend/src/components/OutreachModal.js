import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Sparkles, Send, Mail, Lightbulb, ClipboardCheck, MessageSquareText, Wand2 } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { Button, Spinner, Badge, Input, Textarea } from "./ui";

const TONES = ["professional", "friendly", "firm"];

export default function OutreachModal({ missionId, vendor, currency, onClose, onOfferApplied }) {
  const base = `/missions/${missionId}/vendors/${vendor.id}/outreach`;
  const [thread, setThread] = useState({ messages: [] });
  const [tone, setTone] = useState("professional");
  const [custom, setCustom] = useState("");
  const [toEmail, setToEmail] = useState((vendor.contact_emails || [])[0] || "");
  const [subject, setSubject] = useState("");
  const [bodyText, setBodyText] = useState("");
  const [bodyHtml, setBodyHtml] = useState("");
  const [composing, setComposing] = useState(false);
  const [sending, setSending] = useState(false);
  const [strategy, setStrategy] = useState(null);
  const [loadingStrategy, setLoadingStrategy] = useState(false);
  const [replyBody, setReplyBody] = useState("");
  const [replySubject, setReplySubject] = useState("");
  const [parsed, setParsed] = useState(null);
  const [parsing, setParsing] = useState(false);
  const [summary, setSummary] = useState(null);
  const [tab, setTab] = useState("compose");

  const loadThread = async () => {
    const { data } = await api.get(base);
    setThread(data || { messages: [] });
  };

  useEffect(() => {
    loadThread();
    // eslint-disable-next-line
  }, []);

  const hasThread = (thread.messages || []).length > 0;

  const getStrategy = async () => {
    setLoadingStrategy(true);
    try {
      const { data } = await api.post(`${base}/strategy`);
      setStrategy(data);
      if (data.recommended_tone && TONES.includes(data.recommended_tone)) setTone(data.recommended_tone);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setLoadingStrategy(false);
    }
  };

  const suggestContact = async () => {
    try {
      const { data } = await api.post(`${base}/contact`);
      if (data.found_emails?.length) setToEmail(data.found_emails[0]);
      else if (data.suggested_email) setToEmail(data.suggested_email);
      if (data.recommended_subject) setSubject(data.recommended_subject);
      toast.success("Suggested a contact & subject");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const compose = async (followUp = false) => {
    setComposing(true);
    try {
      const { data } = await api.post(`${base}/compose`, { tone, custom_instructions: custom, follow_up: followUp });
      setSubject(data.subject || "");
      setBodyText(data.body_text || "");
      setBodyHtml(data.body_html || "");
      toast.success("Draft ready — review before sending");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setComposing(false);
    }
  };

  const send = async () => {
    if (!toEmail || !subject || !bodyText) {
      toast.error("Recipient, subject and body are required.");
      return;
    }
    setSending(true);
    try {
      const { data } = await api.post(`${base}/send`, {
        to_email: toEmail, subject, body_text: bodyText, body_html: bodyHtml,
      });
      if (data.result?.ok) toast.success("Email sent to vendor");
      else toast.error(data.message || "Email could not be sent (check SendGrid sender verification).");
      setBodyText("");
      await loadThread();
      setTab("thread");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setSending(false);
    }
  };

  const parseReply = async () => {
    if (!replyBody.trim()) return;
    setParsing(true);
    try {
      const { data } = await api.post(`${base}/reply`, { subject: replySubject, body: replyBody });
      setParsed(data.parsed);
      await loadThread();
      toast.success("Vendor reply parsed");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setParsing(false);
    }
  };

  const applyOffer = async () => {
    if (parsed?.price_per_unit == null) {
      toast.error("No price found to apply.");
      return;
    }
    try {
      await api.post(`${base}/apply-offer`, {
        price_per_unit: parsed.price_per_unit,
        lead_time_days: parsed.lead_time_days,
        payment_terms: parsed.payment_terms,
        shipping_terms: parsed.shipping_terms,
      });
      toast.success("Offer captured from vendor email");
      setParsed(null);
      setReplyBody("");
      onOfferApplied?.();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const getSummary = async () => {
    try {
      const { data } = await api.post(`${base}/summary`);
      setSummary(data);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const TABS = [
    { key: "compose", label: "Compose", icon: Mail },
    { key: "thread", label: `Thread${hasThread ? ` (${thread.messages.length})` : ""}`, icon: MessageSquareText },
    { key: "reply", label: "Log reply", icon: ClipboardCheck },
  ];

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 backdrop-blur-sm p-4 sm:p-8"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        data-testid="outreach-modal"
      >
        <motion.div
          className="glass-strong rounded-2xl w-full max-w-3xl relative border border-white/10 my-4"
          initial={{ opacity: 0, y: 24, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 24 }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between p-5 border-b hairline">
            <div>
              <div className="text-[10px] font-mono tracking-widest text-primary/80 uppercase">Email outreach</div>
              <h3 className="font-display text-xl font-bold">{vendor.name}</h3>
            </div>
            <button onClick={onClose} className="text-white/40 hover:text-white transition-colors" data-testid="outreach-close">
              <X size={20} />
            </button>
          </div>

          <div className="flex gap-1 px-5 pt-4">
            {TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                data-testid={`outreach-tab-${t.key}`}
                className={`flex items-center gap-2 px-4 py-2 rounded-t-lg text-sm transition-colors ${
                  tab === t.key ? "bg-white/8 text-primary" : "text-white/50 hover:text-white"
                }`}
              >
                <t.icon size={14} /> {t.label}
              </button>
            ))}
          </div>

          <div className="p-5 max-h-[65vh] overflow-y-auto">
            {tab === "compose" && (
              <div className="space-y-4">
                <div className="flex flex-wrap gap-2">
                  <Button variant="ghost" size="sm" onClick={getStrategy} disabled={loadingStrategy} data-testid="outreach-strategy-btn">
                    {loadingStrategy ? <Spinner /> : <Lightbulb size={14} />} AI strategy
                  </Button>
                  <Button variant="ghost" size="sm" onClick={suggestContact} data-testid="outreach-contact-btn">
                    <Wand2 size={14} /> Suggest contact
                  </Button>
                </div>

                {strategy && (
                  <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 text-sm space-y-2">
                    <div className="text-primary font-medium flex items-center gap-2"><Lightbulb size={14} /> Suggested approach</div>
                    <p className="text-white/70"><span className="text-white/40">Hook:</span> {strategy.opening_hook}</p>
                    <p className="text-white/70"><span className="text-white/40">Subject:</span> {strategy.subject_approach}</p>
                    {strategy.value_props?.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 pt-1">
                        {strategy.value_props.map((v, i) => <Badge key={i}>{v}</Badge>)}
                      </div>
                    )}
                    <p className="text-[11px] text-white/40">Recommended tone: {strategy.recommended_tone}</p>
                  </div>
                )}

                <div className="flex flex-wrap gap-3 items-end">
                  <div>
                    <span className="block mb-2 text-xs tracking-[0.2em] uppercase text-white/50">Tone</span>
                    <select value={tone} onChange={(e) => setTone(e.target.value)} data-testid="outreach-tone"
                      className="bg-black/40 border border-white/12 rounded-xl px-4 py-3 text-white outline-none focus:border-primary/60">
                      {TONES.map((t) => <option key={t} value={t} className="bg-void">{t}</option>)}
                    </select>
                  </div>
                  <div className="flex-1 min-w-[200px]">
                    <Input label="Custom instructions (optional)" value={custom} onChange={(e) => setCustom(e.target.value)}
                      placeholder="e.g. emphasize bulk discount" data-testid="outreach-custom" />
                  </div>
                  <Button onClick={() => compose(hasThread)} disabled={composing} data-testid="outreach-compose-btn">
                    {composing ? <Spinner /> : <Sparkles size={16} />} {hasThread ? "Draft follow-up" : "AI draft"}
                  </Button>
                </div>

                <Input label="To" type="email" value={toEmail} onChange={(e) => setToEmail(e.target.value)} data-testid="outreach-to" placeholder="vendor@company.com" />
                <Input label="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} data-testid="outreach-subject" />
                <Textarea label="Body" rows={10} value={bodyText} onChange={(e) => setBodyText(e.target.value)} data-testid="outreach-body" className="min-h-[220px]" />

                <div className="flex justify-end">
                  <Button onClick={send} disabled={sending} data-testid="outreach-send-btn">
                    {sending ? <Spinner /> : <Send size={16} />} Send email
                  </Button>
                </div>
              </div>
            )}

            {tab === "thread" && (
              <div className="space-y-4">
                <div className="flex justify-end">
                  <Button variant="ghost" size="sm" onClick={getSummary} data-testid="outreach-summary-btn">
                    <Sparkles size={14} /> AI summary & next step
                  </Button>
                </div>
                {summary && (
                  <div className="rounded-xl border border-secondary/20 bg-secondary/5 p-4 text-sm space-y-1">
                    <p className="text-white/80">{summary.summary}</p>
                    <p className="text-secondary"><span className="text-white/40">Next:</span> {summary.next_action}</p>
                    <div className="flex gap-2 pt-1">
                      <Badge>sentiment: {summary.vendor_sentiment}</Badge>
                      <Badge>urgency: {summary.urgency}</Badge>
                    </div>
                  </div>
                )}
                {hasThread ? (
                  thread.messages.map((m, i) => (
                    <div key={m.id || i} className={`rounded-xl p-4 border ${m.direction === "outbound" ? "border-primary/20 bg-primary/5 ml-8" : "border-white/10 bg-white/5 mr-8"}`}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[10px] font-mono uppercase tracking-wider text-white/50">
                          {m.direction === "outbound" ? "→ Sent" : "← Vendor"} {m.delivered === false && "(not delivered)"}
                        </span>
                        <span className="text-[10px] text-white/30">{(m.at || "").slice(0, 16).replace("T", " ")}</span>
                      </div>
                      {m.subject && <div className="text-sm font-medium mb-1">{m.subject}</div>}
                      <p className="text-sm text-white/70 whitespace-pre-wrap">{m.body_text}</p>
                      {m.parsed?.price_per_unit != null && (
                        <div className="mt-2 text-xs text-secondary">Parsed price: {currency} {m.parsed.price_per_unit}/unit</div>
                      )}
                    </div>
                  ))
                ) : (
                  <p className="text-white/40 text-sm text-center py-8">No emails yet. Compose the first outreach.</p>
                )}
              </div>
            )}

            {tab === "reply" && (
              <div className="space-y-4">
                <p className="text-sm text-white/50">Paste the vendor's email reply. NegoBuy extracts pricing & terms — it never guesses missing values.</p>
                <Input label="Reply subject (optional)" value={replySubject} onChange={(e) => setReplySubject(e.target.value)} data-testid="reply-subject" />
                <Textarea label="Vendor reply" rows={8} value={replyBody} onChange={(e) => setReplyBody(e.target.value)} data-testid="reply-body" className="min-h-[180px]" />
                <div className="flex justify-end">
                  <Button onClick={parseReply} disabled={parsing} data-testid="reply-parse-btn">
                    {parsing ? <Spinner /> : <Wand2 size={16} />} Extract terms
                  </Button>
                </div>

                {parsed && (
                  <div className="rounded-xl border border-white/10 bg-white/5 p-4 text-sm space-y-2" data-testid="parsed-terms">
                    <div className="grid grid-cols-2 gap-2">
                      <Field label="Price / unit" value={parsed.price_per_unit != null ? `${parsed.currency || currency} ${parsed.price_per_unit}` : "—"} />
                      <Field label="MOQ" value={parsed.moq ?? "—"} />
                      <Field label="Lead time" value={parsed.lead_time_days ? `${parsed.lead_time_days} days` : "—"} />
                      <Field label="Payment" value={parsed.payment_terms || "—"} />
                      <Field label="Shipping" value={parsed.shipping_terms || "—"} />
                      <Field label="Valid till" value={parsed.validity_date || "—"} />
                    </div>
                    {parsed.notes && <p className="text-white/50 text-xs pt-1 border-t hairline">{parsed.notes}</p>}
                    <div className="flex items-center justify-between pt-2">
                      <Badge>confidence {Math.round((parsed.confidence || 0) * 100)}%</Badge>
                      <Button size="sm" variant="success" onClick={applyOffer} disabled={parsed.price_per_unit == null} data-testid="apply-offer-btn">
                        <ClipboardCheck size={14} /> Save as offer
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

function Field({ label, value }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-white/40">{label}</div>
      <div className="text-white/85 font-medium">{value}</div>
    </div>
  );
}

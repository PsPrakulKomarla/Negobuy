import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Check, ArrowLeft, Sparkles, Info, Download, CheckCircle2, X } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { Button, Card, Spinner, Badge } from "../components/ui";
import { useAuth } from "../context/AuthContext";

export default function Pricing({ embedded = false }) {
  const { user, refreshUser } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(null);
  const [paid, setPaid] = useState(null);
  const [downloading, setDownloading] = useState(false);

  const downloadReceipt = async (orderId) => {
    setDownloading(true);
    try {
      const res = await api.get(`/billing/receipt/${orderId}`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `${paid?.invoice_no || "NegoBuy-invoice"}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      toast.error("Could not download the invoice. Please try again.");
    } finally {
      setDownloading(false);
    }
  };

  const sym = (c) => (c === "INR" ? "₹" : c === "USD" ? "$" : "");
  const discountPct = (orig, price) => Math.round(((orig - price) / orig) * 100);

  useEffect(() => {
    api
      .get("/billing/plans")
      .then((r) => setData(r.data))
      .finally(() => setLoading(false));
  }, []);

  const loadRazorpay = () =>
    new Promise((resolve) => {
      if (window.Razorpay) return resolve(true);
      const s = document.createElement("script");
      s.src = "https://checkout.razorpay.com/v1/checkout.js";
      s.onload = () => resolve(true);
      s.onerror = () => resolve(false);
      document.body.appendChild(s);
    });

  const checkout = async (planId) => {
    if (!user) {
      toast.error("Please sign in to continue.");
      return;
    }
    if (planId === "free") {
      toast.success("You're on the free Explorer plan — start a mission anytime.");
      return;
    }
    setProcessing(planId);
    try {
      const { data: order } = await api.post(`/billing/orders`, { plan_id: planId });
      if (order.status === "NOT_CONFIGURED") {
        toast.info(order.message || "Payments not configured yet.");
        return;
      }
      const ok = await loadRazorpay();
      if (!ok) {
        toast.error("Could not load the Razorpay checkout. Check your connection.");
        return;
      }
      const rzp = new window.Razorpay({
        key: order.key_id,
        order_id: order.order.id,
        amount: order.order.amount,
        currency: order.order.currency,
        name: "NegoBuy",
        description: `${order.plan.name} — monthly`,
        prefill: { name: user?.name || "", email: user?.email || "" },
        theme: { color: "#0f9d6a" },
        handler: async (resp) => {
          try {
            const { data: v } = await api.post(`/billing/verify`, {
              razorpay_order_id: resp.razorpay_order_id,
              razorpay_payment_id: resp.razorpay_payment_id,
              razorpay_signature: resp.razorpay_signature,
            });
            toast.success("Payment verified — your plan is now active!");
            refreshUser?.();
            setPaid({
              order_id: v.order_id || resp.razorpay_order_id,
              invoice_no: v.invoice_no,
              planName: order.plan.name,
            });
          } catch (e) {
            toast.error("Payment could not be verified. If charged, contact support.");
          }
        },
        modal: { ondismiss: () => setProcessing(null) },
      });
      rzp.on("payment.failed", (r) => {
        toast.error(r?.error?.description || "Payment failed. Please try again.");
      });
      rzp.open();
    } catch (e) {
      toast.error(e?.response?.status === 401 ? "Please sign in to continue." : "Could not start checkout.");
    } finally {
      setProcessing(null);
    }
  };

  const content = (
    <div className={embedded ? "p-6 lg:p-10 max-w-6xl mx-auto" : "max-w-6xl mx-auto px-5 sm:px-8 pt-32 pb-24"}>
      {paid && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/75 backdrop-blur-sm p-4" data-testid="payment-success-modal">
          <motion.div
            initial={{ opacity: 0, scale: 0.94, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            className="w-full max-w-md glass rounded-3xl p-8 relative border border-secondary/30"
          >
            <button
              onClick={() => setPaid(null)}
              className="absolute top-4 right-4 text-white/40 hover:text-white transition-colors"
              data-testid="payment-success-close"
            >
              <X size={18} />
            </button>
            <div className="w-14 h-14 rounded-full bg-secondary/15 border border-secondary/40 flex items-center justify-center mb-5">
              <CheckCircle2 size={28} className="text-secondary" />
            </div>
            <h3 className="font-display text-2xl font-bold mb-1">Payment successful</h3>
            <p className="text-white/55 text-sm mb-1">
              Your <b className="text-white">{paid.planName}</b> plan is now active.
            </p>
            {paid.invoice_no && (
              <p className="text-white/40 text-xs font-mono mb-6" data-testid="payment-invoice-no">
                Invoice {paid.invoice_no}
              </p>
            )}
            <Button
              className="w-full mb-3"
              onClick={() => downloadReceipt(paid.order_id)}
              disabled={downloading}
              data-testid="download-invoice-btn"
            >
              {downloading ? <Spinner className="w-4 h-4" /> : <Download size={16} />}
              Download GST invoice (PDF)
            </Button>
            <Button variant="ghost" className="w-full" onClick={() => setPaid(null)} data-testid="payment-success-done">
              Done
            </Button>
          </motion.div>
        </div>
      )}
      {!embedded && (
        <Link to="/" className="inline-flex items-center gap-2 text-white/40 hover:text-white text-sm mb-8 transition-colors">
          <ArrowLeft size={15} /> Home
        </Link>
      )}

      <div className="text-center mb-14">
        <div className="text-xs tracking-[0.3em] uppercase text-primary/80 font-mono mb-3">
          Commercial plans
        </div>
        <h1 className="font-display text-4xl lg:text-5xl font-bold tracking-tighter mb-4">
          Pay per mission, or run continuously.
        </h1>
        <p className="text-white/55 max-w-xl mx-auto">
          Start free. Buy a single procurement mission, or subscribe for a
          continuously operating AI Buyer.
        </p>
        {data && !data.payment_configured && (
          <div className="inline-flex items-center gap-2 mt-6 text-xs text-yellow-300/80 bg-yellow-400/5 border border-yellow-400/20 rounded-full px-4 py-2">
            <Info size={13} /> Live checkout requires payment configuration — plans are preview-ready.
          </div>
        )}
      </div>

      {loading ? (
        <div className="py-20 flex justify-center">
          <Spinner className="w-8 h-8" />
        </div>
      ) : (
        <div className="grid md:grid-cols-3 gap-6">
          {data?.plans?.map((plan, i) => {
            const highlight = plan.id === "pro";
            const current = user?.plan === plan.id;
            return (
              <motion.div
                key={plan.id}
                initial={{ opacity: 0, y: 24 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: i * 0.08 }}
              >
                <Card
                  className={`p-7 h-full flex flex-col relative ${highlight ? "border-primary/40" : ""}`}
                  data-testid={`plan-${plan.id}`}
                >
                  {highlight && (
                    <div className="absolute -top-3 left-7">
                      <Badge className="bg-primary/20 border-primary/40 text-primary">
                        <Sparkles size={11} className="mr-1" /> Most powerful
                      </Badge>
                    </div>
                  )}
                  <div className="mb-6">
                    <h3 className="font-display text-2xl font-bold">{plan.name}</h3>
                    <div className="mt-3 flex items-baseline gap-2 flex-wrap">
                      {plan.price === 0 ? (
                        <span className="font-display text-3xl font-bold">₹0<span className="text-white/40 text-sm font-normal"> /forever</span></span>
                      ) : plan.price == null ? (
                        <span className="font-display text-2xl font-bold text-white/70">Custom</span>
                      ) : (
                        <>
                          {plan.original_price ? (
                            <span className="font-display text-lg font-semibold text-white/30 line-through" data-testid={`plan-original-${plan.id}`}>
                              {sym(plan.currency)}{plan.original_price}
                            </span>
                          ) : null}
                          <span className="font-display text-3xl font-bold" data-testid={`plan-price-${plan.id}`}>{sym(plan.currency)}{plan.price}</span>
                          {plan.interval && <span className="text-white/40 text-sm">/{plan.interval}</span>}
                        </>
                      )}
                    </div>
                    {plan.original_price && plan.price ? (
                      <div className="mt-2">
                        <Badge className="bg-secondary/15 border-secondary/40 text-secondary" data-testid={`plan-discount-${plan.id}`}>
                          {discountPct(plan.original_price, plan.price)}% OFF · save {sym(plan.currency)}{plan.original_price - plan.price}/{plan.interval}
                        </Badge>
                      </div>
                    ) : null}
                    <div className="text-[11px] font-mono uppercase tracking-wider text-white/35 mt-2">
                      {plan.type.replace("_", " ")}
                    </div>
                  </div>

                  <ul className="space-y-3 mb-7 flex-1">
                    {plan.features.map((f) => (
                      <li key={f} className="flex items-start gap-2.5 text-sm text-white/70">
                        <Check size={16} className="text-secondary shrink-0 mt-0.5" />
                        {f}
                      </li>
                    ))}
                  </ul>

                  {current ? (
                    <Button variant="secondary" disabled className="w-full">
                      Current plan
                    </Button>
                  ) : (
                    <Button
                      variant={highlight ? "primary" : "secondary"}
                      className="w-full"
                      onClick={() => checkout(plan.id)}
                      disabled={processing === plan.id}
                      data-testid={`plan-cta-${plan.id}`}
                    >
                      {processing === plan.id ? (
                        <Spinner className="w-4 h-4" />
                      ) : plan.id === "free" ? (
                        "Get started"
                      ) : (
                        "Choose plan"
                      )}
                    </Button>
                  )}
                </Card>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );

  if (embedded) return content;
  return <div className="min-h-screen bg-void">{content}</div>;
}

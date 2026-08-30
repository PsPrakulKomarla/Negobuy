import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Check, ArrowLeft, Sparkles, Info } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { Button, Card, Spinner, Badge } from "../components/ui";
import { useAuth } from "../context/AuthContext";

export default function Pricing({ embedded = false }) {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get("/billing/plans")
      .then((r) => setData(r.data))
      .finally(() => setLoading(false));
  }, []);

  const checkout = async (planId) => {
    try {
      const { data } = await api.post(`/billing/checkout/${planId}`);
      if (data.status === "not_configured") {
        toast.info(data.message);
      }
    } catch (e) {
      toast.error("Please sign in to continue.");
    }
  };

  const content = (
    <div className={embedded ? "p-6 lg:p-10 max-w-6xl mx-auto" : "max-w-6xl mx-auto px-5 sm:px-8 pt-32 pb-24"}>
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
                    <div className="mt-3 flex items-baseline gap-1">
                      {plan.price === 0 ? (
                        <span className="font-display text-3xl font-bold">Free</span>
                      ) : plan.price == null ? (
                        <span className="font-display text-2xl font-bold text-white/70">Custom</span>
                      ) : (
                        <>
                          <span className="font-display text-3xl font-bold">{plan.currency === "INR" ? "₹" : "$"}{plan.price}</span>
                          {plan.interval && <span className="text-white/40 text-sm">/{plan.interval}</span>}
                        </>
                      )}
                    </div>
                    <div className="text-[11px] font-mono uppercase tracking-wider text-white/35 mt-1">
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
                      data-testid={`plan-cta-${plan.id}`}
                    >
                      {plan.id === "free" ? "Get started" : "Choose plan"}
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

import React, { useState, useEffect, useCallback } from "react";
import { ClipboardList, Package, CheckCircle2, Sparkles, Send } from "lucide-react";
import api from "../lib/api";
import { Card, Badge, Spinner, motion, fadeUp } from "../components/ui";

export default function Orders() {
  const [orders, setOrders] = useState(null);

  const load = useCallback(async () => {
    try { const { data } = await api.get("/telegram/orders"); setOrders(data); }
    catch { setOrders([]); }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [load]);

  const totalValue = (orders || []).reduce((s, o) => s + (o.total || 0), 0);

  return (
    <div className="max-w-5xl mx-auto px-5 sm:px-8 py-8">
      <motion.div {...fadeUp} className="mb-8">
        <div className="flex items-center gap-2 text-xs tracking-[0.3em] uppercase text-primary/80 font-mono mb-2">
          <ClipboardList size={14} /> Orders
        </div>
        <h1 className="font-display text-3xl sm:text-4xl font-bold tracking-tight">Placed orders</h1>
        <p className="text-white/50 mt-2 max-w-2xl">
          Every order you accepted after an AI negotiation. Confirmations were sent to each vendor on Telegram.
        </p>
      </motion.div>

      {orders === null ? (
        <div className="flex justify-center py-20"><Spinner className="w-7 h-7" /></div>
      ) : orders.length === 0 ? (
        <Card className="p-10 text-center border border-white/10" data-testid="orders-empty">
          <Package size={28} className="text-white/30 mx-auto mb-3" />
          <p className="text-white/60">No orders yet.</p>
          <p className="text-white/40 text-sm mt-1">
            Negotiate in Auto-Sourcing or Telegram AI, then accept a vendor's price to place an order.
          </p>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 mb-6">
            <Card className="p-4 border border-white/10">
              <div className="text-[10px] uppercase tracking-wider text-white/40 font-mono">Orders</div>
              <div className="text-2xl font-bold" data-testid="orders-count">{orders.length}</div>
            </Card>
            <Card className="p-4 border border-secondary/20 bg-secondary/5">
              <div className="text-[10px] uppercase tracking-wider text-white/40 font-mono">Total value</div>
              <div className="text-2xl font-bold text-secondary">₹ {totalValue.toLocaleString()}</div>
            </Card>
          </div>

          <div className="space-y-3">
            {orders.map((o) => (
              <Card key={o.id} className="p-5 border border-white/10" data-testid={`order-${o.id}`}>
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-display font-bold truncate">{o.vendor}</span>
                      <Badge className="text-secondary border-secondary/30">
                        <CheckCircle2 size={11} className="mr-1" /> {o.status}
                      </Badge>
                      {o.source?.startsWith("sourcing:") && (
                        <Badge className="text-primary/80 border-primary/30"><Sparkles size={10} className="mr-1" /> sourcing</Badge>
                      )}
                    </div>
                    <div className="text-sm text-white/60 mt-1">{o.material}</div>
                    <div className="flex items-center gap-3 text-xs text-white/45 mt-1 flex-wrap">
                      {o.quantity && <span>{o.quantity} {o.unit}</span>}
                      <span className="flex items-center gap-1"><Send size={11} /> {o.vendor_phone}</span>
                      {o.accepted_at && <span>{new Date(o.accepted_at).toLocaleString()}</span>}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-[10px] uppercase tracking-wider text-white/40 font-mono">Unit price</div>
                    <div className="text-lg font-bold text-yellow-300">{o.currency} {o.price}{o.unit ? `/${o.unit}` : ""}</div>
                    {o.total != null && (
                      <div className="text-sm text-white/60 mt-1">Total <b className="text-white">{o.currency} {o.total.toLocaleString()}</b></div>
                    )}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

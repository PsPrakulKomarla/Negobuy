// Scripted, choreographed marketing narrative. Each entry maps to a camera scene
// and to state-driven 3D visuals (discovering / filtering / verifying / negotiating / ...).
// The numbers below are an illustrative walkthrough — not live data.

export const STORY = [
  {
    kind: "enter",
    label: "NegoBuy // Command Center",
    title: "Your AI Buyer for the real world.",
    body:
      "Step inside the procurement command center. NegoBuy is an AI operator that runs the entire buying journey — from a plain-language request to a decision you approve.",
  },
  {
    kind: "request",
    label: "01 · The Request",
    title: "Describe what you need to buy.",
    request:
      "I need 500 ergonomic office chairs under ₹5 lakh, delivered to Bangalore within 10 days.",
    shards: ["500 UNITS", "ERGONOMIC", "₹5,00,000 MAX", "BANGALORE", "10 DAYS"],
    body: "The request becomes a structured procurement mission.",
  },
  {
    kind: "discovery",
    label: "02 · Market Discovery",
    title: "Searching the entire market.",
    body: "Real discovery scans the market, deduplicates and narrows to what actually fits.",
    funnel: [
      { k: "Candidates found", v: "1,247" },
      { k: "After dedup", v: "384" },
      { k: "Relevant", v: "87" },
      { k: "Shortlisted", v: "23" },
      { k: "Verified suppliers", v: "10" },
    ],
  },
  {
    kind: "intel",
    label: "03 · Supplier Intelligence",
    title: "Investigating each supplier.",
    body: "Every strong candidate becomes an intelligence profile — scored on real signals.",
    stats: [
      { k: "Match", v: "96%" },
      { k: "Reliability", v: "91%" },
      { k: "Delivery", v: "8 days" },
      { k: "Warranty", v: "3 years" },
      { k: "Risk", v: "Low" },
    ],
  },
  {
    kind: "verify",
    label: "04 · Verification",
    title: "Verifying what's real.",
    body: "Information flows through the AI. Nothing is fabricated — only marked verified or uncertain.",
    checks: [
      { k: "Website", s: "verified" },
      { k: "Business information", s: "verified" },
      { k: "Product match", s: "verified" },
      { k: "Contact", s: "verified" },
      { k: "Evidence", s: "verified" },
      { k: "Reputation", s: "review" },
      { k: "Delivery capability", s: "verified" },
    ],
  },
  {
    kind: "negotiation",
    label: "05 · Negotiation",
    title: "Not an IVR. A negotiator.",
    body: "NegoBuy holds a natural conversation and negotiates inside your authority limits.",
    terms: [
      { k: "Delivery", v: "10 days" },
      { k: "Warranty", v: "3 years" },
      { k: "Payment", v: "30% advance" },
    ],
  },
  {
    kind: "warroom",
    label: "06 · Multi-Vendor",
    title: "Every vendor competes.",
    body: "Price alone never decides. Delivery, warranty, reliability and risk all count.",
    vendors: [
      { k: "Supplier A", v: "₹875", lead: false },
      { k: "Supplier B", v: "₹820", lead: true },
      { k: "Supplier C", v: "₹910", lead: false },
      { k: "Supplier D", v: "₹860", lead: false },
    ],
  },
  {
    kind: "landed",
    label: "07 · True Landed Cost",
    title: "The real number.",
    body: "The lowest sticker price is rarely the lowest true cost.",
    cost: [
      { k: "Product price", v: "₹4,10,000", assumption: false },
      { k: "Tax", v: "₹49,200", assumption: false },
      { k: "Shipping", v: "₹9,800", assumption: false },
      { k: "Handling fees", v: "₹3,000", assumption: true },
    ],
    total: "₹4,72,000",
  },
  {
    kind: "recommend",
    label: "08 · Recommendation",
    title: "The strongest overall option.",
    body: "Best combination of landed cost, delivery reliability, warranty and vendor confidence.",
    stats: [
      { k: "Total landed cost", v: "₹4,72,000" },
      { k: "Estimated savings", v: "₹28,000" },
      { k: "Delivery", v: "8 days" },
      { k: "Warranty", v: "3 years" },
      { k: "Risk", v: "Low" },
      { k: "AI confidence", v: "94%" },
    ],
  },
  {
    kind: "decision",
    label: "09 · Human Decision",
    title: "AI recommends. You decide.",
    body: "Nothing material happens without your explicit approval.",
    actions: ["Approve procurement", "Negotiate further", "Reject"],
  },
  {
    kind: "complete",
    label: "10 · Mission Complete",
    title: "Procurement complete.",
    body: "The mission is sealed and stored in your procurement history.",
    summary: [
      { k: "Final supplier", v: "Supplier B" },
      { k: "Final price", v: "₹4,72,000" },
      { k: "Savings", v: "₹28,000" },
      { k: "Delivery", v: "8 days" },
      { k: "Warranty", v: "3 years" },
    ],
  },
];

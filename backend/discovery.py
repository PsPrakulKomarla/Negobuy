"""Vendor discovery — real web search (Tavily) behind a swappable provider, plus scoring/ranking."""
import os
import re
from urllib.parse import urlparse
import httpx

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+?\d[\d ()-]{7,}\d)")

DEFAULT_WEIGHTS = {
    "category_match": 0.35,
    "geographic_suitability": 0.20,
    "credibility": 0.25,
    "evidence_quality": 0.20,
}


def search_configured() -> bool:
    # Tavily supports keyless exploration, so discovery is always available (rate-limited without key).
    return True


def has_search_key() -> bool:
    return bool(os.environ.get("TAVILY_API_KEY"))


async def web_search(query: str, max_results: int = 15) -> list[dict]:
    """Real web search via Tavily. Uses keyless mode when no key is configured."""
    api_key = os.environ.get("TAVILY_API_KEY")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        headers["X-Tavily-Access-Mode"] = "keyless"
    payload = {
        "query": query, "search_depth": "basic", "topic": "general",
        "max_results": max_results, "include_answer": False, "include_raw_content": False,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
        r = await client.post("https://api.tavily.com/search", headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    hits = []
    for item in data.get("results", []):
        url = item.get("url")
        if not url:
            continue
        text = f"{item.get('title','')} {item.get('content','')}"
        hits.append({
            "title": item.get("title", ""),
            "url": url,
            "snippet": item.get("content", ""),
            "score": item.get("score"),
            "domain": urlparse(url).netloc.lower().removeprefix("www."),
            "emails": sorted(set(EMAIL_RE.findall(text))),
            "phones": sorted(set(PHONE_RE.findall(text))),
        })
    return hits


def build_query(mission: dict) -> str:
    parts = []
    if mission.get("category"):
        parts.append(mission["category"])
    parts.append("suppliers OR distributors OR manufacturers OR wholesalers")
    if mission.get("delivery_location"):
        parts.append(mission["delivery_location"])
    return " ".join(parts)


def dedupe(hits: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for h in hits:
        key = h["domain"]
        if key and key not in seen:
            seen.add(key)
            out.append(h)
    return out


def weighted_score(scores: dict, weights: dict = None) -> float:
    weights = weights or DEFAULT_WEIGHTS
    total = 0.0
    for k, w in weights.items():
        total += (scores.get(k, 0) or 0) * w
    return round(total, 1)

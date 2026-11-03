"""Verify the voice_call offer mirror is flagged and never a purchase."""
import os
import re
from pathlib import Path

import requests
from dotenv import dotenv_values

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE}/api"
MISSION_ID = "b983bb2f74bd44f29685978e16251d93"


def _client():
    c = Path("/app/memory/test_credentials.md").read_text(encoding="utf-8")
    email = re.search(r'(?im)^\s*[-*]\s*Email\s*:\s*`([^`]+)`', c).group(1)
    pwd = re.search(r'(?im)^\s*[-*]\s*Password\s*:\s*`([^`]+)`', c).group(1)
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=60)
    r.raise_for_status()
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


def test_voice_offer_flagged_out_of_authority():
    s = _client()
    calls = s.get(f"{API}/voice/console/history", params={"mission_id": MISSION_ID},
                  timeout=60).json()
    done = [c for c in calls if c["status"] == "SIMULATED_COMPLETE"]
    assert done, "no completed simulated calls to check"
    offers = s.get(f"{API}/missions/{MISSION_ID}/offers", timeout=60).json()
    offers = offers if isinstance(offers, list) else offers.get("offers", [])
    vc = [o for o in offers if o.get("source") == "voice_call"]
    print("voice_call offers:", [(o.get("negotiated_price"), o.get("within_authority"),
                                 o.get("status"), o.get("simulation")) for o in vc])
    assert len(vc) <= 1, "more than one voice_call offer per vendor (dedup broken)"
    for o in vc:
        assert o.get("simulation") is True
        mx = o.get("max_authorized_price")
        if mx is not None and o.get("negotiated_price") is not None:
            expected = float(o["negotiated_price"]) <= float(mx)
            assert o["within_authority"] is expected, o
            assert o["status"] == ("OPEN" if expected else "OUT_OF_AUTHORITY"), o
        assert "_id" not in o


def test_mission_not_ordered():
    s = _client()
    m = s.get(f"{API}/missions/{MISSION_ID}", timeout=60).json()
    print("mission status:", m.get("status"), "stage:", m.get("stage"))
    assert m.get("status") not in ("ORDERED", "PURCHASED", "COMPLETED")

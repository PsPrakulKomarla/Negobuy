"""Iteration 18 — Two default tile vendors (SLV + Ananta both +919945842205),
unique ids, launch dedup gate, campaign endpoints. No live Telegram."""
import os
import re
import uuid

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
ADMIN = {"email": "admin@negobuy.ai", "password": "NegoBuy@2026"}
DEFAULT_PHONE = "+919945842205"


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=60)
    assert r.status_code == 200, r.text[:300]
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


@pytest.fixture(scope="session")
def tiles_campaign(client):
    r = client.post(f"{BASE_URL}/api/sourcing/discover", json={
        "material": "Kajaria vitrified floor tiles",
        "specs": "600x600 glazed",
        "quantity": 4000, "unit": "sq ft",
        "target_price": 400, "max_price": 450, "currency": "INR",
        "location": "Bengaluru", "max_vendors": 10}, timeout=300)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
    return r.json()


class TestDefaultTileVendors:
    def test_status_discovered(self, tiles_campaign):
        assert tiles_campaign["status"] == "DISCOVERED"
        assert "id" in tiles_campaign

    def test_both_defaults_present(self, tiles_campaign):
        cands = tiles_campaign["candidates"]
        names = [c["name"] for c in cands]
        assert "SLV Ceramics" in names, names
        assert "Ananta Ceramics" in names, names

    def test_defaults_have_phone_and_default_flag(self, tiles_campaign):
        cands = tiles_campaign["candidates"]
        defaults = [c for c in cands if c["name"] in ("SLV Ceramics", "Ananta Ceramics")]
        assert len(defaults) == 2
        for c in defaults:
            assert c["phone"] == DEFAULT_PHONE
            assert c.get("default") is True
            assert "id" in c and c["id"]

    def test_default_ids_are_unique(self, tiles_campaign):
        cands = tiles_campaign["candidates"]
        defaults = [c for c in cands if c["name"] in ("SLV Ceramics", "Ananta Ceramics")]
        ids = [c["id"] for c in defaults]
        assert len(set(ids)) == 2, f"duplicate default ids: {ids}"

    def test_all_candidates_have_unique_ids(self, tiles_campaign):
        cands = tiles_campaign["candidates"]
        ids = [c.get("id") for c in cands]
        assert all(ids), "some candidate missing id"
        assert len(set(ids)) == len(ids), f"duplicate ids: {ids}"

    def test_no_mongo_id_leak(self, tiles_campaign):
        assert "_id" not in tiles_campaign

    def test_non_tile_material_no_defaults(self, client):
        r = client.post(f"{BASE_URL}/api/sourcing/discover", json={
            "material": "steel rebar TMT bars",
            "target_price": 55, "max_price": 65, "currency": "INR",
            "location": "Chennai", "max_vendors": 5}, timeout=300)
        # Could 200 or 502 (no web results). Focus on defaults only when 200.
        if r.status_code == 502:
            pytest.skip("web search returned no results for steel")
        assert r.status_code == 200, r.text[:400]
        cands = r.json()["candidates"]
        assert all(c["name"] not in ("SLV Ceramics", "Ananta Ceramics") for c in cands)
        assert all(not c.get("default") for c in cands)
        assert all(c.get("phone") != DEFAULT_PHONE for c in cands)


class TestLaunchTelegramGate:
    def test_launch_without_telegram_link_returns_400(self, client, tiles_campaign):
        r = client.post(
            f"{BASE_URL}/api/sourcing/campaigns/{tiles_campaign['id']}/launch",
            json={}, timeout=60)
        assert r.status_code == 400, f"{r.status_code}: {r.text[:300]}"
        assert "Link your Telegram" in r.json()["detail"]

    def test_launch_unknown_campaign_404(self, client):
        r = client.post(
            f"{BASE_URL}/api/sourcing/campaigns/{uuid.uuid4().hex}/launch",
            json={}, timeout=60)
        # Either 404 (campaign check first) or 400 (tg gate first) — code checks
        # campaign first, so expect 404.
        assert r.status_code == 404, f"{r.status_code}: {r.text[:300]}"

    def test_launch_requires_auth(self, tiles_campaign):
        r = requests.post(
            f"{BASE_URL}/api/sourcing/campaigns/{tiles_campaign['id']}/launch",
            json={}, timeout=60)
        assert r.status_code in (401, 403)


class TestCampaignEndpoints:
    def test_list_campaigns(self, client, tiles_campaign):
        r = client.get(f"{BASE_URL}/api/sourcing/campaigns", timeout=60)
        assert r.status_code == 200
        camps = r.json()
        assert isinstance(camps, list)
        assert any(c["id"] == tiles_campaign["id"] for c in camps)
        assert '"_id"' not in r.text

    def test_get_campaign(self, client, tiles_campaign):
        r = client.get(f"{BASE_URL}/api/sourcing/campaigns/{tiles_campaign['id']}", timeout=60)
        assert r.status_code == 200
        camp = r.json()
        assert camp["id"] == tiles_campaign["id"]
        assert "candidates" in camp
        assert "best" in camp  # None when no deals
        assert '"_id"' not in r.text

    def test_get_campaign_404(self, client):
        r = client.get(f"{BASE_URL}/api/sourcing/campaigns/{uuid.uuid4().hex}", timeout=60)
        assert r.status_code == 404

    def test_max_price_below_target_400(self, client):
        r = client.post(f"{BASE_URL}/api/sourcing/discover", json={
            "material": "tiles", "target_price": 500, "max_price": 400,
            "currency": "INR"}, timeout=60)
        assert r.status_code == 400

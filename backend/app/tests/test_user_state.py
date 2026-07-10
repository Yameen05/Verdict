"""Tests for per-user workspace state (watchlist, positions, alerts, levels)."""

from __future__ import annotations


def test_watchlist_roundtrip(client):
    assert client.get("/me/watchlist").json() == {"tickers": []}

    res = client.post("/me/watchlist", json={"ticker": "aapl"})
    assert res.status_code == 200
    assert res.json()["tickers"] == ["AAPL"]

    # Duplicates are idempotent.
    client.post("/me/watchlist", json={"ticker": "AAPL"})
    client.post("/me/watchlist", json={"ticker": "BTC-USD"})
    assert client.get("/me/watchlist").json()["tickers"] == ["AAPL", "BTC-USD"]

    res = client.delete("/me/watchlist/AAPL")
    assert res.json()["tickers"] == ["BTC-USD"]


def test_watchlist_rejects_bad_ticker(client):
    assert client.post("/me/watchlist", json={"ticker": "not a ticker!"}).status_code == 400
    assert client.post("/me/watchlist", json={"ticker": ""}).status_code == 400


def test_position_upsert_and_delete(client):
    assert client.get("/me/positions/TSLA").json() == {"position": None}

    res = client.post(
        "/me/positions",
        json={"ticker": "TSLA", "amount_usd": 250.5, "buy_date": "2026-06-01"},
    )
    assert res.status_code == 200
    body = res.json()["position"]
    assert body == {
        "ticker": "TSLA",
        "amount_usd": 250.5,
        "buy_date": "2026-06-01",
        "buy_price": None,
    }

    # Upsert replaces in place.
    res = client.post(
        "/me/positions",
        json={"ticker": "TSLA", "amount_usd": 300, "buy_date": "2026-06-02", "buy_price": 181.4},
    )
    assert res.json()["position"]["amount_usd"] == 300
    assert res.json()["position"]["buy_price"] == 181.4

    client.delete("/me/positions/TSLA")
    assert client.get("/me/positions/TSLA").json() == {"position": None}


def test_position_validates_inputs(client):
    bad_date = client.post(
        "/me/positions", json={"ticker": "TSLA", "amount_usd": 100, "buy_date": "junk"}
    )
    assert bad_date.status_code == 422
    bad_amount = client.post(
        "/me/positions", json={"ticker": "TSLA", "amount_usd": -5, "buy_date": "2026-06-01"}
    )
    assert bad_amount.status_code == 422


def test_alerts_lifecycle(client):
    res = client.post(
        "/me/alerts", json={"ticker": "AAPL", "direction": "above", "price": 250}
    )
    assert res.status_code == 200
    alert = res.json()["alert"]
    assert alert["ticker"] == "AAPL"
    assert alert["direction"] == "above"
    assert alert["triggered"] is False

    listed = client.get("/me/alerts", params={"ticker": "AAPL"}).json()["alerts"]
    assert len(listed) == 1

    fired = client.post(f"/me/alerts/{alert['id']}/trigger").json()["alert"]
    assert fired["triggered"] is True
    assert fired["triggered_price"] == 250

    # Triggering twice is idempotent.
    again = client.post(f"/me/alerts/{alert['id']}/trigger").json()["alert"]
    assert again["triggered_at"] == fired["triggered_at"]

    client.delete(f"/me/alerts/{alert['id']}")
    assert client.get("/me/alerts").json()["alerts"] == []


def test_trigger_unknown_alert_is_404(client):
    assert client.post("/me/alerts/9999/trigger").status_code == 404


def test_levels_roundtrip(client):
    client.post("/me/levels", json={"ticker": "NVDA", "price": 120.5})
    client.post("/me/levels", json={"ticker": "NVDA", "price": 118})
    client.post("/me/levels", json={"ticker": "NVDA", "price": 120.5})  # dedupe
    assert client.get("/me/levels/NVDA").json()["prices"] == [118.0, 120.5]

    # Delete one price, then clear the rest.
    res = client.delete("/me/levels/NVDA", params={"price": 118})
    assert res.json()["prices"] == [120.5]
    res = client.delete("/me/levels/NVDA")
    assert res.json()["prices"] == []


def test_verdict_watch_roundtrip(client):
    assert client.get("/me/verdict-watch/AAPL").json() == {"recommendation": None}
    res = client.post("/me/verdict-watch", json={"ticker": "AAPL", "recommendation": "Buy"})
    assert res.json() == {"recommendation": "Buy"}
    res = client.post("/me/verdict-watch", json={"ticker": "AAPL", "recommendation": "Hold"})
    assert res.json() == {"recommendation": "Hold"}
    client.delete("/me/verdict-watch/AAPL")
    assert client.get("/me/verdict-watch/AAPL").json() == {"recommendation": None}

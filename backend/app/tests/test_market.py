"""Tests for stock-viewer market data endpoints."""

from __future__ import annotations

import pytest

from app.routers import market as market_mod
from app.services.metrics_client import MetricsClientError, PriceBar


@pytest.fixture(autouse=True)
def reset_market_cache():
    market_mod._reset_cache()
    yield
    market_mod._reset_cache()


def test_price_history_endpoint_returns_bars(client, monkeypatch):
    def fake_fetch(ticker: str, range_key: str, interval_key: str):
        assert ticker == "AAPL"
        assert range_key == "1M"
        assert interval_key == "1D"
        return (
            [
                PriceBar(
                    time="2026-07-08T00:00:00Z",
                    open=100.0,
                    high=102.0,
                    low=99.0,
                    close=101.5,
                    volume=5000,
                )
            ],
            "1D",
        )

    monkeypatch.setattr(market_mod, "fetch_price_history", fake_fetch)
    res = client.get("/market/aapl/history?range=1M")
    assert res.status_code == 200
    body = res.json()
    assert body["ticker"] == "AAPL"
    assert body["range"] == "1M"
    assert body["interval"] == "1D"
    assert body["bars"][0]["close"] == 101.5


def test_price_history_endpoint_rejects_invalid_range(client):
    res = client.get("/market/AAPL/history?range=2Y")
    assert res.status_code == 400
    assert "Invalid range" in res.json()["detail"]


def test_price_history_endpoint_maps_yfinance_error(client, monkeypatch):
    def fake_fetch(_ticker: str, _range_key: str, _interval_key: str):
        raise MetricsClientError("No price history available")

    monkeypatch.setattr(market_mod, "fetch_price_history", fake_fetch)
    res = client.get("/market/AAPL/history")
    assert res.status_code == 502
    assert "No price history" in res.json()["detail"]


def test_latest_price_endpoint_returns_last_bar(client, monkeypatch):
    def fake_fetch(ticker: str, interval_key: str):
        assert ticker == "AAPL"
        assert interval_key == "1M"
        return (
            PriceBar(
                time="2026-07-08T13:31:00Z",
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=3000,
            ),
            "1M",
        )

    monkeypatch.setattr(market_mod, "fetch_latest_price_bar", fake_fetch)
    res = client.get("/market/AAPL/quote?interval=1M")
    assert res.status_code == 200
    body = res.json()
    assert body["interval"] == "1M"
    assert body["bar"]["close"] == 100.5


def _daily_bars(closes: list[float]) -> list[PriceBar]:
    return [
        PriceBar(
            time="2024-01-01T00:00:00Z",
            open=c,
            high=c,
            low=c,
            close=c,
            volume=1000,
        )
        for c in closes
    ]


def test_return_ranges_endpoint(client, monkeypatch):
    from app.services.metrics_client import HorizonStats

    def fake_stats(_closes: list[float], horizon_days: int):
        return HorizonStats(
            horizon_days=horizon_days,
            recent_return_pct=1.0,
            typical_swing_pct=5.0,
            best_window_pct=12.0,
            worst_window_pct=-8.0,
        )

    monkeypatch.setattr(
        market_mod,
        "fetch_price_history",
        lambda t, r, i: (_daily_bars([100.0] * 600), "1D"),
    )
    monkeypatch.setattr(market_mod, "horizon_stats_from_closes", fake_stats)
    res = client.get("/market/AAPL/ranges?amount=200")
    assert res.status_code == 200
    body = res.json()
    assert body["ticker"] == "AAPL"
    assert body["amount"] == 200.0
    assert body["rows"][0]["label"] == "1 week"
    assert body["rows"][0]["likely_low"] == 190.0
    assert body["rows"][0]["likely_high"] == 210.0
    assert body["rows"][0]["best_case"] == 224.0
    assert body["rows"][0]["worst_case"] == 184.0


def test_return_ranges_one_year_row_has_data(client, monkeypatch):
    """~2y of closes must populate every horizon row, including 1 year."""
    closes = [100.0 * (1.0002**i) for i in range(504)]
    monkeypatch.setattr(
        market_mod, "fetch_price_history", lambda t, r, i: (_daily_bars(closes), "1D")
    )
    res = client.get("/market/AAPL/ranges")
    assert res.status_code == 200
    rows = {row["label"]: row for row in res.json()["rows"]}
    year = rows["1 year"]
    assert year["normal_move_pct"] is not None
    assert year["likely_low"] is not None and year["likely_high"] is not None
    assert year["best_case"] is not None and year["worst_case"] is not None


def test_return_ranges_502_when_no_history(client, monkeypatch):
    def boom(_t, _r, _i):
        raise MetricsClientError("all providers down")

    monkeypatch.setattr(market_mod, "fetch_price_history", boom)
    res = client.get("/market/AAPL/ranges")
    assert res.status_code == 502


def test_capabilities_equity_vs_crypto(client):
    equity = client.get("/market/AAPL/capabilities").json()
    assert equity["asset_class"] == "equity"
    assert equity["has_filings"] is True
    assert equity["note"] is None

    coin = client.get("/market/BTC-USD/capabilities").json()
    assert coin["asset_class"] == "crypto"
    assert coin["display_name"] == "Bitcoin"
    assert coin["has_filings"] is False
    assert coin["has_earnings"] is False
    assert coin["trades_24_7"] is True
    assert coin["note"]

    # Unlisted coins still classify as crypto via the -USD suffix.
    other = client.get("/market/PEPE-USD/capabilities").json()
    assert other["asset_class"] == "crypto"
    assert other["display_name"] is None

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

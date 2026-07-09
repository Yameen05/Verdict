"""Unit tests for metrics_client. yfinance is monkey-patched."""

from __future__ import annotations

import pytest

from app.services import metrics_client


class _FakeTicker:
    def __init__(self, info: dict):
        self.info = info


@pytest.fixture
def patched_yf(monkeypatch):
    """Return a setter that installs a stub yf.Ticker constructor."""

    def _set(info: dict):
        monkeypatch.setattr(metrics_client.yf, "Ticker", lambda _t: _FakeTicker(info))

    return _set


def test_fetch_metrics_happy_path(patched_yf):
    patched_yf(
        {
            "totalRevenue": 394328000000,
            "trailingEps": 6.16,
            "trailingPE": 30.5,
            "profitMargins": 0.253,
            "debtToEquity": 145.0,
            "fiftyTwoWeekLow": 164.08,
            "fiftyTwoWeekHigh": 237.49,
        }
    )
    m = metrics_client.fetch_metrics("AAPL")
    assert m.revenue == 394328000000
    assert m.eps == 6.16
    assert m.pe_ratio == 30.5
    assert m.profit_margin == 0.253
    assert m.debt_to_equity == 145.0
    assert m.week_52_low == 164.08
    assert m.week_52_high == 237.49


def test_fetch_metrics_partial_fields_ok(patched_yf):
    patched_yf({"totalRevenue": 1.0, "trailingPE": None, "trailingEps": 0.5})
    m = metrics_client.fetch_metrics("AAPL")
    assert m.revenue == 1.0
    assert m.eps == 0.5
    assert m.pe_ratio is None
    assert m.debt_to_equity is None


def test_fetch_metrics_unknown_ticker(patched_yf):
    # Yahoo's "no such symbol" response: dict with no mapped fields.
    patched_yf({"trailingPegRatio": None})
    with pytest.raises(metrics_client.MetricsClientError, match="No metrics"):
        metrics_client.fetch_metrics("ZZZZZ")


def test_fetch_metrics_yfinance_raises(monkeypatch):
    def boom(_t):
        raise RuntimeError("network down")

    monkeypatch.setattr(metrics_client.yf, "Ticker", boom)
    with pytest.raises(metrics_client.MetricsClientError, match="network down"):
        metrics_client.fetch_metrics("AAPL")


def test_fetch_metrics_nan_dropped(patched_yf):
    nan = float("nan")
    patched_yf({"totalRevenue": 100.0, "trailingEps": nan})
    m = metrics_client.fetch_metrics("AAPL")
    assert m.revenue == 100.0
    assert m.eps is None


def test_fetch_metrics_empty_ticker():
    with pytest.raises(metrics_client.MetricsClientError, match="Empty"):
        metrics_client.fetch_metrics("")


class TestHorizonStats:
    def test_stats_from_synthetic_history(self, monkeypatch):
        import app.services.metrics_client as mc

        # Steady 0.5%/day climb for a year → predictable window returns.
        closes = [100.0 * (1.005**i) for i in range(252)]

        class _FakeHist:
            def __init__(self):
                self._closes = closes

            def __getitem__(self, key):
                assert key == "Close"
                return self

            def tolist(self):
                return self._closes

        class _FakeTicker:
            def __init__(self, _t):
                pass

            def history(self, period, auto_adjust):
                return _FakeHist()

        monkeypatch.setattr(mc.yf, "Ticker", _FakeTicker)
        stats = mc.fetch_horizon_stats("AAPL", 14)  # 14 calendar → 10 trading days
        expected = (1.005**10 - 1) * 100
        assert stats.horizon_days == 14
        assert abs(stats.recent_return_pct - round(expected, 2)) < 0.05
        # A perfectly steady climb has (near) zero swing.
        assert stats.typical_swing_pct < 0.01
        assert abs(stats.best_window_pct - stats.worst_window_pct) < 0.05

    def test_insufficient_history_raises(self, monkeypatch):
        import app.services.metrics_client as mc

        class _FakeHist:
            def __getitem__(self, key):
                return self

            def tolist(self):
                return [100.0, 101.0]

        class _FakeTicker:
            def __init__(self, _t):
                pass

            def history(self, period, auto_adjust):
                return _FakeHist()

        monkeypatch.setattr(mc.yf, "Ticker", _FakeTicker)
        import pytest as _pytest

        with _pytest.raises(mc.MetricsClientError):
            mc.fetch_horizon_stats("AAPL", 30)

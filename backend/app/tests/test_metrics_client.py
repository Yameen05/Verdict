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


class TestPriceHistory:
    def test_fetch_price_history_from_synthetic_bars(self, monkeypatch):
        import app.services.metrics_client as mc

        class _FakeTimestamp:
            def __init__(self, value):
                self.value = value

            def isoformat(self):
                return self.value

        class _FakeHistory:
            empty = False

            def iterrows(self):
                rows = [
                    (
                        _FakeTimestamp("2026-07-08T13:30:00Z"),
                        {
                            "Open": 100.0,
                            "High": 104.0,
                            "Low": 99.5,
                            "Close": 103.0,
                            "Volume": 12345,
                        },
                    ),
                    (
                        _FakeTimestamp("2026-07-08T13:35:00Z"),
                        {
                            "Open": 103.0,
                            "High": 105.0,
                            "Low": 101.0,
                            "Close": 102.5,
                            "Volume": None,
                        },
                    ),
                ]
                return iter(rows)

        class _FakeTicker:
            def __init__(self, _t):
                pass

            def history(self, period, interval, auto_adjust):
                assert period == "1d"
                assert interval == "1m"
                assert auto_adjust is True
                return _FakeHistory()

        monkeypatch.setattr(mc.yf, "Ticker", _FakeTicker)
        bars, interval = mc.fetch_price_history("aapl", "1D", "1M")
        assert len(bars) == 2
        assert interval == "1M"
        assert bars[0].time == "2026-07-08T13:30:00Z"
        assert bars[0].close == 103.0
        assert bars[0].volume == 12345
        assert bars[1].volume is None

    def test_fetch_price_history_rejects_unknown_range(self):
        import app.services.metrics_client as mc

        with pytest.raises(mc.MetricsClientError, match="Unsupported price range"):
            mc.fetch_price_history("AAPL", "2Y")

    def test_fetch_price_history_promotes_too_dense_interval(self, monkeypatch):
        import app.services.metrics_client as mc

        class _FakeHistory:
            empty = False

            def iterrows(self):
                return iter([
                    (
                        "2026-07-08",
                        {
                            "Open": 100.0,
                            "High": 101.0,
                            "Low": 99.0,
                            "Close": 100.5,
                            "Volume": 1000,
                        },
                    )
                ])

        class _FakeTicker:
            def __init__(self, _t):
                pass

            def history(self, period, interval, auto_adjust):
                assert period == "1mo"
                assert interval == "5m"
                return _FakeHistory()

        monkeypatch.setattr(mc.yf, "Ticker", _FakeTicker)
        _bars, interval = mc.fetch_price_history("AAPL", "1M", "1M")
        assert interval == "5M"

    def test_three_month_intraday_promotes_to_hourly(self, monkeypatch):
        import app.services.metrics_client as mc

        class _FakeHistory:
            empty = False

            def iterrows(self):
                return iter([
                    (
                        "2026-07-08",
                        {
                            "Open": 100.0,
                            "High": 101.0,
                            "Low": 99.0,
                            "Close": 100.5,
                            "Volume": 1000,
                        },
                    )
                ])

        class _FakeTicker:
            def __init__(self, _t):
                pass

            def history(self, period, interval, auto_adjust):
                assert period == "3mo"
                assert interval == "1h"
                return _FakeHistory()

        monkeypatch.setattr(mc.yf, "Ticker", _FakeTicker)
        _bars, interval = mc.fetch_price_history("AAPL", "3M", "1M")
        assert interval == "1H"

    def test_fetch_latest_price_bar_returns_last_bar(self, monkeypatch):
        import app.services.metrics_client as mc

        class _FakeHistory:
            empty = False

            def iterrows(self):
                rows = [
                    ("2026-07-08T13:30:00Z", {"Open": 1, "High": 2, "Low": 1, "Close": 1.5}),
                    ("2026-07-08T13:31:00Z", {"Open": 2, "High": 3, "Low": 2, "Close": 2.5}),
                ]
                return iter(rows)

        class _FakeTicker:
            def __init__(self, _t):
                pass

            def history(self, period, interval, auto_adjust):
                return _FakeHistory()

        monkeypatch.setattr(mc.yf, "Ticker", _FakeTicker)
        bar, interval = mc.fetch_latest_price_bar("AAPL", "1M")
        assert interval == "1M"
        assert bar.close == 2.5

    def test_daily_falls_back_to_stooq_when_yahoo_fails(self, monkeypatch):
        import datetime as _dt

        import app.services.metrics_client as mc

        monkeypatch.setattr(
            mc, "_yfinance_history", lambda *_a, **_k: (_ for _ in ()).throw(
                mc.MetricsClientError("yahoo down")
            )
        )
        today = _dt.datetime.now(_dt.UTC).date()
        recent = today - _dt.timedelta(days=1)
        csv_text = (
            "Date,Open,High,Low,Close,Volume\n"
            f"{recent.isoformat()},100,101,99,100.5,1000\n"
        )

        class _Resp:
            text = csv_text

            def raise_for_status(self):
                pass

        monkeypatch.setattr(mc.httpx, "get", lambda *_a, **_k: _Resp())
        bars, resolved = mc.fetch_price_history("AAPL", "1M", "1D")
        assert resolved == "1D"
        assert len(bars) == 1
        assert bars[0].close == 100.5

    def test_intraday_does_not_fall_back_to_stooq(self, monkeypatch):
        import app.services.metrics_client as mc

        monkeypatch.setattr(
            mc, "_yfinance_history", lambda *_a, **_k: (_ for _ in ()).throw(
                mc.MetricsClientError("yahoo down")
            )
        )
        # Stooq has no intraday; a 1D/1m request must surface the Yahoo error.
        with pytest.raises(mc.MetricsClientError):
            mc.fetch_price_history("AAPL", "1D", "1M")

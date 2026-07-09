"""Deterministic technical-analysis snapshot from daily price bars.

Pure functions, no I/O — the timing agent (services/timing.py) feeds these
signals to an LLM, and the deterministic `bias` here is also the fallback when
no LLM is configured. Nothing here *predicts* price; it characterizes the
current setup (trend, momentum, overbought/oversold, volatility, location in
range) so a human — or the agent — can reason about timing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.metrics_client import PriceBar


@dataclass(slots=True)
class TechnicalSnapshot:
    as_of: str
    close: float
    sma20: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    rsi14: float | None = None
    momentum_20d_pct: float | None = None
    volatility_pct: float | None = None  # avg daily true range as % of price
    week_52_high: float | None = None
    week_52_low: float | None = None
    dist_from_high_pct: float | None = None  # negative = below the high
    dist_from_low_pct: float | None = None  # positive = above the low
    support: float | None = None  # recent swing low
    resistance: float | None = None  # recent swing high
    macd_hist: float | None = None  # MACD histogram (macd - signal); >0 bullish
    ma_trend: str | None = None  # golden (50>200) | death (50<200) | None
    days_to_earnings: int | None = None  # populated by the timing agent (network)
    trend: str = "unknown"  # up | down | sideways | unknown
    bias: str = "neutral"  # bullish | neutral | bearish
    bias_score: int = 0
    signals: list[str] = field(default_factory=list)


def _ema(values: list[float], length: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < length:
        return out
    k = 2 / (length + 1)
    ema = sum(values[:length]) / length
    out[length - 1] = ema
    for i in range(length, len(values)):
        ema = values[i] * k + ema * (1 - k)
        out[i] = ema
    return out


def _macd_hist(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> float | None:
    """Latest MACD histogram value (MACD line minus its signal EMA)."""
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    macd_line = [
        f - s for f, s in zip(ema_fast, ema_slow, strict=True) if f is not None and s is not None
    ]
    if len(macd_line) < signal:
        return None
    sig = _ema(macd_line, signal)
    last_macd = macd_line[-1]
    last_sig = sig[-1]
    if last_sig is None:
        return None
    return round(last_macd - last_sig, 4)


def _sma(closes: list[float], length: int) -> float | None:
    if len(closes) < length:
        return None
    return round(sum(closes[-length:]) / length, 4)


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        gains += max(delta, 0.0)
        losses += max(-delta, 0.0)
    avg_gain = gains / period
    avg_loss = losses / period
    for i in range(period + 1, len(closes)):
        delta = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(delta, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-delta, 0.0)) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 2)


def _avg_true_range_pct(bars: list[PriceBar], period: int = 14) -> float | None:
    if len(bars) < 2:
        return None
    trs: list[float] = []
    for i in range(1, len(bars)):
        prev_close = bars[i - 1].close
        high = bars[i].high
        low = bars[i].low
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    window = trs[-period:] if len(trs) >= period else trs
    atr = sum(window) / len(window)
    last_close = bars[-1].close
    if last_close <= 0:
        return None
    return round(atr / last_close * 100, 2)


def compute_snapshot(bars: list[PriceBar]) -> TechnicalSnapshot:
    if not bars:
        raise ValueError("no price bars")

    closes = [b.close for b in bars]
    last = bars[-1]
    close = last.close
    snap = TechnicalSnapshot(as_of=last.time, close=round(close, 4))

    snap.sma20 = _sma(closes, 20)
    snap.sma50 = _sma(closes, 50)
    snap.sma200 = _sma(closes, 200)
    snap.rsi14 = _rsi(closes)
    snap.volatility_pct = _avg_true_range_pct(bars)

    if len(closes) > 20:
        prior = closes[-21]
        if prior > 0:
            snap.momentum_20d_pct = round((close - prior) / prior * 100, 2)

    window = bars[-252:] if len(bars) >= 252 else bars
    highs = [b.high for b in window]
    lows = [b.low for b in window]
    snap.week_52_high = round(max(highs), 4)
    snap.week_52_low = round(min(lows), 4)
    if snap.week_52_high > 0:
        snap.dist_from_high_pct = round((close - snap.week_52_high) / snap.week_52_high * 100, 2)
    if snap.week_52_low > 0:
        snap.dist_from_low_pct = round((close - snap.week_52_low) / snap.week_52_low * 100, 2)

    recent = bars[-20:] if len(bars) >= 20 else bars
    snap.support = round(min(b.low for b in recent), 4)
    snap.resistance = round(max(b.high for b in recent), 4)

    snap.macd_hist = _macd_hist(closes)
    if snap.sma50 is not None and snap.sma200 is not None:
        snap.ma_trend = "golden" if snap.sma50 > snap.sma200 else "death"

    _classify(snap)
    return snap


def _classify(snap: TechnicalSnapshot) -> None:
    """Derive trend, a bias score, and human-readable signals."""
    score = 0
    signals: list[str] = []
    close = snap.close

    if snap.sma50 is not None:
        if close > snap.sma50:
            score += 1
            signals.append("price is above its 50-day average (uptrend support)")
        else:
            score -= 1
            signals.append("price is below its 50-day average (downtrend pressure)")
    if snap.sma20 is not None and snap.sma50 is not None:
        if snap.sma20 > snap.sma50:
            score += 1
            signals.append("short-term average is above the medium-term (momentum up)")
        else:
            score -= 1
            signals.append("short-term average is below the medium-term (momentum down)")

    if snap.rsi14 is not None:
        if snap.rsi14 >= 70:
            score -= 1
            signals.append(f"RSI {snap.rsi14:.0f} — overbought, near-term pullback risk")
        elif snap.rsi14 <= 30:
            score += 1
            signals.append(f"RSI {snap.rsi14:.0f} — oversold, possible bounce")
        else:
            signals.append(f"RSI {snap.rsi14:.0f} — neutral momentum")

    if snap.momentum_20d_pct is not None:
        if snap.momentum_20d_pct >= 5:
            score += 1
            signals.append(f"up {snap.momentum_20d_pct:.1f}% over the last month")
        elif snap.momentum_20d_pct <= -5:
            score -= 1
            signals.append(f"down {abs(snap.momentum_20d_pct):.1f}% over the last month")

    if snap.dist_from_high_pct is not None and snap.dist_from_high_pct >= -3:
        score -= 1
        signals.append("trading near its 52-week high — less margin of safety")
    if snap.dist_from_low_pct is not None and snap.dist_from_low_pct <= 8:
        signals.append("trading close to its 52-week low")

    if snap.macd_hist is not None:
        if snap.macd_hist > 0:
            score += 1
            signals.append("MACD above its signal line (bullish momentum)")
        else:
            score -= 1
            signals.append("MACD below its signal line (bearish momentum)")

    if snap.ma_trend == "golden":
        score += 1
        signals.append("50-day average is above the 200-day (long-term uptrend)")
    elif snap.ma_trend == "death":
        score -= 1
        signals.append("50-day average is below the 200-day (long-term downtrend)")

    if snap.volatility_pct is not None and snap.volatility_pct >= 4:
        signals.append(f"elevated volatility (~{snap.volatility_pct:.1f}%/day) — size positions smaller")

    # Trend label from the moving-average stack.
    if snap.sma20 is not None and snap.sma50 is not None:
        if close > snap.sma20 > snap.sma50:
            snap.trend = "up"
        elif close < snap.sma20 < snap.sma50:
            snap.trend = "down"
        else:
            snap.trend = "sideways"

    snap.bias_score = score
    snap.bias = "bullish" if score >= 2 else "bearish" if score <= -2 else "neutral"
    snap.signals = signals

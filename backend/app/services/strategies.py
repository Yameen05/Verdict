"""Small deterministic daily-bar strategies. No LLM or paid analysis calls."""

import asyncio
import math
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.schemas.practice import Rules
from app.services.cache import TTLCache
from app.services.metrics_client import PriceBar, fetch_price_history
from app.services.technicals import _rsi

LIQUID_UNIVERSE = (
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "AMD",
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
)
DATA_NOTE = "Prices are from a recent trading day's finish, not live. We leave out today. Buying and selling here use that recorded price and pretend money. You must choose when to sell."
TEMPLATES = [
    {
        "template": "breakout",
        "name": "A stock getting more attention",
        "lesson": "Find a stock whose price has moved above its recent high, with more shares being bought and sold than usual.",
        "why": "Someone might study this to see whether new interest keeps the price moving up. The price can also fall back.",
    },
    {
        "template": "pullback",
        "name": "A pause in a rising stock",
        "lesson": "Find a stock with a rising average price that is near its usual recent price and has just had an up day.",
        "why": "Someone might study this instead of buying after a big jump. Being near an average does not make it cheap or safe.",
    },
    {
        "template": "rsi_recovery",
        "name": "A stock starting to recover",
        "lesson": "Look for early signs that a stock may be bouncing back after weak price moves. Its latest recorded price must also be higher than the day before.",
        "why": "Someone might study this for early signs of a recovery. It can still keep falling.",
    },
]
_cache: TTLCache[list[PriceBar]] = TTLCache(120, maxsize=128)
_semaphore = asyncio.Semaphore(4)


class DataUnavailable(ValueError):
    pass


def completed_bars(bars: list[PriceBar], now: datetime | None = None) -> list[PriceBar]:
    """Exclude today's possibly unfinished bar, reject corrupt/ambiguous history."""
    now = now or datetime.now(UTC)
    today = now.astimezone(ZoneInfo("America/New_York")).date()
    result = []
    previous = None
    for bar in bars:
        try:
            day = datetime.fromisoformat(bar.time.replace("Z", "+00:00")).date()
        except (TypeError, ValueError) as exc:
            raise DataUnavailable("The price history has a date we cannot read") from exc
        if day > today:
            raise DataUnavailable("The price history has a date in the future, so we cannot use it")
        if day == today:
            continue
        if previous is not None and day <= previous:
            raise DataUnavailable("The price history has repeated or mixed-up dates")
        values = (bar.open, bar.high, bar.low, bar.close)
        if any(not math.isfinite(v) or v <= 0 or v > 100_000_000 for v in values) or not (
            bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high
        ):
            raise DataUnavailable("Some recorded prices do not look valid")
        if bar.volume is not None and (not math.isfinite(bar.volume) or bar.volume < 0):
            raise DataUnavailable("The number of shares traded does not look valid")
        previous = day
        result.append(bar)
    if not result or (today - previous).days > 5:
        raise DataUnavailable(
            "No recent daily price is available. We need a price from the last five calendar days"
        )
    return result


async def market_bars(ticker: str) -> list[PriceBar]:
    async def load():
        async with _semaphore:
            try:
                bars, interval = await asyncio.wait_for(
                    asyncio.to_thread(fetch_price_history, ticker, "1Y", "1D"), timeout=35
                )
            except Exception as exc:
                raise DataUnavailable(
                    "We could not get the price history. Try again in a little while"
                ) from exc
        if interval != "1D":
            raise DataUnavailable("We need daily prices to check this idea")
        return completed_bars(bars)

    # Revalidate cached data so a cache crossing midnight cannot bypass freshness.
    return completed_bars(await _cache.get_or_set(ticker, load))


def evaluate(rules: Rules, bars: list[PriceBar]) -> dict:
    required = (
        max(rules.lookback + 1, 51) if rules.template == "pullback" else max(rules.lookback + 1, 16)
    )
    if len(bars) < required:
        raise DataUnavailable(
            f"We need at least {required} trading days of prices to check this idea"
        )
    last, prior = bars[-1], bars[-2]
    closes = [b.close for b in bars]
    checks = []

    def check(label, passed, explanation, yes, no):
        checks.append(
            {
                "label": label,
                "passed": bool(passed),
                "explanation": explanation,
                "summary": yes if passed else no,
            }
        )

    if rules.template == "breakout":
        window = bars[-rules.lookback - 1 : -1]
        high = max(b.high for b in window)
        if any(b.volume is None for b in [*window, last]):
            raise DataUnavailable(
                "The number of shares traded is missing, so we cannot check this idea"
            )
        average = sum(b.volume for b in window) / len(window)
        if average <= 0:
            raise DataUnavailable("We do not have a usual trading amount to compare with")
        check(
            "Price moved above its recent high",
            last.close > high,
            f"Recorded price ${last.close:.2f}; highest price over the previous {rules.lookback} trading days ${high:.2f}",
            "Its price finished above its recent high.",
            "Its price has not finished above its recent high.",
        )
        ratio = last.volume / average
        check(
            "More shares traded than usual",
            ratio >= rules.volume_multiple,
            f"Shares traded: {ratio:.2f}× the usual amount; this search needs {rules.volume_multiple:g}×",
            "More shares changed hands than the amount this search looks for.",
            "Not enough extra shares changed hands to fit this search.",
        )
    elif rules.template == "pullback":
        average = sum(closes[-rules.lookback :]) / rules.lookback
        slow = sum(closes[-50:]) / 50
        previous_slow = sum(closes[-51:-1]) / 50
        distance = abs(last.close / average - 1) * 100
        check(
            "The longer-term average is rising",
            last.close > slow and slow > previous_slow,
            f"Recorded price ${last.close:.2f}; average over 50 trading days ${slow:.2f}, previously ${previous_slow:.2f}",
            "Its longer-term average price is rising, and the recorded price is above it.",
            "Its price is not above a rising longer-term average.",
        )
        check(
            "Near its usual recent price",
            distance <= rules.tolerance_pct,
            f"Price is {distance:.2f}% from its average over {rules.lookback} trading days (${average:.2f}); this search allows {rules.tolerance_pct:g}%",
            "Its price is close to its average from recent trading days.",
            "Its price is too far from its recent average for this search.",
        )
        check(
            "Price finished higher than the day before",
            last.close > prior.close,
            f"Recorded price ${last.close:.2f}; previous trading day's finish ${prior.close:.2f}",
            "The price finished higher than the trading day before.",
            "The price did not finish higher than the trading day before.",
        )
    else:
        before, current = _rsi(closes[:-1]), _rsi(closes)
        check(
            "The price-change measure turned up",
            before <= rules.rsi_threshold < current,
            f"RSI, a measure of price gains and losses over 14 trading days: {before:.2f} → {current:.2f}; recovery line {rules.rsi_threshold:g}",
            "A measure of recent price gains and losses has just moved back above this search's recovery line.",
            "The price-change measure has not just moved back above this search's recovery line.",
        )
        check(
            "Price finished higher than the day before",
            last.close > prior.close,
            f"Recorded price ${last.close:.2f}; previous trading day's finish ${prior.close:.2f}",
            "The price finished higher than the trading day before.",
            "The price did not finish higher than the trading day before.",
        )
    passed = sum(c["passed"] for c in checks)
    return {
        "matched": passed == len(checks),
        "rules_passed": passed,
        "rules_total": len(checks),
        "checks": checks,
        "as_of": last.time,
        "close": last.close,
    }

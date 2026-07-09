"""FRED macro regime signal."""

from __future__ import annotations

from app.config import get_settings
from app.services.signals.base import get_json, to_float
from app.services.signals.types import MacroRegime

BASE = "https://api.stlouisfed.org/fred/series/observations"


async def _observations(series_id: str, limit: int = 1) -> list[dict]:
    key = get_settings().fred_api_key.strip()
    if not key:
        return []
    data = await get_json(
        BASE,
        params={
            "series_id": series_id,
            "api_key": key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": limit,
        },
    )
    if not isinstance(data, dict):
        return []
    rows = data.get("observations") or []
    return [r for r in rows if isinstance(r, dict) and to_float(r.get("value")) is not None]


async def _latest(series_id: str) -> float | None:
    rows = await _observations(series_id, 1)
    return to_float(rows[0].get("value")) if rows else None


async def _cpi_yoy() -> float | None:
    rows = await _observations("CPIAUCSL", 18)
    values = [to_float(r.get("value")) for r in rows]
    values = [v for v in values if v is not None]
    if len(values) < 13 or not values[12]:
        return None
    return (values[0] / values[12] - 1.0) * 100.0


def _regime(
    fed_funds_pct: float | None,
    cpi_yoy_pct: float | None,
    unemployment_pct: float | None,
    yield_spread_10y_2y: float | None,
) -> tuple[str, str]:
    score = 0
    notes: list[str] = []
    if fed_funds_pct is not None:
        if fed_funds_pct >= 4.5:
            score -= 1
            notes.append("policy rate is high")
        elif fed_funds_pct <= 2.5:
            score += 1
            notes.append("policy rate is easier")
    if cpi_yoy_pct is not None:
        if cpi_yoy_pct >= 3.5:
            score -= 1
            notes.append("inflation is still above target")
        elif cpi_yoy_pct <= 2.5:
            score += 1
            notes.append("inflation is closer to target")
    if yield_spread_10y_2y is not None and yield_spread_10y_2y < -0.25:
        score -= 1
        notes.append("yield curve is inverted")
    if unemployment_pct is not None and unemployment_pct >= 5.0:
        score -= 1
        notes.append("unemployment is elevated")

    if score <= -2:
        return "restrictive", "; ".join(notes) or "macro backdrop is tight"
    if score >= 2:
        return "supportive", "; ".join(notes) or "macro backdrop is supportive"
    return "neutral", "; ".join(notes) or "macro backdrop is mixed"


async def fetch_macro_regime() -> MacroRegime | None:
    if not get_settings().fred_api_key.strip():
        return None
    fed_funds, cpi_yoy, unemployment, ten_year, two_year = await _gather_macro()
    spread = (ten_year - two_year) if ten_year is not None and two_year is not None else None
    regime, note = _regime(fed_funds, cpi_yoy, unemployment, spread)
    if all(v is None for v in (fed_funds, cpi_yoy, unemployment, spread)):
        return None
    return MacroRegime(
        fed_funds_pct=round(fed_funds, 2) if fed_funds is not None else None,
        cpi_yoy_pct=round(cpi_yoy, 2) if cpi_yoy is not None else None,
        unemployment_pct=round(unemployment, 2) if unemployment is not None else None,
        yield_spread_10y_2y=round(spread, 2) if spread is not None else None,
        regime=regime,
        note=note,
        source="fred",
    )


async def _gather_macro() -> tuple[
    float | None,
    float | None,
    float | None,
    float | None,
    float | None,
]:
    import asyncio

    return await asyncio.gather(
        _latest("FEDFUNDS"),
        _cpi_yoy(),
        _latest("UNRATE"),
        _latest("DGS10"),
        _latest("DGS2"),
    )

"""Free US listing directory; browsing never invokes the AI provider."""

from __future__ import annotations

import asyncio
import csv
import io
import re
from datetime import UTC, datetime
from typing import Literal

import httpx
from pydantic import BaseModel

from app.services.cache import TTLCache

DIRECTORY_URLS = (
    "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
)
EXCHANGES = {"N": "NYSE", "A": "NYSE American", "P": "NYSE Arca", "Z": "Cboe", "V": "IEX"}


class ListedAsset(BaseModel):
    ticker: str
    name: str
    exchange: str
    asset_class: Literal["stock", "etf"]


class StockDirectory(BaseModel):
    assets: list[ListedAsset]
    fetched_at: datetime
    source: str = "Nasdaq Trader symbol directories"


_cache: TTLCache[StockDirectory] = TTLCache(6 * 60 * 60, maxsize=1)


def parse_directory(text: str, *, nasdaq: bool) -> list[ListedAsset]:
    rows = csv.DictReader(io.StringIO(text), delimiter="|")
    symbol_column = "Symbol" if nasdaq else "ACT Symbol"
    if not {symbol_column, "Security Name", "ETF", "Test Issue"}.issubset(rows.fieldnames or []):
        raise ValueError("Invalid symbol directory")
    assets = []
    for row in rows:
        symbol = (row.get(symbol_column) or "").strip().upper()
        if not symbol or symbol.startswith("FILE CREATION TIME:") or row.get("Test Issue") != "N":
            continue
        # Yahoo uses hyphens for class shares and longer suffixes for listed
        # warrants, units, and rights (BBAI.W -> BBAI-WT).
        root, separator, suffix = symbol.rpartition(".")
        yahoo_suffix = {"W": "WT", "WS": "WT", "U": "UN", "R": "RT"}.get(suffix)
        ticker = f"{root}-{yahoo_suffix}" if separator and yahoo_suffix else symbol.replace(".", "-")
        if not re.fullmatch(r"[A-Z0-9-]{1,10}", ticker):
            continue
        name = (row.get("Security Name") or "").strip()
        if not name:
            continue
        assets.append(ListedAsset(
            ticker=ticker,
            name=name,
            exchange="NASDAQ" if nasdaq else EXCHANGES.get(row.get("Exchange", ""), "Other US"),
            asset_class="etf" if row.get("ETF") == "Y" else "stock",
        ))
    if not assets:
        raise ValueError("Empty symbol directory")
    return assets


async def _fetch_directory() -> StockDirectory:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        responses = await asyncio.gather(*(client.get(url) for url in DIRECTORY_URLS))
    assets: dict[str, ListedAsset] = {}
    for index, response in enumerate(responses):
        response.raise_for_status()
        for asset in parse_directory(response.text, nasdaq=index == 0):
            assets[asset.ticker] = asset
    return StockDirectory(
        assets=sorted(assets.values(), key=lambda asset: asset.ticker),
        fetched_at=datetime.now(UTC),
    )


async def get_stock_directory() -> StockDirectory:
    return await _cache.get_or_set("directory", _fetch_directory)

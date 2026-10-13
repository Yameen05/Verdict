from __future__ import annotations

import httpx
import pytest

from app.routers import market
from app.services import stock_directory as directory

NASDAQ = """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
AAPL|Apple Inc. Common Stock|Q|N|N|100|N|N
QQQ|Invesco QQQ Trust|G|N|N|100|Y|N
TEST|Test Security|Q|Y|N|100|N|N
File Creation Time: 1009202621:31|||||||
"""
OTHER = """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
BRK.B|Berkshire Hathaway Class B|N|BRK.B|N|100|N|BRK/B
SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY
BAD$A|Unsupported symbol|N|BAD$A|N|100|N|BAD$A
BBAI.W|BigBear.ai Holdings Inc. Warrants|N|BBAI.WS|N|100|N|BBAI+
AAC.U|Acquisition Company Units|N|AAC.U|N|100|N|AAC=
"""


def test_parses_real_directory_formats_and_normalizes_class_shares():
    nasdaq = directory.parse_directory(NASDAQ, nasdaq=True)
    other = directory.parse_directory(OTHER, nasdaq=False)
    assert [(a.ticker, a.asset_class, a.exchange) for a in nasdaq] == [
        ("AAPL", "stock", "NASDAQ"), ("QQQ", "etf", "NASDAQ"),
    ]
    assert [(a.ticker, a.asset_class, a.exchange) for a in other] == [
        ("BRK-B", "stock", "NYSE"), ("SPY", "etf", "NYSE Arca"),
        ("BBAI-WT", "stock", "NYSE"), ("AAC-UN", "stock", "NYSE"),
    ]


@pytest.mark.parametrize("text", ["<html>Upstream error</html>", NASDAQ.splitlines()[0]])
def test_rejects_bad_or_empty_directory_instead_of_caching_it(text):
    with pytest.raises(ValueError):
        directory.parse_directory(text, nasdaq=True)


async def test_fetches_both_sources_and_caches_without_ai_requests(monkeypatch):
    calls = []
    transport = httpx.MockTransport(lambda request: (
        calls.append(str(request.url)) or httpx.Response(200, text=NASDAQ if "nasdaqlisted" in str(request.url) else OTHER)
    ))
    client_type = httpx.AsyncClient
    monkeypatch.setattr(directory.httpx, "AsyncClient", lambda **kwargs: client_type(transport=transport, **kwargs))
    directory._cache.clear()
    try:
        first = await directory.get_stock_directory()
        second = await directory.get_stock_directory()
        assert second == first
        assert [asset.ticker for asset in first.assets] == ["AAC-UN", "AAPL", "BBAI-WT", "BRK-B", "QQQ", "SPY"]
        assert set(calls) == set(directory.DIRECTORY_URLS)
        assert len(calls) == 2
    finally:
        directory._cache.clear()


def test_directory_endpoint_returns_catalog(client, monkeypatch):
    async def fake_directory():
        return directory.StockDirectory(assets=directory.parse_directory(NASDAQ, nasdaq=True), fetched_at="2026-10-10T12:00:00Z")
    monkeypatch.setattr(market, "get_stock_directory", fake_directory)
    response = client.get("/market/directory")
    assert response.status_code == 200
    assert len(response.json()["assets"]) == 2
    client.cookies.clear()
    assert client.get("/market/directory").status_code == 401


def test_directory_outage_returns_recoverable_error(client, monkeypatch):
    async def unavailable():
        raise httpx.ConnectError("directory unavailable")
    monkeypatch.setattr(market, "get_stock_directory", unavailable)
    response = client.get("/market/directory")
    assert response.status_code == 503
    assert "Popular stocks and manual ticker search still work" in response.json()["detail"]

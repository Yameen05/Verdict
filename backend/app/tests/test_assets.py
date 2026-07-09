"""Crypto asset routing: skips for SEC/insider, names for news."""

from __future__ import annotations

from app.agents.nodes import insider_agent as insider_mod
from app.agents.nodes import sec_agent as sec_mod
from app.services.assets import crypto_name, is_crypto


def test_registry():
    assert is_crypto("BTC-USD")
    assert is_crypto("eth-usd")
    assert not is_crypto("AAPL")
    assert crypto_name("BTC-USD") == "Bitcoin"
    assert crypto_name("AAPL") is None


async def test_sec_agent_skips_crypto():
    out = await sec_mod.sec_agent({"ticker": "BTC-USD"})
    assert out["sec"].status == "skipped"
    assert "SEC" in (out["sec"].error or "")


async def test_insider_agent_skips_crypto():
    out = await insider_mod.insider_agent({"ticker": "ETH-USD"})
    assert out["insider"].status == "skipped"

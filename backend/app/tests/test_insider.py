"""Tests for the Form 4 parser and the insider agent node."""

from __future__ import annotations

from app.agents.nodes import insider_agent as insider_agent_mod
from app.schemas.research import InsiderFindings
from app.services.insider_client import (
    Form4Transaction,
    InsiderClientError,
    _parse_form4_xml,
)

FORM4_XML = """<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>DOE JANE</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>0</isDirector>
      <isOfficer>1</isOfficer>
      <officerTitle>Chief Executive Officer</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-06-15</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>210.50</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-06-10</value></transactionDate>
      <transactionCoding><transactionCode>F</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>50</value></transactionShares>
        <transactionPricePerShare><value>210.00</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
"""


def test_parse_form4_xml():
    txns = _parse_form4_xml(FORM4_XML)
    assert len(txns) == 2
    buy = txns[0]
    assert buy.insider == "DOE JANE"
    assert buy.role == "Chief Executive Officer"
    assert buy.kind == "buy"
    assert buy.shares == 1000
    assert buy.value_usd == 210500.0
    assert txns[1].kind == "other"  # F = tax withholding, not a signal


async def test_insider_agent_summarizes_buys(monkeypatch):
    async def fake_fetch(_ticker, max_filings=8):
        return [
            Form4Transaction(
                insider="DOE JANE", role="CEO", date="2026-06-15",
                code="P", kind="buy", shares=1000, value_usd=210500.0,
            ),
            Form4Transaction(
                insider="ROE RICHARD", role=None, date="2026-06-01",
                code="S", kind="sell", shares=200, value_usd=42000.0,
            ),
        ]

    insider_agent_mod._reset_cache()
    monkeypatch.setattr(insider_agent_mod, "fetch_recent_form4", fake_fetch)
    out = await insider_agent_mod.insider_agent({"ticker": "AAPL"})
    findings: InsiderFindings = out["insider"]
    assert findings.status == "ok"
    assert findings.buy_count == 1
    assert findings.sell_count == 1
    # biggest dollar transaction first
    assert findings.transactions[0].insider == "DOE JANE"
    assert "1 open-market buy" in (findings.summary or "")


async def test_insider_agent_skips_on_upstream_failure(monkeypatch):
    async def boom(_ticker, max_filings=8):
        raise InsiderClientError("EDGAR submissions fetch failed: timeout")

    insider_agent_mod._reset_cache()
    monkeypatch.setattr(insider_agent_mod, "fetch_recent_form4", boom)
    out = await insider_agent_mod.insider_agent({"ticker": "AAPL"})
    assert out["insider"].status == "skipped"


async def test_insider_agent_ok_with_no_transactions(monkeypatch):
    async def fake_fetch(_ticker, max_filings=8):
        return []

    insider_agent_mod._reset_cache()
    monkeypatch.setattr(insider_agent_mod, "fetch_recent_form4", fake_fetch)
    out = await insider_agent_mod.insider_agent({"ticker": "AAPL"})
    assert out["insider"].status == "ok"
    assert out["insider"].buy_count == 0
    assert "No open-market" in (out["insider"].summary or "")

"""SEC Form 4 (insider transactions) client.

Uses the same free EDGAR endpoints as sec_client: the submissions JSON lists
recent filings per CIK; each Form 4 is a small XML document whose transaction
codes tell us whether insiders bought or sold on the open market.

Codes we classify (SEC Form 4 Table I):
  P = open-market purchase  → buy   (the strong signal — insiders spending
                                     their own cash)
  S = open-market sale      → sell
  everything else (A grants, M option exercises, F tax withholding, G gifts)
  → other; reported but excluded from the buy/sell counts.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx
from defusedxml import ElementTree as SafeET

from app.observability.logging import get_logger
from app.services.sec_client import SUBMISSIONS_URL_TEMPLATE, _headers, lookup_cik

log = get_logger(__name__)

RAW_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{doc}"
MAX_FORM4 = 8


class InsiderClientError(RuntimeError):
    pass


@dataclass(slots=True)
class Form4Transaction:
    insider: str
    role: str | None
    date: str
    code: str  # raw SEC transaction code
    kind: str  # "buy" | "sell" | "other"
    shares: float | None
    value_usd: float | None


def _kind_for_code(code: str) -> str:
    if code == "P":
        return "buy"
    if code == "S":
        return "sell"
    return "other"


def _float_or_none(text: str | None) -> float | None:
    try:
        return float(text) if text not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _parse_form4_xml(xml_text: str) -> list[Form4Transaction]:
    root = SafeET.fromstring(xml_text)

    owner = root.find(".//reportingOwner")
    name = owner.findtext(".//rptOwnerName", default="Unknown insider") if owner is not None else "Unknown insider"
    role = None
    if owner is not None:
        rel = owner.find(".//reportingOwnerRelationship")
        if rel is not None:
            if rel.findtext("officerTitle"):
                role = rel.findtext("officerTitle")
            elif rel.findtext("isDirector") in ("1", "true"):
                role = "Director"
            elif rel.findtext("isTenPercentOwner") in ("1", "true"):
                role = "10% owner"

    out: list[Form4Transaction] = []
    for txn in root.findall(".//nonDerivativeTransaction"):
        code = txn.findtext(".//transactionCoding/transactionCode", default="")
        shares = _float_or_none(
            txn.findtext(".//transactionAmounts/transactionShares/value")
        )
        price = _float_or_none(
            txn.findtext(".//transactionAmounts/transactionPricePerShare/value")
        )
        out.append(
            Form4Transaction(
                insider=name.strip(),
                role=role.strip() if role else None,
                date=txn.findtext(".//transactionDate/value", default="").strip(),
                code=code.strip(),
                kind=_kind_for_code(code.strip()),
                shares=shares,
                value_usd=round(shares * price, 2) if shares and price else None,
            )
        )
    return out


async def fetch_recent_form4(ticker: str, max_filings: int = MAX_FORM4) -> list[Form4Transaction]:
    """Return transactions from the most recent Form 4 filings for `ticker`.

    Raises InsiderClientError on lookup/network failure. An empty list simply
    means no recent Form 4s — not an error.
    """
    ticker = ticker.strip().upper()
    async with httpx.AsyncClient(headers=_headers(), timeout=20.0) as client:
        try:
            cik = await lookup_cik(ticker, client=client)
            r = await client.get(SUBMISSIONS_URL_TEMPLATE.format(cik=cik))
            r.raise_for_status()
            recent = r.json()["filings"]["recent"]
        except ValueError:
            raise
        except Exception as e:  # noqa: BLE001 - EDGAR quirks vary
            raise InsiderClientError(f"EDGAR submissions fetch failed: {e}") from e

        targets: list[tuple[str, str]] = []  # (accession, primary_document)
        # EDGAR's parallel arrays are equal length by contract, but a truncated
        # response shouldn't crash the agent — zip stops at the shortest.
        for form, acc, doc in zip(
            recent["form"],
            recent["accessionNumber"],
            recent["primaryDocument"],
            strict=False,
        ):
            if form == "4" and doc:
                targets.append((acc, doc))
            if len(targets) >= max_filings:
                break

        if not targets:
            return []

        cik_int = str(int(cik))

        async def _fetch_one(acc: str, doc: str) -> list[Form4Transaction]:
            # primaryDocument for ownership forms is often prefixed with the
            # XSL stylesheet path ("xslF345X05/foo.xml"); the raw XML lives at
            # the bare filename.
            raw_doc = doc.split("/")[-1]
            url = RAW_DOC_URL.format(
                cik_int=cik_int, acc_nodash=acc.replace("-", ""), doc=raw_doc
            )
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                return _parse_form4_xml(resp.text)
            except Exception as e:  # noqa: BLE001 - one bad filing shouldn't sink the rest
                log.warning(
                    "form4_fetch_failed",
                    extra={"ticker": ticker, "accession": acc, "error_type": type(e).__name__},
                )
                return []

        results = await asyncio.gather(*(_fetch_one(a, d) for a, d in targets))

    transactions = [t for batch in results for t in batch]
    transactions.sort(key=lambda t: t.date, reverse=True)
    return transactions

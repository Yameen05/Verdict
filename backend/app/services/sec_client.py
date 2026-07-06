"""Minimal SEC EDGAR client.

SEC's free API requires a descriptive User-Agent including contact info.
Requests without it return 403. The User-Agent is read from settings.

Reference: https://www.sec.gov/os/accessing-edgar-data
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings

FilingForm = Literal["10-K", "10-Q"]

TICKER_LOOKUP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVE_DOC_URL_TEMPLATE = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{doc}"


@dataclass(slots=True)
class Filing:
    ticker: str
    cik: str  # 10-digit zero-padded
    form: FilingForm
    accession: str  # e.g. "0000320193-24-000123"
    filing_date: str  # YYYY-MM-DD
    primary_document: str
    raw_text: str


def _headers() -> dict[str, str]:
    ua = get_settings().sec_user_agent
    return {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}


@dataclass(slots=True)
class TickerInfo:
    cik: str  # zero-padded 10-digit
    name: str  # company title from SEC


_ticker_cache: dict[str, TickerInfo] | None = None


async def _ensure_ticker_cache(client: httpx.AsyncClient | None = None) -> None:
    global _ticker_cache
    if _ticker_cache is not None:
        return
    owns_client = client is None
    c = client or httpx.AsyncClient(headers=_headers(), timeout=30.0)
    try:
        r = await c.get(TICKER_LOOKUP_URL)
        r.raise_for_status()
        data = r.json()
        _ticker_cache = {
            row["ticker"].upper(): TickerInfo(
                cik=str(row["cik_str"]).zfill(10),
                name=row["title"],
            )
            for row in data.values()
        }
    finally:
        if owns_client:
            await c.aclose()


async def lookup_cik(ticker: str, client: httpx.AsyncClient | None = None) -> str:
    """Return zero-padded 10-digit CIK for a ticker symbol."""
    ticker = ticker.upper().strip()
    await _ensure_ticker_cache(client)
    if _ticker_cache is None:
        raise RuntimeError("SEC ticker cache failed to initialize")
    if ticker not in _ticker_cache:
        raise ValueError(f"Unknown ticker: {ticker}")
    return _ticker_cache[ticker].cik


async def lookup_company_name(
    ticker: str, client: httpx.AsyncClient | None = None
) -> str:
    """Return the SEC-registered company name for a ticker (e.g. 'Apple Inc.')."""
    ticker = ticker.upper().strip()
    await _ensure_ticker_cache(client)
    if _ticker_cache is None:
        raise RuntimeError("SEC ticker cache failed to initialize")
    if ticker not in _ticker_cache:
        raise ValueError(f"Unknown ticker: {ticker}")
    return _ticker_cache[ticker].name


async def _fetch_filing(ticker: str, form: FilingForm) -> Filing:
    ticker = ticker.upper().strip()
    async with httpx.AsyncClient(headers=_headers(), timeout=60.0) as client:
        cik = await lookup_cik(ticker, client=client)

        submissions_url = SUBMISSIONS_URL_TEMPLATE.format(cik=cik)
        r = await client.get(submissions_url)
        r.raise_for_status()
        sub = r.json()

        recent = sub["filings"]["recent"]
        forms = recent["form"]
        accessions = recent["accessionNumber"]
        dates = recent["filingDate"]
        docs = recent["primaryDocument"]

        idx = next((i for i, f in enumerate(forms) if f == form), None)
        if idx is None:
            raise ValueError(f"No {form} filing found for {ticker}")

        accession = accessions[idx]
        filing_date = dates[idx]
        primary_document = docs[idx]

        cik_int = str(int(cik))
        acc_nodash = accession.replace("-", "")
        doc_url = ARCHIVE_DOC_URL_TEMPLATE.format(
            cik_int=cik_int, acc_nodash=acc_nodash, doc=primary_document
        )

        doc_r = await client.get(doc_url)
        doc_r.raise_for_status()
        raw_html = doc_r.text

        text = _html_to_text(raw_html)

        return Filing(
            ticker=ticker,
            cik=cik,
            form=form,
            accession=accession,
            filing_date=filing_date,
            primary_document=primary_document,
            raw_text=text,
        )


async def fetch_latest_10k(ticker: str) -> Filing:
    return await _fetch_filing(ticker, "10-K")


async def fetch_latest_10q(ticker: str) -> Filing:
    return await _fetch_filing(ticker, "10-Q")


def _html_to_text(html: str) -> str:
    """Strip tags, scripts, XBRL noise; return roughly readable text."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "head", "meta", "link"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # Collapse runs of whitespace
    lines = (line.strip() for line in text.splitlines())
    cleaned = "\n".join(line for line in lines if line)
    return cleaned

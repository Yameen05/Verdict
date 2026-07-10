"""Asset registry — which tickers are crypto, and friendly names for them.

Crypto trades 24/7 on Yahoo Finance under SYMBOL-USD tickers, so the metrics
agent works unchanged. But coins don't file with the SEC, so the filing and
insider agents skip with a plain-language reason instead of a confusing error.
"""

from __future__ import annotations

CRYPTO_NAMES: dict[str, str] = {
    "BTC-USD": "Bitcoin",
    "ETH-USD": "Ethereum",
    "SOL-USD": "Solana",
    "XRP-USD": "XRP",
    "ADA-USD": "Cardano",
    "DOGE-USD": "Dogecoin",
    "AVAX-USD": "Avalanche",
    "LINK-USD": "Chainlink",
}

CRYPTO_SKIP_REASON = (
    "Cryptocurrencies don't file reports with the SEC, so there's no filing "
    "or insider evidence for this one — the verdict rests on price action "
    "and news."
)


def is_crypto(ticker: str) -> bool:
    ticker = ticker.strip().upper()
    # The curated list catches the majors; the -USD suffix catches the rest of
    # Yahoo's coin universe so an unlisted coin is still treated as crypto.
    return ticker in CRYPTO_NAMES or ticker.endswith("-USD")


def crypto_name(ticker: str) -> str | None:
    return CRYPTO_NAMES.get(ticker.strip().upper())


def asset_capabilities(ticker: str) -> dict:
    """What kinds of evidence exist for this asset.

    Panels use this to hide sections that *cannot* apply (a coin has no SEC
    filings) instead of rendering them as "missing", which reads like an error.
    """
    ticker = ticker.strip().upper()
    crypto = is_crypto(ticker)
    return {
        "ticker": ticker,
        "asset_class": "crypto" if crypto else "equity",
        "display_name": crypto_name(ticker),
        "has_filings": not crypto,
        "has_insiders": not crypto,
        "has_earnings": not crypto,
        "has_analyst_coverage": not crypto,
        "trades_24_7": crypto,
        "note": CRYPTO_SKIP_REASON if crypto else None,
    }

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
    return ticker.strip().upper() in CRYPTO_NAMES


def crypto_name(ticker: str) -> str | None:
    return CRYPTO_NAMES.get(ticker.strip().upper())

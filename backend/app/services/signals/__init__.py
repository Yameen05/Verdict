"""Optional external market-signal providers.

Each module wraps one provider and returns a typed signal or None. They are
key-gated (blank key → skipped) and fully best-effort: any network/parse error
degrades to None so the timing agent keeps working with whatever is available.

`aggregate.gather_market_signals` fans out to every configured provider and
merges the results into a single `MarketSignals` object.
"""

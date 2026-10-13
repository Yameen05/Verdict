"""Rule correctness, ownership and real cash-ledger invariants."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.practice import Rules
from app.services import strategies as engine
from app.services.metrics_client import PriceBar


def history(closes=None):
    closes = closes or [100.0] * 79 + [105.0]
    # Match completed_bars' exchange date, including the UTC/NY midnight gap.
    day = datetime.now(ZoneInfo("America/New_York")).date() - timedelta(days=len(closes))
    return [
        PriceBar(
            time=f"{day + timedelta(days=i)}T00:00:00Z",
            open=p,
            high=p + 1,
            low=p - 1,
            close=p,
            volume=2000 if i == len(closes) - 1 else 1000,
        )
        for i, p in enumerate(closes)
    ]


@pytest.fixture
def market(monkeypatch):
    state = {"bars": history(), "missing": set()}

    async def bars(ticker):
        if ticker in state["missing"]:
            raise engine.DataUnavailable("No usable market data")
        return engine.completed_bars(state["bars"])

    monkeypatch.setattr(engine, "market_bars", bars)
    return state


def save(client, **kw):
    response = client.post(
        "/me/strategies", json={"name": "My breakout", "template": "breakout", **kw}
    )
    assert response.status_code == 200, response.text
    return response.json()


def preview(client, strategy):
    response = client.post(
        "/me/practice/quote", json={"strategy_id": strategy["id"], "ticker": "AAPL"}
    )
    assert response.status_code == 200, response.text
    return response.json()


def place_body(quote, **kw):
    return {
        "quote_id": quote["id"],
        "quantity": 10,
        "stop": 100,
        "target": 115,
        "thesis": "Test the breakout; reassess after two daily closes",
        **kw,
    }


def place(client, quote, **kw):
    response = client.post("/me/practice/trades", json=place_body(quote, **kw))
    assert response.status_code == 200, response.text
    return response.json()


def test_breakout_excludes_signal_bar_from_baselines():
    rules = Rules(name="Breakout", template="breakout")
    result = engine.evaluate(rules, history())
    assert result["matched"] is True
    assert result["rules_passed"] == 2
    assert "101.00" in result["checks"][0]["explanation"]
    assert "2.00×" in result["checks"][1]["explanation"]
    assert engine.evaluate(rules, history([100.0] * 80))["matched"] is False
    bars = history()
    bars[-2] = replace(bars[-2], volume=None)
    with pytest.raises(engine.DataUnavailable, match="shares traded is missing"):
        engine.evaluate(rules, bars)


def test_pullback_requires_trend_proximity_and_up_day():
    rules = Rules(name="Pullback", template="pullback", tolerance_pct=5)
    closes = [100 + i * 0.1 for i in range(80)]
    assert engine.evaluate(rules, history(closes))["matched"] is True
    assert engine.evaluate(rules, history(list(reversed(closes))))["matched"] is False
    assert (
        engine.evaluate(rules.model_copy(update={"tolerance_pct": 0.1}), history(closes))["matched"]
        is False
    )


def test_rsi_recovery_requires_cross_not_just_high_rsi():
    rules = Rules(name="Recovery", template="rsi_recovery")
    closes = [150 - i * 0.5 for i in range(79)] + [120.0]
    result = engine.evaluate(rules, history(closes))
    assert result["matched"] is True
    assert engine.evaluate(rules, history(closes + [121]))["matched"] is False
    with pytest.raises(engine.DataUnavailable, match="at least"):
        engine.evaluate(rules, history([100] * 5))


def test_completed_bars_reject_stale_bad_and_unordered_prices():
    now = datetime(2026, 10, 12, 16, tzinfo=UTC)
    bar = PriceBar("2026-10-09T00:00:00Z", 100, 101, 99, 100, 1000)
    today = replace(bar, time="2026-10-12T00:00:00Z")
    assert engine.completed_bars([bar, today], now) == [bar]
    for bars in (
        [],
        [replace(bar, time="2026-10-13T00:00:00Z")],
        [replace(bar, time="2026-10-01T00:00:00Z")],
        [replace(bar, close=float("nan"))],
        [replace(bar, high=98)],
        [bar, bar],
        [replace(bar, volume=-1)],
        [replace(bar, time="bad")],
    ):
        with pytest.raises(engine.DataUnavailable):
            engine.completed_bars(bars, now)


def test_saved_rules_scan_and_edit_have_no_ai(client, market, monkeypatch):
    async def no_ai(*a, **kw):
        pytest.fail("Scanner must never call research")

    monkeypatch.setattr("app.routers.research.run_research", no_ai, raising=False)
    strategy = save(client)
    market["missing"].add("TSLA")
    response = client.post(f"/me/strategies/{strategy['id']}/scan", json={"universe": "liquid"})
    assert response.status_code == 200, response.text
    scan = response.json()
    assert len(scan["results"]) == 11
    assert scan["skipped"] == [{"ticker": "TSLA", "reason": "No usable market data"}]
    assert all(r["matched"] for r in scan["results"])
    assert len(scan["tickers"]) == 12
    assert client.get("/research/history/AAPL").json()["runs"] == []
    edited = client.post(
        f"/me/strategies/{strategy['id']}",
        json={"name": "Strict volume", "template": "breakout", "volume_multiple": 3},
    )
    assert edited.status_code == 200
    scan = client.post(f"/me/strategies/{strategy['id']}/scan", json={"universe": "liquid"}).json()
    assert not any(r["matched"] for r in scan["results"])


def test_watchlist_scan_is_bounded_and_skips_crypto(client, market, monkeypatch):
    from app.services.stock_directory import ListedAsset, StockDirectory

    async def directory():
        return StockDirectory(
            assets=[
                ListedAsset(ticker="AAPL", name="Apple", exchange="NASDAQ", asset_class="stock")
            ],
            fetched_at=datetime.now(UTC),
        )

    monkeypatch.setattr("app.routers.practice.get_stock_directory", directory)
    strategy = save(client)
    empty = client.post(
        f"/me/strategies/{strategy['id']}/scan", json={"universe": "watchlist"}
    ).json()
    assert empty["results"] == []
    client.post("/me/watchlist", json={"ticker": "AAPL"})
    client.post("/me/watchlist", json={"ticker": "BTC-USD"})
    scan = client.post(
        f"/me/strategies/{strategy['id']}/scan", json={"universe": "watchlist"}
    ).json()
    assert scan["tickers"] == ["AAPL"]
    assert scan["skipped"][0]["ticker"] == "BTC-USD"
    assert (
        client.post(
            "/me/practice/quote", json={"strategy_id": strategy["id"], "ticker": "BTC-USD"}
        ).status_code
        == 400
    )


def test_cash_pnl_journal_snapshot_and_retries(client, market):
    strategy = save(client)
    quote = preview(client, strategy)
    trade = place(client, quote)
    assert place(client, quote)["id"] == trade["id"]
    account = client.get("/me/practice").json()
    assert account["cash"] == 98950
    assert account["open_cost"] == 1050
    assert account["equity"] == 100000
    # Entry context survives edits/deletion, not just a reference to current rules.
    client.post(
        f"/me/strategies/{strategy['id']}", json={"name": "Changed", "template": "pullback"}
    )
    client.delete(f"/me/strategies/{strategy['id']}")
    market["bars"][-1] = replace(market["bars"][-1], open=110, high=111, low=109, close=110)
    account = client.get("/me/practice").json()
    assert account["unrealized_pnl"] == 50
    assert account["equity"] == 100050
    closed = client.post(f"/me/practice/trades/{trade['id']}/close").json()
    assert closed["realized_pnl"] == 50
    assert closed["context"]["strategy"]["name"] == "My breakout"
    assert closed["context"]["plan"]["stop"] == 100
    assert client.post(f"/me/practice/trades/{trade['id']}/close").json() == closed
    notes = client.post(
        f"/me/practice/trades/{trade['id']}/notes", json={"notes": "Followed my plan"}
    ).json()
    assert notes["notes"] == "Followed my plan"
    final = client.get("/me/practice").json()
    assert final["cash"] == final["equity"] == 100050
    assert final["realized_pnl"] == 50
    assert final["unrealized_pnl"] == 0
    assert len(final["trades"]) == 1


def test_missing_data_never_creates_fills_or_fake_marks(client, market):
    strategy = save(client)
    trade = place(client, preview(client, strategy))
    market["missing"].add("AAPL")
    assert (
        client.post(
            "/me/practice/quote", json={"strategy_id": strategy["id"], "ticker": "AAPL"}
        ).status_code
        == 503
    )
    assert client.post(f"/me/practice/trades/{trade['id']}/close").status_code == 503
    account = client.get("/me/practice").json()
    assert account["cash"] == 98950
    assert account["equity"] is None
    assert account["unrealized_pnl"] is None
    assert account["trades"][0]["closed_at"] is None


def test_invalid_plans_no_overdraft_and_loss_accounting(client, market):
    strategy = save(client)
    quote = preview(client, strategy)
    for kw in ({"stop": 105}, {"target": 105}, {"quantity": 0}, {"quantity": 1.5}, {"thesis": " "}):
        assert client.post("/me/practice/trades", json=place_body(quote, **kw)).status_code == 422
    assert (
        client.post("/me/practice/trades", json=place_body(quote, quantity=1000)).status_code == 409
    )
    trade = place(client, quote, quantity=900)
    market["bars"][-1] = replace(market["bars"][-1], open=95, high=96, low=94, close=95)
    assert client.post(f"/me/practice/trades/{trade['id']}/close").json()["realized_pnl"] == -9000
    final = client.get("/me/practice").json()
    assert final["cash"] == final["equity"] == 91000


def test_concurrent_open_and_close_cannot_double_spend(client, market):
    strategy = save(client)
    quote = preview(client, strategy)
    client.get("/me/practice")
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: client.post("/me/practice/trades", json=place_body(quote, quantity=900)),
                range(2),
            )
        )
    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    trade = responses[0].json()
    assert client.get("/me/practice").json()["cash"] == 5500
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(lambda _: client.post(f"/me/practice/trades/{trade['id']}/close"), range(2))
        )
    assert [r.status_code for r in responses] == [200, 200]
    assert client.get("/me/practice").json()["cash"] == 100000


def test_ownership_auth_and_csrf(client, market):
    strategy = save(client)
    quote = preview(client, strategy)
    trade = place(client, quote)
    invite = client.post("/auth/invites", json={"note": "isolation test"}).json()["code"]
    with TestClient(create_app()) as other:
        assert other.get("/me/strategies").status_code == 401
        registered = other.post(
            "/auth/register",
            json={
                "invite_code": invite,
                "email": "other@example.com",
                "password": "Test-password-123",
            },
        )
        assert registered.status_code == 201
        assert (
            other.post(
                "/me/strategies", json={"name": "Bad CSRF", "template": "breakout"}
            ).status_code
            == 403
        )
        other.headers.update({"X-CSRF-Token": registered.json()["csrf_token"]})
        assert other.get("/me/strategies").json()["strategies"] == []
        assert other.get("/me/practice").json()["cash"] == 100000
        for path, body in (
            (f"/me/strategies/{strategy['id']}/scan", {}),
            ("/me/practice/trades", place_body(quote)),
            (f"/me/practice/trades/{trade['id']}/close", {}),
            (f"/me/practice/trades/{trade['id']}/notes", {"notes": "Intrusion"}),
        ):
            assert other.post(path, json=body).status_code == 404
        assert other.delete(f"/me/strategies/{strategy['id']}").status_code == 404


def test_expired_preview_rejected(client, market, monkeypatch):
    from app.security import utc_now

    strategy = save(client)
    quote = preview(client, strategy)
    future = utc_now() + timedelta(minutes=3)
    monkeypatch.setattr("app.routers.practice.utc_now", lambda: future)
    assert client.post("/me/practice/trades", json=place_body(quote)).status_code == 409
    assert client.get("/me/practice").json()["cash"] == 100000


def test_reject_older_close_bar(client, market):
    strategy = save(client)
    trade = place(client, preview(client, strategy))
    market["bars"] = market["bars"][:-1]
    assert client.get("/me/practice").json()["equity"] is None
    assert client.post(f"/me/practice/trades/{trade['id']}/close").status_code == 409


def test_distinct_concurrent_orders_cannot_overdraw(client, market):
    strategy = save(client)
    quotes = [preview(client, strategy), preview(client, strategy)]
    client.get("/me/practice")
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda q: client.post("/me/practice/trades", json=place_body(q, quantity=900)),
                quotes,
            )
        )
    assert sorted(r.status_code for r in responses) == [200, 409]
    account = client.get("/me/practice").json()
    assert account["cash"] == 5500
    assert len(account["trades"]) == 1
    assert account["equity"] == 100000


def test_fill_price_is_server_owned_and_rounds_to_cents(client, market):
    strategy = save(client)
    market["bars"][-1] = replace(market["bars"][-1], open=105.005, high=106, close=105.005)
    quote_response = client.post(
        "/me/practice/quote",
        json={"strategy_id": strategy["id"], "ticker": "AAPL", "entry_price": 1},
    )
    quote = quote_response.json()
    assert quote["entry_price"] == 105.01
    trade = place(client, quote, quantity=3)
    assert client.get("/me/practice").json()["cash"] == 99684.97
    market["bars"][-1] = replace(market["bars"][-1], open=106.005, high=107, close=106.005)
    closed = client.post(f"/me/practice/trades/{trade['id']}/close").json()
    assert closed["realized_pnl"] == 3
    assert client.get("/me/practice").json()["cash"] == 100003

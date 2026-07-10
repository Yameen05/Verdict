"""Background evaluation of price alerts and verdict watches.

Before this worker, alerts were checked only in the browser, so they could not
fire unless a tab was open. The worker runs inside the API process (started in
the lifespan), wakes every ALERTS_CHECK_SECONDS, and:

  1. Fetches one live quote per ticker that has pending alerts and marks any
     crossed alert triggered (email sent when SMTP is configured).
  2. Compares each armed verdict watch against the newest stored run for its
     ticker and notifies + re-arms on a recommendation change.

Every step is best-effort: a bad ticker or provider hiccup skips that ticker
and the loop continues. Nothing here raises out of the worker.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.observability.logging import get_logger
from app.persistence.db import User, latest_run_for_ticker
from app.persistence.user_state import (
    PriceAlert,
    VerdictWatch,
    list_pending_alerts,
    mark_alert_triggered,
)
from app.services.mailer import email_configured, send_email
from app.services.metrics_client import MetricsClientError, fetch_latest_price_bar

log = get_logger(__name__)


def _crossed(alert: PriceAlert, price: float) -> bool:
    return price >= alert.price if alert.direction == "above" else price <= alert.price


async def _email_user(session: AsyncSession, user_id: int, subject: str, body: str) -> None:
    if not email_configured():
        return
    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        return
    await asyncio.to_thread(send_email, user.email, subject, body)


async def evaluate_alerts_once(session: AsyncSession) -> int:
    """One pass over pending price alerts. Returns how many were triggered."""
    pending = await list_pending_alerts(session)
    if not pending:
        return 0

    by_ticker: dict[str, list[PriceAlert]] = {}
    for alert in pending:
        by_ticker.setdefault(alert.ticker, []).append(alert)

    triggered = 0
    for ticker, alerts in by_ticker.items():
        try:
            bar, _ = await asyncio.to_thread(fetch_latest_price_bar, ticker, "1M")
        except MetricsClientError:
            continue  # provider hiccup or delisted ticker — retry next cycle
        for alert in alerts:
            if not _crossed(alert, bar.close):
                continue
            await mark_alert_triggered(session, alert, bar.close)
            triggered += 1
            log.info(
                "price_alert_triggered",
                extra={"ticker": ticker, "alert_id": alert.id, "price": bar.close},
            )
            await _email_user(
                session,
                alert.user_id,
                f"Verdict price alert: {ticker}",
                (
                    f"{ticker} is {alert.direction} your alert level of "
                    f"${alert.price:,.2f} (now ${bar.close:,.2f})."
                ),
            )
    return triggered


async def evaluate_verdict_watches_once(session: AsyncSession) -> int:
    """Notify + re-arm watches whose ticker got a different recommendation."""
    watches = list(await session.scalars(select(VerdictWatch)))
    changed = 0
    for watch in watches:
        latest = await latest_run_for_ticker(session, watch.ticker)
        if latest is None or latest.recommendation == watch.recommendation:
            continue
        old = watch.recommendation
        watch.recommendation = latest.recommendation
        await session.commit()
        changed += 1
        log.info(
            "verdict_watch_changed",
            extra={"ticker": watch.ticker, "from": old, "to": latest.recommendation},
        )
        await _email_user(
            session,
            watch.user_id,
            f"Verdict changed: {watch.ticker}",
            (
                f"The verdict for {watch.ticker} changed from {old} to "
                f"{latest.recommendation}. Open Verdict to read the new report."
            ),
        )
    return changed


async def run_worker(stop: asyncio.Event, interval_seconds: float) -> None:
    """Long-lived loop; started from the FastAPI lifespan, stopped on shutdown."""
    from app.persistence.db import get_sessionmaker

    log.info("alerts_worker_started", extra={"interval_seconds": interval_seconds})
    while not stop.is_set():
        try:
            async with get_sessionmaker()() as session:
                await evaluate_alerts_once(session)
                await evaluate_verdict_watches_once(session)
        except Exception:  # noqa: BLE001 - the worker must survive anything
            log.exception("alerts_worker_cycle_failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except TimeoutError:
            continue
    log.info("alerts_worker_stopped")

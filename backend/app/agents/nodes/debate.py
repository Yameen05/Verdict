"""Adversarial debate — evidence ledger + bull/bear advocates.

After the fetch agents (SEC, news, metrics, insider) complete, `build_evidence`
deterministically converts their findings into a ledger of citable
`EvidenceItem`s. The bull and bear advocates then each get ONE LLM call to
build the strongest case for their side, citing evidence ids. The judge
(see judge.py) weighs both cases and issues the verdict.

Two advocates arguing over the same ledger is not theater: single-pass
synthesis anchors on whichever signal appears first in the prompt; forcing an
explicit steelman of both directions surfaces the disconfirming evidence the
judge must overrule on the record.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import lru_cache
from typing import Literal

from langgraph.config import get_stream_writer
from openai import AsyncOpenAI, OpenAIError

from app.agents.state import ResearchState
from app.config import get_settings
from app.observability.cost import record_chat
from app.observability.logging import get_logger
from app.schemas.research import Argument, DebateCase, EvidenceItem
from app.services.llm import make_llm_client

log = get_logger(__name__)


@lru_cache(maxsize=1)
def _client() -> AsyncOpenAI:
    return make_llm_client()


def _writer() -> Callable[[dict], None]:
    """Custom-stream writer; no-op outside a streaming graph run (e.g. tests)."""
    try:
        return get_stream_writer()
    except Exception:  # noqa: BLE001 - direct node calls have no graph context
        return lambda _payload: None


# ----- evidence ledger -----

def _horizon_label(days: int) -> str:
    if days <= 7:
        return "1-week"
    if days <= 14:
        return "2-week"
    if days <= 31:
        return "1-month"
    if days <= 92:
        return "3-month"
    return "1-year"


def _fmt_usd(v: float) -> str:
    if abs(v) >= 1e9:
        return f"${v / 1e9:.1f}B"
    if abs(v) >= 1e6:
        return f"${v / 1e6:.1f}M"
    return f"${v:,.2f}"


def _fmt_pct(v: float | None, *, signed: bool = False) -> str:
    if v is None:
        return "n/a"
    sign = "+" if signed and v > 0 else ""
    return f"{sign}{v:.1f}%"


def build_evidence(state: ResearchState) -> dict:
    """Pure node: convert agent findings into citable evidence items."""
    items: list[EvidenceItem] = []

    sec = state.get("sec")
    if sec is not None and sec.status == "ok":
        for i, f in enumerate(sec.findings):
            items.append(
                EvidenceItem(
                    id=f"sec:{i}",
                    source="sec",
                    label=f.question,
                    content=f.answer[:600],
                )
            )

    news = state.get("news")
    if news is not None and news.status == "ok":
        if news.sentiment_score is not None:
            items.append(
                EvidenceItem(
                    id="news:sentiment",
                    source="news",
                    label=f"Aggregate news sentiment ({news.article_count} articles, 30 days)",
                    content=f"score {news.sentiment_score:+.2f} in [-1, 1]. "
                    + (news.summary or ""),
                )
            )
        for i, h in enumerate(news.top_headlines[:8]):
            score = f" (sentiment {h.score:+.2f})" if h.score is not None else ""
            items.append(
                EvidenceItem(
                    id=f"news:h{i}",
                    source="news",
                    label=f"{h.source or 'Headline'} · {h.published_at[:10]}",
                    content=f"{h.title}{score}",
                    url=h.url or None,
                )
            )

    metrics = state.get("metrics")
    if metrics is not None and metrics.status == "ok":
        rows: list[tuple[str, str, str]] = []
        if metrics.revenue is not None:
            rows.append(("metrics:revenue", "Revenue (TTM)", _fmt_usd(metrics.revenue)))
        if metrics.eps is not None:
            rows.append(("metrics:eps", "EPS (TTM)", f"{metrics.eps:.2f}"))
        if metrics.pe_ratio is not None:
            rows.append(("metrics:pe", "P/E (trailing)", f"{metrics.pe_ratio:.1f}"))
        if metrics.profit_margin is not None:
            rows.append(
                ("metrics:margin", "Profit margin", f"{metrics.profit_margin * 100:.1f}%")
            )
        if metrics.debt_to_equity is not None:
            rows.append(
                ("metrics:dte", "Debt / equity", f"{metrics.debt_to_equity:.1f}")
            )
        if metrics.week_52_low is not None and metrics.week_52_high is not None:
            rng = f"${metrics.week_52_low:.2f} – ${metrics.week_52_high:.2f}"
            if metrics.current_price is not None:
                rng += f" (current ${metrics.current_price:.2f})"
            rows.append(("metrics:range", "Price range over the past year", rng))
        elif metrics.current_price is not None:
            rows.append(
                ("metrics:price", "Current price", f"${metrics.current_price:.2f}")
            )
        if metrics.horizon_days and metrics.recent_return_pct is not None:
            label = _horizon_label(metrics.horizon_days)
            rows.append(
                (
                    "metrics:recent",
                    f"Most recent {label} move",
                    f"{metrics.recent_return_pct:+.1f}%",
                )
            )
        if metrics.horizon_days and metrics.typical_swing_pct is not None:
            label = _horizon_label(metrics.horizon_days)
            content = f"±{metrics.typical_swing_pct:.1f}% is a normal {label} move for this asset"
            if metrics.best_window_pct is not None and metrics.worst_window_pct is not None:
                content += (
                    f" (best {label} in the past year {metrics.best_window_pct:+.1f}%, "
                    f"worst {metrics.worst_window_pct:+.1f}%)"
                )
            rows.append(("metrics:swing", f"Typical {label} swing", content))
        for eid, label, content in rows:
            items.append(
                EvidenceItem(id=eid, source="metrics", label=label, content=content)
            )

    insider = state.get("insider")
    if insider is not None and insider.status == "ok":
        items.append(
            EvidenceItem(
                id="insider:net",
                source="insider",
                label=f"Insider activity (recent Form 4s: {insider.buy_count} buys / {insider.sell_count} sells)",
                content=insider.summary or "No summary available.",
            )
        )
        for i, t in enumerate(insider.transactions[:6]):
            val = f" ~{_fmt_usd(t.value_usd)}" if t.value_usd else ""
            shares = f"{t.shares:,.0f} shares" if t.shares else "shares n/a"
            items.append(
                EvidenceItem(
                    id=f"insider:t{i}",
                    source="insider",
                    label=f"{t.insider}{' — ' + t.role if t.role else ''}",
                    content=f"{t.kind.upper()} {shares}{val} on {t.date}",
                )
            )

    signals = state.get("signals")
    if signals is not None and signals.status == "ok":
        analyst = signals.analyst
        if analyst is not None:
            total = (
                analyst.strong_buy
                + analyst.buy
                + analyst.hold
                + analyst.sell
                + analyst.strong_sell
            )
            items.append(
                EvidenceItem(
                    id="signals:analyst",
                    source="signals",
                    label=f"Analyst consensus ({analyst.source}, {analyst.period or 'latest'})",
                    content=(
                        f"{analyst.consensus} consensus from {total} analysts "
                        f"(strong buy {analyst.strong_buy}, buy {analyst.buy}, "
                        f"hold {analyst.hold}, sell {analyst.sell}, "
                        f"strong sell {analyst.strong_sell}); score {analyst.score:+.2f}."
                    ),
                )
            )

        if signals.earnings_days is not None:
            items.append(
                EvidenceItem(
                    id="signals:earnings",
                    source="signals",
                    label="Next earnings date",
                    content=(
                        f"Next earnings event is in about {signals.earnings_days} "
                        "calendar day(s); short holds can gap sharply around it."
                    ),
                )
            )

        fundamentals = signals.fundamentals
        if fundamentals is not None:
            quote_price = next((q.price for q in signals.quotes if q.price), None)
            parts: list[str] = []
            if fundamentals.pe_ratio is not None:
                parts.append(f"P/E {fundamentals.pe_ratio:.1f}")
            if fundamentals.peg_ratio is not None:
                parts.append(f"PEG {fundamentals.peg_ratio:.2f}")
            if fundamentals.profit_margin is not None:
                parts.append(f"profit margin {fundamentals.profit_margin * 100:.1f}%")
            if fundamentals.analyst_target is not None:
                target = f"analyst target ${fundamentals.analyst_target:.2f}"
                if quote_price:
                    upside = (fundamentals.analyst_target / quote_price - 1.0) * 100.0
                    target += f" ({_fmt_pct(upside, signed=True)} vs latest quote)"
                parts.append(target)
            if parts:
                items.append(
                    EvidenceItem(
                        id="signals:fundamentals",
                        source="signals",
                        label=f"Fundamental snapshot ({fundamentals.source})",
                        content="; ".join(parts) + ".",
                    )
                )

        if signals.quotes:
            quote_text = []
            for q in signals.quotes[:6]:
                move = (
                    f" {_fmt_pct(q.change_pct, signed=True)}"
                    if q.change_pct is not None
                    else ""
                )
                quote_text.append(f"{q.source}: ${q.price:.2f}{move}")
            items.append(
                EvidenceItem(
                    id="signals:quotes",
                    source="signals",
                    label="Provider quote cross-check",
                    content="; ".join(quote_text),
                )
            )

        retail = signals.retail
        if retail is not None:
            items.append(
                EvidenceItem(
                    id="signals:retail",
                    source="signals",
                    label=f"Retail sentiment ({retail.source})",
                    content=(
                        f"{retail.label}; {retail.bullish} bullish vs "
                        f"{retail.bearish} bearish tagged posts/messages "
                        f"(sample {retail.sample}, score {retail.score:+.2f})."
                    ),
                )
            )

        macro = signals.macro
        if macro is not None:
            parts = [
                f"regime {macro.regime}",
                f"fed funds {_fmt_pct(macro.fed_funds_pct)}",
                f"CPI YoY {_fmt_pct(macro.cpi_yoy_pct)}",
                f"unemployment {_fmt_pct(macro.unemployment_pct)}",
            ]
            if macro.yield_spread_10y_2y is not None:
                parts.append(f"10Y-2Y spread {macro.yield_spread_10y_2y:+.2f} pts")
            if macro.note:
                parts.append(macro.note)
            items.append(
                EvidenceItem(
                    id="signals:macro",
                    source="signals",
                    label=f"Macro regime ({macro.source})",
                    content="; ".join(parts) + ".",
                )
            )

    return {"evidence": items}


# ----- advocates -----

_ADVOCATE_SYSTEM = """You are the {stance} advocate in an adversarial equity
research debate about {ticker}. You receive an evidence ledger: lines of the
form  [id] label: content.

The user plans to hold for about {horizon}. Weight your arguments for that
window — momentum, news, and typical swings dominate short holds; valuation
and fundamentals dominate long holds.

Build the strongest honest {stance} case. Rules:
  • 3-5 arguments, each a single concrete claim grounded in the ledger.
  • Every argument MUST cite the ids of the evidence it rests on.
  • Cite only ids that appear in the ledger. Never invent numbers or facts.
  • Do not concede or hedge — the other side will make the opposing case,
    and a judge will weigh both. Your job is the steelman, not the balance.
  • If the ledger is thin, argue what it supports and no more.

Return ONLY JSON (no markdown fences):
{{"thesis": "one-sentence core thesis",
  "arguments": [{{"claim": "…", "evidence": ["id", "id"]}}]}}
"""


def _ledger_lines(evidence: list[EvidenceItem]) -> str:
    return "\n".join(f"[{e.id}] {e.label}: {e.content}" for e in evidence)


async def _advocate(state: ResearchState, stance: Literal["bull", "bear"]) -> DebateCase:
    evidence = state.get("evidence") or []
    if not evidence:
        return DebateCase(
            stance=stance,
            status="skipped",
            error="No usable evidence was collected; debate skipped.",
        )

    model = get_settings().llm_model
    try:
        resp = await _client().chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": _ADVOCATE_SYSTEM.format(
                        stance=stance,
                        ticker=state["ticker"],
                        horizon=_horizon_label(state.get("horizon_days") or 14),
                    ),
                },
                {"role": "user", "content": _ledger_lines(evidence)},
            ],
            temperature=0.4,
            response_format={"type": "json_object"},
        )
    except OpenAIError as e:
        log.warning(
            "advocate_llm_failed",
            extra={"stance": stance, "error_type": type(e).__name__},
        )
        return DebateCase(
            stance=stance,
            status="error",
            error=f"{stance} advocate LLM call failed ({type(e).__name__}).",
        )
    record_chat(model, resp)

    known_ids = {e.id for e in evidence}
    try:
        data = json.loads(resp.choices[0].message.content or "{}")
        arguments = [
            Argument(
                claim=str(a.get("claim", "")).strip(),
                evidence=[i for i in (a.get("evidence") or []) if i in known_ids],
            )
            for a in (data.get("arguments") or [])
            if str(a.get("claim", "")).strip()
        ][:5]
        return DebateCase(
            stance=stance,
            status="ok",
            thesis=str(data.get("thesis", "")).strip(),
            arguments=arguments,
        )
    except (json.JSONDecodeError, AttributeError, TypeError) as e:
        log.warning("advocate_parse_failed", extra={"stance": stance, "error": str(e)})
        return DebateCase(
            stance=stance,
            status="error",
            error=f"{stance} advocate returned unparseable output.",
        )


async def bull_agent(state: ResearchState) -> dict:
    case = await _advocate(state, "bull")
    _writer()({"kind": "debate_case", "stance": "bull", "case": case.model_dump()})
    return {"bull": case}


async def bear_agent(state: ResearchState) -> dict:
    case = await _advocate(state, "bear")
    _writer()({"kind": "debate_case", "stance": "bear", "case": case.model_dump()})
    return {"bear": case}

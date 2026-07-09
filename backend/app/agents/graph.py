"""LangGraph assembly — the trial.

Topology:

              ┌──────────┐
              │  start   │
              └────┬─────┘
                   │ fan-out (parallel)
     ┌────────┬────┴────┬───────────┐
     ▼        ▼         ▼           ▼
   sec      news     metrics     insider
     └────────┴────┬────┴───────────┘
                   ▼ join
            build_evidence          (deterministic ledger of citable facts)
              ┌────┴────┐
              ▼         ▼
            bull      bear          (adversarial advocates, parallel)
              └────┬────┘
                   ▼ join
                 judge              (verdict + confidence + dissent + falsifiers)
                   │
        ┌──────────┴─────────┐
        ▼ needs_evidence     ▼
     followup               END
   (one targeted RAG
    query, then back
    to the judge)
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.nodes.debate import bear_agent, build_evidence, bull_agent
from app.agents.nodes.insider_agent import insider_agent
from app.agents.nodes.judge import followup, judge, route_after_judge
from app.agents.nodes.metrics_agent import metrics_agent
from app.agents.nodes.news_agent import news_agent
from app.agents.nodes.sec_agent import sec_agent
from app.agents.state import ResearchState
from app.schemas.research import (
    InsiderFindings,
    MetricsFindings,
    NewsFindings,
    ResearchReport,
    ResearchResponse,
    SECFindings,
)

FETCH_NODES = ("sec_agent", "news_agent", "metrics_agent", "insider_agent")


def _build_graph():
    g = StateGraph(ResearchState)

    g.add_node("sec_agent", sec_agent)
    g.add_node("news_agent", news_agent)
    g.add_node("metrics_agent", metrics_agent)
    g.add_node("insider_agent", insider_agent)
    g.add_node("build_evidence", build_evidence)
    g.add_node("bull_agent", bull_agent)
    g.add_node("bear_agent", bear_agent)
    g.add_node("judge", judge)
    g.add_node("followup", followup)

    for node in FETCH_NODES:
        g.add_edge(START, node)
    # List-form edges are explicit join barriers: the target runs once, after
    # ALL listed sources complete.
    g.add_edge(list(FETCH_NODES), "build_evidence")
    g.add_edge("build_evidence", "bull_agent")
    g.add_edge("build_evidence", "bear_agent")
    g.add_edge(["bull_agent", "bear_agent"], "judge")
    g.add_conditional_edges(
        "judge", route_after_judge, {"followup": "followup", "__end__": END}
    )
    g.add_edge("followup", "judge")

    return g.compile()


@lru_cache(maxsize=1)
def get_graph():
    return _build_graph()


def initial_state(
    ticker: str,
    prior_run: dict[str, Any] | None = None,
    horizon_days: int = 14,
) -> dict:
    return {
        "ticker": ticker.upper(),
        "prior_run": prior_run,
        "horizon_days": horizon_days,
        "reflection_count": 0,
    }


def state_to_response(ticker: str, state: dict) -> ResearchResponse:
    return ResearchResponse(
        ticker=ticker.upper(),
        sec=state.get("sec") or SECFindings(status="skipped"),
        news=state.get("news") or NewsFindings(status="skipped"),
        metrics=state.get("metrics") or MetricsFindings(status="skipped"),
        insider=state.get("insider") or InsiderFindings(status="skipped"),
        bull=state.get("bull"),
        bear=state.get("bear"),
        evidence=state.get("evidence") or [],
        report=state.get("report")
        or ResearchReport(
            ticker=ticker.upper(),
            recommendation="Pending",
            justification="Graph did not produce a report.",
            company_overview="",
            financial_health="",
        ),
    )


async def run_research(
    ticker: str,
    prior_run: dict[str, Any] | None = None,
    horizon_days: int = 14,
) -> ResearchResponse:
    graph = get_graph()
    final_state = await graph.ainvoke(initial_state(ticker, prior_run, horizon_days))
    return state_to_response(ticker, final_state)

"""Conversational follow-up endpoint (POST /research/ask).

Grounded in a prior report, with one LLM tool available: `search_filing`
runs a semantic search over the indexed SEC filing so follow-ups can pull
detail the report doesn't carry. Mounted under the /research prefix.
"""

# NOTE: no `from __future__ import annotations` — see routers/research.py.

import json
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel, Field

from app.config import get_settings
from app.limiter import limiter
from app.observability.cost import record_chat, start_tracking
from app.observability.logging import get_logger, get_request_id
from app.routers.research import _validate_ticker
from app.schemas.research import ResearchResponse
from app.services.llm import llm_key_configured, make_llm_client

router = APIRouter()
log = get_logger(__name__)



class ChatTurn(BaseModel):
    role: str = Field(pattern=r"^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class AskRequest(BaseModel):
    ticker: str
    question: str = Field(min_length=2, max_length=2000)
    context: ResearchResponse | None = None
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


class AskResponse(BaseModel):
    answer: str
    cost_usd: float
    request_id: str
    searched_filing: bool = False


_ASK_SYSTEM = """You are Verdict's analyst assistant. The user has already
run a multi-agent research report on a public stock. You receive that report
(SEC filing extracts, recent news sentiment, financial metrics, insider
activity, the bull/bear debate, and the judge's verdict) as JSON, plus the
user's follow-up question.

You also have a tool: `search_filing` runs a semantic search over the indexed
SEC filing for this ticker. Use it when the question asks about something in
the filing that the report context doesn't already answer (segments, specific
risks, accounting details, geographic exposure). Don't use it for questions
the context already covers.

Answer in 2-6 sentences, conversational tone, plain English.

Hard rules:
  • Ground every claim in the JSON context or retrieved filing excerpts. If
    something isn't there, say so plainly — never invent numbers or filings.
  • This is not personalized investment advice. If the user asks for a
    prediction or a "should I" decision, frame it as scenario-based reasoning
    using the provided metrics, and add a one-line disclaimer at the end.
  • For "if I invest $X" hypotheticals: estimate using the 52-week range
    midpoint vs current implied price when available, OR cite the recommendation
    and the metrics that drive it. Show your arithmetic briefly. Always note
    that past ranges don't guarantee future returns.
  • Never recommend specific trades, position sizes, or timing.
  • If context is missing/empty, say "I don't have a fresh report for this
    ticker yet — run the research first."
"""

_SEARCH_FILING_TOOL = {
    "type": "function",
    "function": {
        "name": "search_filing",
        "description": (
            "Semantic search over the indexed SEC filing (10-K/10-Q) for the "
            "current ticker. Returns the most relevant excerpts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to look for in the filing",
                }
            },
            "required": ["query"],
        },
    },
}


@lru_cache(maxsize=1)
def _ask_client() -> AsyncOpenAI:
    return make_llm_client()


def _llm_error_detail(e: OpenAIError) -> str:
    """Turn a provider SDK error into a clear, actionable message.

    Distinguishes a hard out-of-quota/billing failure (which retrying never
    fixes) from a transient rate limit — the SDK reports both as
    RateLimitError, which is what made the original failure look like a
    temporary "try again" glitch.
    """
    msg = str(getattr(e, "message", "") or e).lower()
    if any(s in msg for s in ("insufficient_quota", "exceeded your current quota", "billing")):
        return (
            "The AI provider rejected the request: this account is out of "
            "quota/credits. Add billing/credits or switch to a free provider "
            "(e.g. a Google Gemini key). Retrying won't help until then."
        )
    return f"LLM call failed ({type(e).__name__})"


async def _run_filing_search(ticker: str, query: str) -> str:
    """Execute the search_filing tool; failures come back as tool text."""
    from app.services import vectorstore
    from app.services.embeddings import embed_query

    try:
        vector = await embed_query(query)
        matches = await vectorstore.query(ticker, vector, top_k=4)
    except Exception as e:  # noqa: BLE001 - tool result, not endpoint failure
        return f"Filing search failed ({type(e).__name__}). Answer from the report context."
    if not matches:
        return (
            "No indexed filing chunks for this ticker. Tell the user to ingest "
            "a filing first if they need filing-level detail."
        )
    return "\n\n---\n\n".join(m.text[:1000] for m in matches)


@router.post("/ask", response_model=AskResponse)
@limiter.limit(lambda: get_settings().rate_limit_research)
async def ask(request: Request, body: AskRequest) -> AskResponse:
    ticker = _validate_ticker(body.ticker)
    tracker = start_tracking()
    rid = get_request_id()

    settings = get_settings()
    # Catch missing/placeholder keys early so we return a clean 503 instead of
    # bouncing off the provider SDK.
    if not llm_key_configured(settings.resolved_llm_key):
        raise HTTPException(
            status_code=503,
            detail=(
                "No LLM API key configured. Set LLM_API_KEY (or OPENAI_API_KEY) "
                "in the backend .env and restart. For free Google Gemini, also "
                "set LLM_BASE_URL to its OpenAI-compatible endpoint."
            ),
        )

    grounding: dict[str, Any] = {"ticker": ticker}
    grounding["report"] = body.context.model_dump() if body.context is not None else None

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _ASK_SYSTEM},
        {
            "role": "user",
            "content": "RESEARCH CONTEXT (JSON):\n" + json.dumps(grounding, default=str),
        },
    ]
    for turn in body.history[-10:]:
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": body.question.strip()})

    searched = False
    try:
        resp = await _ask_client().chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=0.3,
            max_tokens=500,
            tools=[_SEARCH_FILING_TOOL],
        )
        record_chat(settings.llm_model, resp)
        choice = resp.choices[0]

        tool_calls = getattr(choice.message, "tool_calls", None)
        if tool_calls:
            searched = True
            messages.append(choice.message.model_dump(exclude_none=True))
            for call in tool_calls[:2]:
                try:
                    query = json.loads(call.function.arguments).get("query", "")
                except json.JSONDecodeError:
                    query = ""
                excerpts = await _run_filing_search(ticker, query or body.question)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": excerpts,
                    }
                )
            resp = await _ask_client().chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                temperature=0.3,
                max_tokens=500,
            )
            record_chat(settings.llm_model, resp)
            choice = resp.choices[0]
    except OpenAIError as e:
        log.exception("ask_llm_failed", extra={"error_type": type(e).__name__})
        raise HTTPException(status_code=502, detail=_llm_error_detail(e)) from e

    answer = (choice.message.content or "").strip() or (
        "I couldn't generate a response. Try rephrasing your question."
    )
    log.info(
        "ask_completed",
        extra={"ticker": ticker, "cost_usd": tracker.total_usd, "searched": searched},
    )
    return AskResponse(
        answer=answer,
        cost_usd=tracker.total_usd,
        request_id=rid,
        searched_filing=searched,
    )



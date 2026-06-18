"""Per-request token and cost accounting.

A `CostTracker` is bound to a ContextVar so any agent code that records chat or
embedding usage contributes to the active request's running total. The router
reads the total at the end of the request and persists / surfaces it.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field

from app.config import get_settings


@dataclass(slots=True)
class CostTracker:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    embedding_tokens: int = 0
    # Per-call breakdown by model for nicer reporting.
    calls: list[dict] = field(default_factory=list)

    def add_chat(self, model: str, prompt: int, completion: int) -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.calls.append(
            {"kind": "chat", "model": model, "prompt": prompt, "completion": completion}
        )

    def add_embedding(self, model: str, tokens: int) -> None:
        self.embedding_tokens += tokens
        self.calls.append({"kind": "embedding", "model": model, "tokens": tokens})

    @property
    def total_usd(self) -> float:
        s = get_settings()
        return round(
            (self.prompt_tokens / 1_000_000) * s.cost_input_per_mtok_usd
            + (self.completion_tokens / 1_000_000) * s.cost_output_per_mtok_usd
            + (self.embedding_tokens / 1_000_000) * s.cost_embed_per_mtok_usd,
            6,
        )

    def to_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "embedding_tokens": self.embedding_tokens,
            "total_usd": self.total_usd,
        }


_tracker_ctx: ContextVar[CostTracker | None] = ContextVar("cost_tracker", default=None)


def start_tracking() -> CostTracker:
    tracker = CostTracker()
    _tracker_ctx.set(tracker)
    return tracker


def current_tracker() -> CostTracker | None:
    return _tracker_ctx.get()


def record_chat(model: str, response) -> None:  # noqa: ANN001 - SDK response
    """Pull usage from a chat completion response and accumulate it."""
    tracker = current_tracker()
    if tracker is None:
        return
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    tracker.add_chat(
        model=model,
        prompt=getattr(usage, "prompt_tokens", 0) or 0,
        completion=getattr(usage, "completion_tokens", 0) or 0,
    )


def record_embedding(model: str, response) -> None:  # noqa: ANN001
    tracker = current_tracker()
    if tracker is None:
        return
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    tracker.add_embedding(
        model=model, tokens=getattr(usage, "prompt_tokens", 0) or 0
    )

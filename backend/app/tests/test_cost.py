"""Gemini usage must include reported thinking without counting it twice."""

from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.observability.cost import record_chat, start_tracking


@pytest.mark.parametrize(
    "completion,details", [(31, None), (76, SimpleNamespace(reasoning_tokens=45))]
)
def test_gemini_reported_thinking_is_counted_once(monkeypatch, completion, details):
    monkeypatch.setenv("COST_INPUT_PER_MTOK_USD", "0")
    monkeypatch.setenv("COST_OUTPUT_PER_MTOK_USD", "0")
    get_settings.cache_clear()
    tracker = start_tracking()
    record_chat(
        "gemini-3.8-flash",
        SimpleNamespace(
            usage=SimpleNamespace(
                prompt_tokens=2485,
                completion_tokens=completion,
                total_tokens=2561,
                completion_tokens_details=details,
            )
        ),
    )
    assert tracker.completion_tokens == 76
    assert tracker.reasoning_tokens == 45
    assert tracker.total_usd == 0

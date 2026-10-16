import pytest

from app.schemas.research import ResearchResponse
from app.services.investment_answer import investment_answer
from app.services.research_policy import research_boundary_answer


@pytest.mark.parametrize("question", [
    "Should I buy AAPL?", "Should we sell our shares?", "Can I invest my savings?",
    "How many shares should I buy?", "Which stocks should I buy?",
    "Tell me when to sell.", "How long should I hold it?",
    "Will I gain or lose money?", "What return should I expect?",
    "I owe $5000 and need to pay rent. Choose a stock.",
    "Use my retirement portfolio to choose an allocation.",
])
async def test_personal_requests_cannot_bypass_via_calculator(question):
    boundary = research_boundary_answer(question)
    assert boundary is not None
    assert "cannot choose a trade" in boundary
    assert await investment_answer("AAPL", question, None) == boundary


def test_ambiguous_followup_stays_within_boundary_but_general_research_can_continue():
    history = ["Should I sell to cover my rent?"]
    assert research_boundary_answer("Okay, what next?", history) is not None
    assert research_boundary_answer("Explain the balance sheet debt", history) is None


@pytest.mark.parametrize("question", ["Does 70 confidence mean 70% odds?", "Is Hold a 50/50 outcome?", "What does assessment score mean?"])
def test_score_questions_are_not_answered_as_probabilities(question):
    answer = research_boundary_answer(question)
    assert "not verified odds of profit" in answer
    assert "Hold does not mean a validated 50/50" in answer


async def test_historical_arithmetic_keeps_exact_inputs_without_trade_guidance(monkeypatch):
    from app.services import investment_answer as module
    from app.services.metrics_client import HorizonStats
    async def stats(*args):
        return HorizonStats(14, recent_return_pct=2, typical_swing_pct=8,
                            best_window_pct=10, worst_window_pct=-5)
    monkeypatch.setattr(module, "_stats_for_horizon", stats)
    context = ResearchResponse.model_validate({
        "ticker": "AAPL", "sec": {"status": "skipped"}, "news": {"status": "skipped"},
        "metrics": {"status": "ok", "current_price": 50}, "insider": {"status": "skipped"},
        "report": {"ticker": "AAPL", "recommendation": "Sell", "confidence": 80,
                   "justification": "General assessment", "company_overview": "", "financial_health": ""},
    })
    answer = await investment_answer("AAPL", "Apply historical swings to a hypothetical $200 investment over 2 weeks", context)
    assert "4.0000 hypothetical shares" in answer
    assert "$184-$216" in answer
    assert "$204" in answer
    assert "not forecasts" in answer
    assert "How long" not in answer
    assert "selling/avoiding" not in answer
    assert "usually" not in answer

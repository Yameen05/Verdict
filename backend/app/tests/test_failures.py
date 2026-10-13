"""Public failure categories never require a live provider."""

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError

from app.services.failures import normalize_failure


def provider(status, body=None, message="secret-key PRIVATE raw exception"):
    response = httpx.Response(status, request=httpx.Request("POST", "https://example.test"))
    return APIStatusError(message, response=response, body=body)


@pytest.mark.parametrize(
    "metric,kind,window",
    [
        ("GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "provider_rate_limit", "minute"),
        ("GenerateRequestsPerDayPerProjectPerModel-FreeTier", "provider_daily_limit", "day"),
        (
            "generate_content_free_tier_input_token_count_PerMinute",
            "provider_token_limit",
            "minute",
        ),
        ("GenerateTokensPerDay", "provider_token_limit", "day"),
        ("GenerateTokens", "provider_token_limit", None),
    ],
)
def test_structured_quota_has_priority(metric, kind, window):
    info = normalize_failure(
        provider(
            429,
            {
                "error": {
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                            "violations": [{"quotaId": metric}],
                        },
                        {
                            "@type": "type.googleapis.com/google.rpc.RetryInfo",
                            "retryDelay": "12.5s",
                        },
                    ]
                }
            },
            "429 per minute rate limit",
        )
    )
    assert (info.kind, info.window) == (kind, window)
    assert info.reset_at is None
    assert info.retry_after_seconds == (12.5 if window == "minute" else None)
    assert "PRIVATE" not in info.message
    if window == "day":
        assert "shortly" in info.message


@pytest.mark.parametrize(
    "status,kind",
    [
        (429, "provider_limit"),
        (503, "provider_busy"),
        (401, "configuration"),
        (403, "configuration"),
        (500, "unknown"),
    ],
)
def test_ambiguous_status_never_invents_quota_window(status, kind):
    result = normalize_failure(provider(status))
    assert result.kind == kind
    assert result.window is result.reset_at is result.retry_after_seconds is None
    assert "PRIVATE" not in result.model_dump_json()
    assert "billing" not in result.message


def test_connectivity_and_timeout_are_distinct():
    request = httpx.Request("POST", "https://example.test")
    assert normalize_failure(APIConnectionError(request=request)).kind == "connection"
    assert normalize_failure(APITimeoutError(request=request)).kind == "timeout"
    assert normalize_failure(TimeoutError()).kind == "timeout"


def test_wrapped_sentiment_failure_keeps_cause():
    cause = provider(503)
    wrapped = RuntimeError("Sentiment failed PRIVATE")
    wrapped.__cause__ = cause
    assert normalize_failure(wrapped, stage="news sentiment").kind == "provider_busy"
    assert normalize_failure(wrapped, stage="news sentiment").stage == "news sentiment"

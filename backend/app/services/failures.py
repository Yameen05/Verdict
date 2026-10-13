"""Normalize provider errors using structured metadata before legacy text.

A 429 alone says nothing about the quota window or remaining allowance.
Only app-owned counters have a known reset time.
"""

from __future__ import annotations

import json
import re

from app.schemas.failure import FailureInfo

MESSAGES = {
    "provider_rate_limit": "Google's requests-per-minute limit was reached. Wait briefly before trying again; cached reports remain available.",
    "provider_daily_limit": "Google's daily AI quota was reached. Retrying shortly is unlikely to help. The provider did not give a confirmed reset time.",
    "provider_token_limit": "Google's AI token quota was reached.",
    "provider_limit": "Google rejected the request because of an AI limit. It did not identify whether this is a short rate limit or a longer quota limit, so a short wait may not help.",
    "provider_busy": "Google is temporarily busy. Try again later; cached reports remain available.",
    "timeout": "The research request timed out. Try again later; any completed checks do not make this a finished report.",
    "connection": "The server could not reach the AI service. Try again when the connection is available.",
    "configuration": "The AI service rejected the server's credentials or configuration. The server configuration needs attention before this can succeed.",
    "unknown": "The research request could not finish. Try again later; cached reports remain available.",
}


def _walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def normalize_failure(error: BaseException, *, stage: str | None = None) -> FailureInfo:
    # Sentiment and retrieval helpers may wrap the SDK exception.
    seen = set()
    while error.__cause__ is not None and id(error) not in seen:
        seen.add(id(error))
        error = error.__cause__
    body = getattr(error, "body", None)
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            body = None
    pairs = list(_walk(body))
    quota = " ".join(
        str(v)
        for k, v in pairs
        if k.lower()
        in {
            "quotametric",
            "quotaid",
            "quota_metric",
            "quota_id",
            "subject",
        }
    ).lower()
    codes = (
        " ".join(
            str(v)
            for k, v in pairs
            if k.lower()
            in {
                "status",
                "code",
                "type",
                "reason",
            }
        ).lower()
        + " "
        + str(getattr(error, "code", "") or "").lower()
    )
    status = getattr(error, "status_code", None)
    # Text is inspected only for classification, never included in public output.
    legacy = f"{type(error).__name__} {error}".lower()
    text = quota if quota else (codes + " " + legacy)
    compact = re.sub(r"[^a-z0-9]", "", text)
    window = (
        "day"
        if "perday" in compact or "daily" in text
        else ("minute" if "perminute" in compact or "rpm" in text else None)
    )
    limited = (
        status == 429
        or bool(re.search(r"\b429\b", legacy))
        or any(
            s in codes + " " + legacy
            for s in (
                "resource_exhausted",
                "ratelimit",
                "rate limit",
                "insufficient_quota",
                "quota",
            )
        )
    )
    if quota:
        limited = True
    if (
        status in (401, 403)
        or re.search(r"\b(?:401|403)\b", legacy)
        or any(
            s in codes + " " + legacy
            for s in (
                "unauthenticated",
                "permission_denied",
                "authentication",
                "invalid_api_key",
                "missing credentials",
                "no llm api key",
                "api_key_invalid",
            )
        )
    ):
        kind = "configuration"
    elif limited:
        if "token" in text:
            kind = "provider_token_limit"
        elif window == "day":
            kind = "provider_daily_limit"
        elif window == "minute":
            kind = "provider_rate_limit"
        else:
            kind = "provider_limit"
    elif (
        status == 503
        or re.search(r"\b503\b", legacy)
        or "unavailable" in codes
        or "overloaded" in legacy
        or "provider busy" in legacy
    ):
        kind = "provider_busy"
    elif isinstance(error, TimeoutError) or "timeout" in legacy or "timed out" in legacy:
        kind = "timeout"
    elif "connection" in legacy or "connecterror" in legacy:
        kind = "connection"
    else:
        kind = "unknown"
    retry = None
    # Google RetryInfo is a suggested delay, not a confirmed daily reset.
    for key, value in pairs:
        if key.lower() in {"retrydelay", "retry_delay"} and isinstance(value, str):
            match = re.fullmatch(r"(\d+(?:\.\d+)?)s", value)
            if match:
                retry = float(match[1])
    message = MESSAGES[kind]
    if kind == "provider_token_limit":
        message += {
            "day": " This is a daily limit; retrying shortly is unlikely to help. No reset time was confirmed.",
            "minute": " This is a per-minute limit; wait briefly before trying again.",
            None: " The provider did not identify its window; a short wait may not help.",
        }[window]
    elif kind == "provider_rate_limit" and retry is not None:
        message += f" The provider suggests waiting at least {retry:g} seconds."
    return FailureInfo(
        kind=kind,
        message=message,
        stage=stage,
        window=window,
        retry_after_seconds=retry if window == "minute" else None,
    )

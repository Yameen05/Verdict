"""Read-only classification of current and legacy research payloads."""

from collections.abc import Mapping


def assessment_failed(payload) -> bool:
    if not isinstance(payload, Mapping):
        return False
    report = payload.get("report") or {}
    if not isinstance(report, Mapping):
        return False
    if (
        report.get("degraded")
        or report.get("failures")
        or report.get("assessment_status") in {"failed", "incomplete"}
        or report.get("recommendation") in {"Failed", "Pending"}
    ):
        return True
    # Known execution failures, not optional absence or zero headlines.
    for key in ("sec", "news", "metrics", "bull", "bear"):
        source = payload.get(key)
        if isinstance(source, Mapping) and (
            source.get("status") == "error" or source.get("failure")
        ):
            return True
    if any(isinstance(payload.get(key), Mapping) for key in ("bull", "bear")) and any(
        not isinstance(payload.get(key), Mapping) for key in ("bull", "bear")
    ):
        return True
    # Older deterministic fallbacks predate the degraded flag.
    text = str(report.get("justification") or "").lower()
    return any(
        phrase in text
        for phrase in (
            "full ai analysis could not run",
            "full ai analysis was unavailable",
            "limited verdict from the data already collected",
        )
    )


def assessment_failure_reason(payload) -> str:
    """Explain exclusions from saved evidence without exposing stored exceptions."""
    from app.services.failures import normalize_failure

    labels = {
        "sec": "Filing review",
        "news": "News review",
        "metrics": "Financial review",
        "bull": "Positive case",
        "bear": "Negative case",
        "insider": "Insider review",
        "signals": "Market signals",
    }
    causes = {
        "provider_rate_limit": "the provider's per-minute quota was reached",
        "provider_daily_limit": "the provider's daily quota was reached",
        "provider_token_limit": "the provider's token quota was reached",
        "provider_limit": "a provider quota was reached; its window was not recorded",
        "provider_busy": "the provider was temporarily busy",
        "timeout": "the request timed out",
        "connection": "the service could not be reached",
        "configuration": "service authentication or configuration failed",
        "unknown": "the exact cause was not recorded",
    }
    notes = []
    if not isinstance(payload, Mapping):
        return "Failed to assess. No usable prediction was issued."
    for key, label in labels.items():
        source = payload.get(key)
        if not isinstance(source, Mapping) or not (
            source.get("status") == "error" or source.get("failure")
        ):
            continue
        saved = source.get("failure")
        kind = saved.get("kind") if isinstance(saved, Mapping) else None
        if kind not in causes:
            kind = normalize_failure(RuntimeError(str(source.get("error") or ""))).kind
        notes.append(f"{label} failed: {causes.get(kind, causes['unknown'])}.")
    report = payload.get("report") or {}
    if not isinstance(report, Mapping):
        report = {}
    if notes and report.get("recommendation") == "Pending":
        notes.append("The final review did not issue a prediction.")
    if not notes:
        if report.get("recommendation") == "Pending":
            notes.append("The final review did not issue a prediction.")
        else:
            notes.append("The saved assessment records an incomplete or failed final review.")
    return (
        "Failed to assess. " + " ".join(dict.fromkeys(notes)) + " Excluded from prediction scores."
    )


def prediction_kind(payload, recommendation=None, confidence=None) -> str:
    """Classify an originally issued prediction independently of analysis quality."""
    payload = payload if isinstance(payload, Mapping) else {}
    report = payload.get("report") or {}
    report = report if isinstance(report, Mapping) else {}
    rec = recommendation or report.get("recommendation")
    if rec not in {"Buy", "Hold", "Sell"} or report.get("recommendation") in {"Failed", "Pending"}:
        return "none"
    explicit = report.get("prediction_kind")
    if explicit == "none":
        return "none"
    if explicit in {"ai", "partial_ai", "rules_based"}:
        kind = explicit
    else:
        text = str(report.get("justification") or "").lower()
        fallback = any(
            phrase in text
            for phrase in (
                "conservative fallback verdict",
                "ai judge was unavailable",
                "full ai analysis could not run",
                "full ai analysis was unavailable",
                "limited verdict from the data already collected",
            )
        )
        # Legacy degraded records came from the deterministic fallback. Modern
        # partial judge results declare partial_ai explicitly before serialization.
        kind = (
            "rules_based"
            if fallback or report.get("degraded")
            else ("partial_ai" if assessment_failed(payload) else "ai")
        )
    if kind == "ai" and assessment_failed(payload):
        kind = "partial_ai"
    score = confidence if confidence is not None else report.get("confidence")
    if kind == "rules_based" and rec == "Hold" and score == 50:
        return "none"  # Known automatic failure placeholder, never an AI prediction.
    return kind


def has_issued_prediction(run) -> bool:
    return (
        prediction_kind(getattr(run, "payload", None), run.recommendation, run.confidence) != "none"
    )


def analysis_warning(payload) -> str:
    reason = assessment_failure_reason(payload)
    return reason.removeprefix("Failed to assess. ").removesuffix(
        " Excluded from prediction scores."
    )

"""Safe public failure metadata; never contains provider response text."""

from typing import Literal

from pydantic import BaseModel

FailureKind = Literal[
    "app_daily_limit",
    "provider_rate_limit",
    "provider_daily_limit",
    "provider_token_limit",
    "provider_limit",
    "provider_busy",
    "timeout",
    "connection",
    "configuration",
    "unknown",
]


class FailureInfo(BaseModel):
    kind: FailureKind
    message: str
    stage: str | None = None
    window: Literal["minute", "day"] | None = None
    retry_after_seconds: float | None = None
    reset_at: str | None = None

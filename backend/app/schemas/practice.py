from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Rules(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    name: str = Field(min_length=1, max_length=80)
    template: Literal["breakout", "pullback", "rsi_recovery"]
    lookback: int = Field(default=20, ge=10, le=60)
    volume_multiple: float = Field(default=1.5, ge=1, le=5)
    tolerance_pct: float = Field(default=2, ge=0.1, le=10)
    rsi_threshold: float = Field(default=30, ge=10, le=50)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Give your saved search a name")
        return value.strip()


class ScanBody(BaseModel):
    universe: Literal["liquid", "watchlist"] = "liquid"


class QuoteBody(BaseModel):
    strategy_id: int
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.-]{0,11}$")


class PlaceBody(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    quote_id: str = Field(min_length=36, max_length=36)
    quantity: int = Field(strict=True, ge=1, le=1_000_000)
    stop: float = Field(gt=0, le=100_000_000)
    target: float = Field(gt=0, le=100_000_000)
    thesis: str = Field(min_length=1, max_length=2000)

    @field_validator("thesis")
    @classmethod
    def thesis_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Write a quick note about why you want to try this")
        return value.strip()


class NotesBody(BaseModel):
    notes: str = Field(max_length=4000)

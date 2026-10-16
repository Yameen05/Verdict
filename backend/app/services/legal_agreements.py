"""Current-document agreement required only when creating a new account."""
import json
from pathlib import Path

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.agreements import LegalAcceptanceRecord
from app.security import record_audit, utc_now

LEGAL_MANIFEST = json.loads((Path(__file__).resolve().parents[1] / "legal_manifest.json").read_text())


class LegalAcceptance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: bool = Field(default=False, strict=True)
    terms_version: str = Field(default="", max_length=64)
    risk_version: str = Field(default="", max_length=64)
    privacy_version: str = Field(default="", max_length=64)
    content_sha256: str = Field(default="", max_length=64)


def current_legal_acceptance() -> dict:
    """Explicit payload helper for synthetic tests, not automatic user consent."""
    return {"accepted": True, "content_sha256": LEGAL_MANIFEST["content_sha256"],
            **{f"{key}_version": value for key, value in LEGAL_MANIFEST["versions"].items()}}


def require_current_acceptance(value: LegalAcceptance | None) -> None:
    if value is None or not value.accepted or value.model_dump() != current_legal_acceptance():
        raise HTTPException(428, "Review and explicitly agree to the current Terms of Service, understand the Risk & Data Disclosure and acknowledge the Privacy Notice before creating an account")


async def record_acceptance(db: AsyncSession, request: Request, user_id: int) -> None:
    versions = LEGAL_MANIFEST["versions"]
    db.add(LegalAcceptanceRecord(user_id=user_id, terms_version=versions["terms"],
                                risk_version=versions["risk"], privacy_version=versions["privacy"],
                                content_sha256=LEGAL_MANIFEST["content_sha256"], accepted_at=utc_now()))
    await record_audit(db, request, "account_legal_agreement", user_id=user_id,
                       details={"versions": versions, "content_sha256": LEGAL_MANIFEST["content_sha256"],
                                "purpose": "terms_agreement_risk_privacy_acknowledgement"})

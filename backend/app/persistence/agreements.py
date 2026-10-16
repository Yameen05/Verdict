"""Account-creation agreement evidence; never backfilled for existing accounts."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.db import Base


class LegalAcceptanceRecord(Base):
    __tablename__ = "legal_acceptances"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    terms_version: Mapped[str] = mapped_column(String(64))
    risk_version: Mapped[str] = mapped_column(String(64))
    privacy_version: Mapped[str] = mapped_column(String(64))
    content_sha256: Mapped[str] = mapped_column(String(64))
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    purpose: Mapped[str] = mapped_column(String(64), default="account_creation")

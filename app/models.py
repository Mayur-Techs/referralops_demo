"""SQLAlchemy persistence models.

Canonical schema used by every Matrix360 tool:
- Mayur: database / API (this file)
- Avinash: chat intake
- Tanmayi: WhatsApp outreach
- Pratha: fit scoring
- Abhinav: Radar / Apollo lead import

Rule: ALL additions are additive (nullable or with a default).
The app still works against the old SQLite if columns are missing —
old rows simply read as None for new nullable fields.

New normalized columns for 3-step deduplication (phone-last-10 → email → linkedin).
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _extract_digits(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\D", "", value)


def normalize_phone_last10(phone: str | None) -> str | None:
    """Return last 10 digits for comparison; None if fewer than 10 digits present.

    Never matches empty/None against empty/None.
    """
    digits = _extract_digits(phone)
    if len(digits) >= 10:
        return digits[-10:]
    return None


def normalize_email_key(email: str | None) -> str | None:
    """Trim + lowercase email; None for empty."""
    if not email:
        return None
    cleaned = email.strip().lower()
    return cleaned or None


def normalize_linkedin_key(url: str | None) -> str | None:
    """Strip scheme/www/trailing-slash/query from LinkedIn URL for key comparison.

    Returns None if URL is empty or does not contain 'linkedin'.
    """
    if not url:
        return None
    val = url.strip().lower()
    if "linkedin" not in val:
        return None
    # Remove scheme
    val = re.sub(r"^https?://(www\.)?", "", val)
    # Remove trailing slash and query
    val = val.split("?")[0].rstrip("/")
    return val or None


# ---------------------------------------------------------------------------
# base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Partner
# ---------------------------------------------------------------------------

class Partner(Base):
    __tablename__ = "partners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # New optional field — nullable so old DB rows still load without migration
    is_approved_broker: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Lead  (canonical shared record)
# ---------------------------------------------------------------------------

class Lead(Base):
    """One canonical lead row shared by all Matrix360 tools.

    Existing columns are unchanged; new columns are nullable or have defaults
    so that existing database rows continue to work.
    """
    __tablename__ = "leads"

    # ------------------------------------------------------------------
    # Primary key
    # ------------------------------------------------------------------
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # ------------------------------------------------------------------
    # Matrix360 shared canonical fields (new, all nullable / with defaults)
    # ------------------------------------------------------------------
    client: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    property_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    lead_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    source: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)

    # linkedin
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Ownership / next action
    owner: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    next_action: Mapped[str | None] = mapped_column(String(255), nullable=True)
    next_action_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Marketing attribution
    utm_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Intent (hot / warm / cold)
    intent: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)

    # Stage (new / qualified / contacted / engaged / visit_booked / ...)
    stage: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)

    # fit_score + fit_reasons are exposed as aliases of score/score_reasons
    # (no separate columns; computed properties map them)

    # opted_out flag (separate from contact_consent withdrawal)
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Deduplication normalized keys (computed at write time)
    dedup_phone: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    dedup_email: Mapped[str | None] = mapped_column(String(254), nullable=True, index=True)
    dedup_linkedin: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)

    # ------------------------------------------------------------------
    # Existing core fields (unchanged)
    # ------------------------------------------------------------------
    primary_partner_id: Mapped[int | None] = mapped_column(
        ForeignKey("partners.id"), nullable=True
    )
    profile_id: Mapped[str] = mapped_column(String(40), default="industrial_land", nullable=False)
    company_name: Mapped[str] = mapped_column(String(180), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), index=True, nullable=False)
    phone: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    industry: Mapped[str] = mapped_column(String(40), nullable=False)
    business_requirements: Mapped[str] = mapped_column(Text, default="", nullable=False)
    plot_size_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    budget_inr: Mapped[float | None] = mapped_column(Float, nullable=True)
    timeline: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    is_decision_maker: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    site_visit_interest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    preferred_contact_channel: Mapped[str] = mapped_column(String(20), default="email", nullable=False)
    consent_to_share: Mapped[bool] = mapped_column(Boolean, nullable=False)
    contact_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_notice_version: Mapped[str] = mapped_column(String(64), nullable=False)
    consent_recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    attribution_disputed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    score_reasons: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    missing_fields: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="needs_info", nullable=False)
    approval_state: Mapped[str] = mapped_column(String(40), default="pending_review", nullable=False)
    ai_provider: Mapped[str] = mapped_column(String(40), default="not_run", nullable=False)
    ai_analysis_status: Mapped[str] = mapped_column(String(40), default="not_run", nullable=False)
    ai_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ai_fit_signal: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    ai_missing_info: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    follow_up_draft: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ai_concerns: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    # ------------------------------------------------------------------
    # Computed property aliases for canonical field names
    # ------------------------------------------------------------------
    @property
    def lead_id(self) -> str:
        return self.id

    @property
    def name(self) -> str:
        return self.contact_name

    @property
    def company(self) -> str:
        return self.company_name

    @property
    def consent(self) -> bool:
        return self.consent_to_share

    @property
    def fit_score(self) -> int:
        return self.score

    @property
    def fit_reasons(self) -> list:
        return self.score_reasons or []


# ---------------------------------------------------------------------------
# ReferralSubmission
# ---------------------------------------------------------------------------

class ReferralSubmission(Base):
    __tablename__ = "referral_submissions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_referral_submission_idempotency_key"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True, nullable=False)
    partner_id: Mapped[int | None] = mapped_column(ForeignKey("partners.id"), nullable=True)
    submitted_company_name: Mapped[str] = mapped_column(String(180), nullable=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duplicate_match_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="accepted", nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


# ---------------------------------------------------------------------------
# ApprovalEvent
# ---------------------------------------------------------------------------

class ApprovalEvent(Base):
    __tablename__ = "approval_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True, nullable=False)
    reviewer: Mapped[str] = mapped_column(String(120), nullable=False)
    decision: Mapped[str] = mapped_column(String(40), nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    draft_snapshot: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


# ---------------------------------------------------------------------------
# SiteVisit
# ---------------------------------------------------------------------------

class SiteVisit(Base):
    __tablename__ = "site_visits"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="requested", nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


# ---------------------------------------------------------------------------
# CommissionReview
# ---------------------------------------------------------------------------

class CommissionReview(Base):
    __tablename__ = "commission_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(40), default="pending_human_review", nullable=False
    )
    proposed_amount_inr: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


# ---------------------------------------------------------------------------
# AuditEvent
# ---------------------------------------------------------------------------

class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), default="lead", nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    actor: Mapped[str] = mapped_column(String(120), default="system", nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

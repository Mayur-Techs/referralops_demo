"""Request/response schemas for Matrix360 / ReferralOps.

Preserves the existing ReferralCreate / LeadAnalysis / ApprovalRequest /
SiteVisitCreate / SiteVisitUpdate / CommissionDecision /
ContactConsentWithdrawal shapes exactly so every current test and the
dashboard keep working.

Adds canonical Matrix360 shared schemas (LeadCreate / LeadResponse /
LeadListParams) alongside — not replacing — the existing ones.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ── type aliases used by existing code ──────────────────────────────────────
Industry = Literal["manufacturing", "warehousing", "logistics", "other"]
Timeline = Literal[
    "immediate", "within_3_months", "within_6_months", "within_12_months", "unknown"
]
Channel = Literal["email", "phone", "whatsapp"]
QualificationProfile = Literal["industrial_land", "generic_b2b_demo", "industrial", "flats", "plots"]

# ── new canonical type aliases ───────────────────────────────────────────────
PropertyType = Literal["industrial", "flats", "plots"]
LeadType = Literal["company", "buyer", "broker"]
IntentType = Literal["hot", "warm", "cold"]


# ── shared validators ────────────────────────────────────────────────────────

def _clean_email(value: str) -> str:
    value = value.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise ValueError("Enter a valid email address")
    return value


def _clean_phone(value: str) -> str:
    value = value.strip()
    plus = value.startswith("+")
    digits = re.sub(r"\D", "", value)
    if not 7 <= len(digits) <= 15:
        raise ValueError("Phone must contain 7 to 15 digits")
    return ("+" if plus else "") + digits


# ============================================================================
# EXISTING SCHEMAS — unchanged so all existing tests continue to pass
# ============================================================================

class ReferralCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    partner_code: str = Field(min_length=3, max_length=40)
    profile_id: QualificationProfile = "industrial_land"
    company_name: str = Field(min_length=2, max_length=180)
    contact_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=254)
    phone: str = Field(min_length=7, max_length=24)
    industry: Industry
    business_requirements: str = Field(default="", max_length=1000)
    plot_size_sqm: float | None = Field(default=None, gt=0, le=10_000_000)
    budget_inr: float | None = Field(default=None, gt=0, le=10_000_000_000_000)
    timeline: Timeline = "unknown"
    is_decision_maker: bool | None = None
    site_visit_interest: bool = False
    preferred_contact_channel: Channel = "email"
    consent_to_share: bool
    contact_consent: bool = False

    @field_validator("partner_code")
    @classmethod
    def normalise_partner_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("company_name", "contact_name", "business_requirements")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("email")
    @classmethod
    def normalise_email(cls, value: str) -> str:
        return _clean_email(value)

    @field_validator("phone")
    @classmethod
    def normalise_phone(cls, value: str) -> str:
        return _clean_phone(value)

    @field_validator("business_requirements")
    @classmethod
    def bound_requirements(cls, value: str) -> str:
        return value[:1000]


class LeadAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=600)
    sector_fit: Literal["high", "medium", "low", "unknown"]
    missing_info: list[str] = Field(max_length=10)
    follow_up_draft: str = Field(min_length=1, max_length=1200)
    concerns: list[str] = Field(max_length=10)


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve_follow_up", "hold", "reject"]
    reviewer: str = Field(min_length=2, max_length=120)
    notes: str = Field(default="", max_length=1000)


class SiteVisitCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requested_by: str = Field(min_length=2, max_length=120)
    notes: str = Field(default="", max_length=1000)


class SiteVisitUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["scheduled", "completed", "cancelled"]
    scheduled_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_schedule_time(self):
        if self.status == "scheduled" and self.scheduled_at is None:
            raise ValueError("scheduled_at is required when scheduling a visit")
        return self


class CommissionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approved_for_payout", "held", "rejected"]
    reviewer: str = Field(min_length=2, max_length=120)
    proposed_amount_inr: float | None = Field(default=None, gt=0, le=1_000_000_000)
    notes: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def amount_required_for_approval(self):
        if self.decision == "approved_for_payout" and self.proposed_amount_inr is None:
            raise ValueError("A human-proposed amount is required for approval")
        return self


class ContactConsentWithdrawal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requested_by: str = Field(min_length=2, max_length=120)
    source: Literal["email", "phone", "web_form", "other"]
    evidence_reference: str = Field(min_length=3, max_length=200)


# ============================================================================
# NEW CANONICAL SCHEMAS for the shared Matrix360 lead format
# ============================================================================

VALID_SOURCES = {
    "radar", "referral", "broker", "chat", "ad", "apollo",
    "landing_page", "whatsapp", "crm_import", "manual",
}
VALID_CLIENTS = {"Lakhotia", "Shree Heights", "Vrindavan Greens", "demo"}
VALID_STAGES = {
    "new", "qualified", "contacted", "engaged", "visit_booked",
    "disqualified", "nurture", "visit_completed", "visit_cancelled",
    # existing statuses kept for backward compat
    "needs_info", "priority_review", "standard_review",
}


class LeadCreate(BaseModel):
    """Canonical Matrix360 lead create schema.

    Used by Avinash (chat), Tanmayi (WhatsApp), Abhinav (Radar/Apollo) and
    the referral endpoint adapter. All fields beyond the mandatory trio
    (name/company/phone-or-email) are optional so tools can submit partial
    data without synthetic fill-in.
    """
    model_config = ConfigDict(extra="ignore")  # tolerate extra tool-specific keys

    # Canonical Matrix360 fields
    client: str = Field(default="Lakhotia", max_length=80)
    property_type: PropertyType | None = None
    lead_type: LeadType | None = None
    source: str = Field(default="referral", max_length=40)
    evidence: str = Field(default="", max_length=2000)

    # Contact
    name: str = Field(min_length=2, max_length=120)
    company: str = Field(min_length=2, max_length=180)
    phone: str | None = Field(default=None, max_length=24)
    email: str | None = Field(default=None, max_length=254)
    linkedin_url: str | None = Field(default=None, max_length=500)

    # Consent
    consent: bool = Field(default=False)
    opted_out: bool = Field(default=False)

    # Ownership
    owner: str | None = Field(default=None, max_length=120)
    next_action: str | None = Field(default=None, max_length=255)
    next_action_date: datetime | None = None

    # Marketing
    utm_source: str | None = Field(default=None, max_length=100)
    utm_campaign: str | None = Field(default=None, max_length=100)

    # Qualification (optional, added when available)
    industry: Industry | None = None
    plot_size_sqm: float | None = Field(default=None, gt=0, le=10_000_000)
    budget_inr: float | None = Field(default=None, gt=0, le=10_000_000_000_000)
    timeline: Timeline | None = None
    is_decision_maker: bool | None = None
    site_visit_interest: bool = False
    business_requirements: str = Field(default="", max_length=1000)

    # Auth partner code (optional; used when coming through referral channel)
    partner_code: str | None = Field(default=None, max_length=40)

    @field_validator("name", "company", "evidence")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_email(value)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_phone(value)

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        v = value.strip().lower()
        if v not in VALID_SOURCES:
            # Accept but normalise; unknown sources are not rejected so new
            # tools aren't blocked by a code change requirement.
            return v
        return v

    @field_validator("client")
    @classmethod
    def validate_client(cls, value: str) -> str:
        v = value.strip()
        if v not in VALID_CLIENTS:
            raise ValueError(
                f"Unknown client '{v}'. Valid clients: {sorted(VALID_CLIENTS)}"
            )
        return v

    @model_validator(mode="after")
    def require_at_least_one_contact(self) -> "LeadCreate":
        if not self.phone and not self.email and not self.linkedin_url:
            raise ValueError(
                "At least one contact identifier (phone, email, or linkedin_url) is required"
            )
        return self


class LeadResponse(BaseModel):
    """Canonical JSON shape returned for a single lead.

    Maps model fields to the agreed Matrix360 field names.
    """
    model_config = ConfigDict(from_attributes=True)

    lead_id: str
    client: str | None
    property_type: str | None
    lead_type: str | None
    source: str | None
    evidence: str | None

    name: str
    company: str
    phone: str
    email: str
    linkedin_url: str | None

    consent: bool
    opted_out: bool

    fit_score: int
    fit_reasons: list
    intent: str | None
    stage: str | None

    owner: str | None
    next_action: str | None
    next_action_date: datetime | None

    utm_source: str | None
    utm_campaign: str | None

    # existing operational fields exposed for compatibility
    status: str
    approval_state: str
    ai_analysis_status: str
    ai_summary: str
    ai_fit_signal: str
    ai_missing_info: list
    follow_up_draft: str
    ai_concerns: list
    missing_fields: list
    score_reasons: list

    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_lead(cls, lead) -> "LeadResponse":
        return cls(
            lead_id=lead.id,
            client=lead.client,
            property_type=lead.property_type,
            lead_type=lead.lead_type,
            source=lead.source,
            evidence=lead.evidence,
            name=lead.contact_name,
            company=lead.company_name,
            phone=lead.phone,
            email=lead.email,
            linkedin_url=lead.linkedin_url,
            consent=lead.consent_to_share,
            opted_out=lead.opted_out,
            fit_score=lead.score,
            fit_reasons=lead.score_reasons or [],
            intent=lead.intent,
            stage=lead.stage or lead.status,
            owner=lead.owner,
            next_action=lead.next_action,
            next_action_date=lead.next_action_date,
            utm_source=lead.utm_source,
            utm_campaign=lead.utm_campaign,
            status=lead.status,
            approval_state=lead.approval_state,
            ai_analysis_status=lead.ai_analysis_status,
            ai_summary=lead.ai_summary,
            ai_fit_signal=lead.ai_fit_signal,
            ai_missing_info=lead.ai_missing_info or [],
            follow_up_draft=lead.follow_up_draft,
            ai_concerns=lead.ai_concerns or [],
            missing_fields=lead.missing_fields or [],
            score_reasons=lead.score_reasons or [],
            created_at=lead.created_at,
            updated_at=lead.updated_at,
        )


class LeadListParams(BaseModel):
    """Query parameters for GET /api/v1/leads with canonical filters."""
    model_config = ConfigDict(extra="ignore")

    q: str | None = Field(default=None, max_length=200, description="Free-text search across name, company, email, phone, evidence")
    client: str | None = Field(default=None, max_length=80)
    property_type: PropertyType | None = None
    source: str | None = Field(default=None, max_length=40)
    intent: IntentType | None = None
    stage: str | None = Field(default=None, max_length=40)
    owner: str | None = Field(default=None, max_length=120)
    status: str | None = Field(default=None, max_length=40)
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)

"""ReferralOps: local-first referral lead management prototype."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
from typing import Generator

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

import uuid
from .ai import AIProvider, AIProviderError, make_ai_provider, validate_analysis
from .config import Settings, get_settings
from .database import build_engine, initialise_database
from .models import (
    ApprovalEvent, AuditEvent, CommissionReview, Lead, Partner, ReferralSubmission, SiteVisit, utcnow,
    normalize_phone_last10, normalize_email_key, normalize_linkedin_key,
)
from .schemas import (
    ApprovalRequest, CommissionDecision, ContactConsentWithdrawal, LeadAnalysis,
    ReferralCreate, SiteVisitCreate, SiteVisitUpdate, LeadCreate, LeadResponse,
)
from .scoring import calculate_score
from .profiles import public_profiles, get_profile

STATIC_DIR = Path(__file__).parent / "static"


def _normalised_phone(phone: str) -> str:
    return "".join(ch for ch in phone if ch.isdigit())


def _payload_hash(payload: ReferralCreate) -> str:
    canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _generic_payload_hash(data: dict) -> str:
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def find_duplicate_lead(
    db: Session,
    phone: str | None,
    email: str | None,
    linkedin_url: str | None,
) -> tuple[Lead | None, str | None]:
    """Find duplicate lead in exact priority order:
    1. Phone (comparing last 10 digits if >= 10 digits available)
    2. Email (normalised: lowercased, trimmed)
    3. LinkedIn URL (canonicalized path)
    Never matches empty/missing values against each other.
    Returns (matched_lead, match_reason) or (None, None).
    """
    # 1. Phone match (last 10 digits)
    phone_10 = normalize_phone_last10(phone)
    if phone_10:
        lead = db.scalar(
            select(Lead).where(
                or_(
                    Lead.dedup_phone == phone_10,
                    Lead.phone.endswith(phone_10),
                )
            ).order_by(Lead.created_at.asc())
        )
        if lead:
            return lead, "matched_phone_last_10"

    # 2. Email match (normalised)
    email_key = normalize_email_key(email)
    if email_key:
        lead = db.scalar(
            select(Lead).where(
                or_(
                    Lead.dedup_email == email_key,
                    func.lower(Lead.email) == email_key,
                )
            ).order_by(Lead.created_at.asc())
        )
        if lead:
            return lead, "matched_email"

    # 3. LinkedIn match (canonicalized path)
    linkedin_key = normalize_linkedin_key(linkedin_url)
    if linkedin_key:
        lead = db.scalar(
            select(Lead).where(
                or_(
                    Lead.dedup_linkedin == linkedin_key,
                    Lead.linkedin_url.contains(linkedin_key),
                )
            ).order_by(Lead.created_at.asc())
        )
        if lead:
            return lead, "matched_linkedin"

    return None, None


def _lead_data_for_ai(lead: Lead) -> dict:
    """Send only qualification-relevant fields, not direct contact identifiers."""
    return {
        "profile_id": lead.profile_id,
        "industry": lead.industry,
        "business_requirements": lead.business_requirements,
        "plot_size_sqm": lead.plot_size_sqm,
        "budget_inr": lead.budget_inr,
        "timeline": lead.timeline,
        "is_decision_maker": lead.is_decision_maker,
        "site_visit_interest": lead.site_visit_interest,
    }


def _lead_dict(lead: Lead) -> dict:
    return {
        # Canonical shared fields (Matrix360 exact field names)
        "lead_id": lead.id,
        "client": lead.client or "Lakhotia",
        "property_type": lead.property_type or "industrial",
        "lead_type": lead.lead_type or "buyer",
        "source": lead.source or "referral",
        "evidence": lead.evidence or "",
        "name": lead.contact_name,
        "company": lead.company_name,
        "phone": lead.phone,
        "email": lead.email,
        "linkedin_url": lead.linkedin_url,
        "consent": lead.consent_to_share,
        "opted_out": lead.opted_out,
        "fit_score": lead.score,
        "fit_reasons": lead.score_reasons or [],
        "intent": lead.intent or "cold",
        "stage": lead.stage or lead.status,
        "owner": lead.owner,
        "next_action": lead.next_action,
        "next_action_date": lead.next_action_date.isoformat() if lead.next_action_date else None,
        "utm_source": lead.utm_source,
        "utm_campaign": lead.utm_campaign,

        # Legacy & detailed qualification fields (preserved for existing routes & dashboard)
        "id": lead.id,
        "primary_partner_id": lead.primary_partner_id,
        "profile_id": lead.profile_id,
        "company_name": lead.company_name,
        "contact_name": lead.contact_name,
        "industry": lead.industry,
        "business_requirements": lead.business_requirements,
        "plot_size_sqm": lead.plot_size_sqm,
        "budget_inr": lead.budget_inr,
        "timeline": lead.timeline,
        "is_decision_maker": lead.is_decision_maker,
        "site_visit_interest": lead.site_visit_interest,
        "preferred_contact_channel": lead.preferred_contact_channel,
        "consent_to_share": lead.consent_to_share,
        "contact_consent": lead.contact_consent,
        "consent_notice_version": lead.consent_notice_version,
        "consent_recorded_at": lead.consent_recorded_at.isoformat() if lead.consent_recorded_at else None,
        "attribution_disputed": lead.attribution_disputed,
        "score": lead.score,
        "score_reasons": lead.score_reasons or [],
        "missing_fields": lead.missing_fields or [],
        "status": lead.status,
        "approval_state": lead.approval_state,
        "ai_provider": lead.ai_provider,
        "ai_analysis_status": lead.ai_analysis_status,
        "ai_summary": lead.ai_summary,
        "ai_fit_signal": lead.ai_fit_signal,
        "ai_missing_info": lead.ai_missing_info or [],
        "follow_up_draft": lead.follow_up_draft,
        "ai_concerns": lead.ai_concerns or [],
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
    }


def _submission_dict(submission: ReferralSubmission, lead: Lead, replay: bool = False) -> dict:
    # Public intake responses never expose direct contact identifiers, including on first submission.
    public_lead = (
        {"id": lead.id, "status": "duplicate_review", "attribution_disputed": lead.attribution_disputed,
         "contact_details_hidden": True}
        if submission.is_duplicate else {
            "id": lead.id, "company_name": lead.company_name, "profile_id": lead.profile_id, "industry": lead.industry,
            "score": lead.score, "score_reasons": lead.score_reasons or [], "missing_fields": lead.missing_fields or [],
            "status": lead.status, "approval_state": lead.approval_state, "ai_provider": lead.ai_provider,
            "ai_analysis_status": lead.ai_analysis_status, "ai_summary": lead.ai_summary, "ai_fit_signal": lead.ai_fit_signal,
            "ai_missing_info": lead.ai_missing_info or [], "follow_up_draft": lead.follow_up_draft,
            "ai_concerns": lead.ai_concerns or [], "contact_details_hidden": True,
        }
    )
    return {
        "submission_id": submission.id,
        "lead_id": lead.id,
        "is_duplicate": submission.is_duplicate,
        "submission_status": submission.status,
        "idempotent_replay": replay,
        "message": (
            "Existing prospect matched. Original attribution was preserved; review the new referral claim. Contact details are not disclosed in this response."
            if submission.is_duplicate else
            "Referral saved. Any AI output is an assistive draft and requires human review before contact."
        ),
        "lead": public_lead,
    }


def _record_audit(db: Session, event_type: str, entity_id: str, actor: str = "system",
                  entity_type: str = "lead", details: dict | None = None) -> None:
    """Queue a minimal audit event in the current DB transaction; avoid storing lead PII in audit details."""
    db.add(AuditEvent(event_type=event_type, entity_type=entity_type, entity_id=entity_id,
                      actor=actor[:120], details=details or {}))


def _apply_analysis(lead: Lead, provider: AIProvider) -> None:
    lead.ai_provider = provider.name
    try:
        analysis = validate_analysis(provider.analyze(_lead_data_for_ai(lead)))
        lead.ai_analysis_status = "ready"
        lead.ai_summary = analysis.summary
        lead.ai_fit_signal = analysis.sector_fit
        lead.ai_missing_info = analysis.missing_info
        lead.follow_up_draft = analysis.follow_up_draft
        lead.ai_concerns = analysis.concerns
    except Exception as exc:  # Provider failures must not lose the stored referral.
        lead.ai_analysis_status = "failed_manual_review"
        lead.ai_summary = "AI analysis is unavailable or failed validation. Review the submitted fields manually."
        lead.ai_fit_signal = "unknown"
        lead.ai_missing_info = []
        lead.follow_up_draft = ""
        # Keep a short, bounded diagnostic for known guard/provider errors; never log request payloads or secrets.
        diagnostic = str(exc)[:160] if isinstance(exc, AIProviderError) else type(exc).__name__
        lead.ai_concerns = [f"Analysis failure: {diagnostic}; no external message was sent."]


def create_app(
    database_url: str | None = None,
    settings: Settings | None = None,
    ai_provider: AIProvider | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    url = database_url or settings.database_url
    engine = build_engine(url)
    initialise_database(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    provider = ai_provider or make_ai_provider(settings)

    app = FastAPI(
        title="ReferralOps API",
        version="0.1.0",
        description=(
            "Prototype for referral intake, deterministic lead qualification, AI-assisted drafts, "
            "human approvals, site-visit tracking and commission review. External messaging and payouts are disabled."
        ),
    )
    app.state.engine = engine
    app.state.session_factory = SessionLocal
    app.state.settings = settings
    app.state.ai_provider = provider

    def get_db() -> Generator[Session, None, None]:
        with SessionLocal() as db:
            yield db

    def require_admin(x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")) -> None:
        expected = settings.admin_api_key
        if not x_admin_key or not hmac.compare_digest(x_admin_key, expected):
            raise HTTPException(status_code=401, detail="Valid X-Admin-Key header required")

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/health", tags=["system"])
    def health():
        return {"status": "ok", "service": "referralops", "database": "configured"}

    @app.get("/api/v1/config", tags=["system"])
    def public_config():
        provider_name = provider.name
        return {
            "service": "ReferralOps",
            "ai_provider": provider_name,
            "ai_mode": "demo" if provider_name == "demo_rules" else "external_api",
            "outbound_messaging_enabled": False,
            "commission_payouts_enabled": False,
            "disclaimer": "Demo scoring weights and commission milestones are not company-approved policies.",
        }

    @app.get("/api/v1/profiles", tags=["qualification"])
    def qualification_profiles():
        return public_profiles()

    @app.post("/api/v1/referrals", status_code=status.HTTP_201_CREATED, tags=["referrals"])
    def create_referral(
        payload: ReferralCreate,
        db: Session = Depends(get_db),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128),
    ):
        # This gate runs before partner lookup or persistence, so a no-consent payload is not stored.
        if payload.consent_to_share is not True:
            raise HTTPException(status_code=422, detail="Consent to share/process this referral is required; no record was stored")
        if get_profile(payload.profile_id) is None:
            raise HTTPException(status_code=422, detail="Unknown qualification profile")

        partner = db.scalar(select(Partner).where(Partner.code == payload.partner_code, Partner.active.is_(True)))
        if not partner:
            raise HTTPException(status_code=422, detail="Unknown or inactive referral partner code")

        digest = _payload_hash(payload)
        if idempotency_key:
            existing_submission = db.scalar(select(ReferralSubmission).where(ReferralSubmission.idempotency_key == idempotency_key))
            if existing_submission:
                if existing_submission.payload_hash != digest:
                    raise HTTPException(status_code=409, detail="Idempotency-Key was already used with a different payload")
                existing_lead = db.get(Lead, existing_submission.lead_id)
                _record_audit(db, "referral.idempotency_replay", existing_lead.id, actor=partner.code,
                              details={"submission_id": existing_submission.id})
                db.commit()
                return _submission_dict(existing_submission, existing_lead, replay=True)

        normalised_phone = _normalised_phone(payload.phone)
        # Check duplicate using 3-step priority: phone last 10 digits -> email -> linkedin
        existing_lead, match_reason = find_duplicate_lead(db, payload.phone, payload.email, None)
        if not existing_lead:
            # Fallback check for exact raw phone / raw email
            normalised_phone = _normalised_phone(payload.phone)
            existing_lead = db.scalar(
                select(Lead).where(or_(Lead.email == payload.email, Lead.phone == normalised_phone, Lead.phone == payload.phone)).order_by(Lead.created_at.asc())
            )
            if existing_lead:
                match_reason = "matched_email_or_phone"

        if existing_lead:
            # Preserve the first attribution. The second partner's claim is recorded, not overwritten.
            different_partner = existing_lead.primary_partner_id != partner.id
            existing_lead.attribution_disputed = existing_lead.attribution_disputed or different_partner
            submission = ReferralSubmission(
                lead_id=existing_lead.id,
                partner_id=partner.id,
                submitted_company_name=payload.company_name,
                is_duplicate=True,
                duplicate_match_reason=match_reason,
                status="duplicate_review",
                idempotency_key=idempotency_key,
                payload_hash=digest,
            )
            db.add(submission)
            db.flush()
            _record_audit(db, "referral.duplicate_claimed", existing_lead.id, actor=partner.code,
                          details={"submission_id": submission.id, "attribution_disputed": bool(existing_lead.attribution_disputed),
                                   "match_reason": match_reason})
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise HTTPException(status_code=409, detail="Could not safely save duplicate submission; retry with a new idempotency key") from exc
            db.refresh(submission)
            db.refresh(existing_lead)
            return _submission_dict(submission, existing_lead)

        normalised_phone = _normalised_phone(payload.phone)
        score_result = calculate_score(payload.model_dump(), profile_id=payload.profile_id)
        lead = Lead(
            client="Lakhotia",
            property_type="industrial",
            lead_type="buyer",
            source="referral",
            evidence=f"Referral by partner {partner.code}",
            primary_partner_id=partner.id,
            profile_id=payload.profile_id,
            company_name=payload.company_name,
            contact_name=payload.contact_name,
            email=payload.email,
            phone=normalised_phone,
            dedup_phone=normalize_phone_last10(payload.phone),
            dedup_email=normalize_email_key(payload.email),
            industry=payload.industry,
            business_requirements=payload.business_requirements,
            plot_size_sqm=payload.plot_size_sqm,
            budget_inr=payload.budget_inr,
            timeline=payload.timeline,
            is_decision_maker=payload.is_decision_maker,
            site_visit_interest=payload.site_visit_interest,
            preferred_contact_channel=payload.preferred_contact_channel,
            consent_to_share=payload.consent_to_share,
            contact_consent=payload.contact_consent,
            consent_notice_version=settings.consent_notice_version,
            score=score_result.score,
            score_reasons=score_result.reasons,
            missing_fields=score_result.missing_fields,
            status=score_result.status,
            intent=score_result.intent,
            stage="new",
        )
        db.add(lead)
        db.flush()
        submission = ReferralSubmission(
            lead_id=lead.id,
            partner_id=partner.id,
            submitted_company_name=payload.company_name,
            is_duplicate=False,
            status="accepted",
            idempotency_key=idempotency_key,
            payload_hash=digest,
        )
        db.add(submission)
        db.flush()
        _record_audit(db, "referral.accepted", lead.id, actor=partner.code,
                      details={"submission_id": submission.id, "profile_id": lead.profile_id})
        try:
            db.commit()  # Persist first; a provider outage cannot erase the lead.
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail="Could not safely save referral. Check the idempotency key and retry.") from exc

        db.refresh(lead)
        db.refresh(submission)
        _apply_analysis(lead, provider)
        _record_audit(db, "ai.analysis.ready" if lead.ai_analysis_status == "ready" else "ai.analysis.failed", lead.id,
                      actor=provider.name, details={"provider": lead.ai_provider, "state": lead.ai_analysis_status})
        lead.updated_at = utcnow()
        db.commit()
        db.refresh(lead)
        return _submission_dict(submission, lead)

    @app.post("/api/v1/leads", status_code=status.HTTP_201_CREATED, tags=["leads"])
    def create_lead(
        payload: LeadCreate,
        db: Session = Depends(get_db),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128),
    ):
        """Canonical Matrix360 lead creation endpoint.
        Used by Avinash (chat), Shalini (landing page), Abhinav (Radar), etc.
        Enforces 3-step deduplication: phone (last 10 digits) -> email -> linkedin URL.
        """
        digest = _generic_payload_hash(payload.model_dump(mode="json"))
        if idempotency_key:
            existing_submission = db.scalar(
                select(ReferralSubmission).where(ReferralSubmission.idempotency_key == idempotency_key)
            )
            if existing_submission:
                if existing_submission.payload_hash != digest:
                    raise HTTPException(status_code=409, detail="Idempotency-Key was already used with a different payload")
                existing_lead = db.get(Lead, existing_submission.lead_id)
                _record_audit(db, "lead.idempotency_replay", existing_lead.id, actor="api",
                              details={"submission_id": existing_submission.id})
                db.commit()
                return {
                    "lead_id": existing_lead.id,
                    "is_duplicate": existing_submission.is_duplicate,
                    "idempotent_replay": True,
                    "lead": _lead_dict(existing_lead),
                }

        # Deduplication in exact priority order: Phone last 10 -> Email -> LinkedIn URL
        duplicate_lead, match_reason = find_duplicate_lead(
            db, payload.phone, payload.email, payload.linkedin_url
        )

        if duplicate_lead:
            # Preserve original attribution. Link duplicate claim safely.
            partner_id = None
            if payload.partner_code:
                partner = db.scalar(select(Partner).where(Partner.code == payload.partner_code))
                if partner:
                    partner_id = partner.id
                    if duplicate_lead.primary_partner_id and duplicate_lead.primary_partner_id != partner.id:
                        duplicate_lead.attribution_disputed = True

            submission = ReferralSubmission(
                lead_id=duplicate_lead.id,
                partner_id=partner_id,
                submitted_company_name=payload.company,
                is_duplicate=True,
                duplicate_match_reason=match_reason,
                status="duplicate_review",
                idempotency_key=idempotency_key,
                payload_hash=digest,
            )
            db.add(submission)
            db.flush()
            _record_audit(
                db, "lead.duplicate_matched", duplicate_lead.id, actor=payload.source or "api",
                details={"match_reason": match_reason, "submission_id": submission.id}
            )
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise HTTPException(status_code=409, detail="Could not safely save duplicate lead; retry.") from exc
            db.refresh(duplicate_lead)
            return {
                "lead_id": duplicate_lead.id,
                "is_duplicate": True,
                "duplicate_match_reason": match_reason,
                "message": f"Existing lead matched by {match_reason}. Original attribution preserved.",
                "lead": _lead_dict(duplicate_lead),
            }

        # New Lead
        score_data = {
            "industry": payload.industry or "other",
            "plot_size_sqm": payload.plot_size_sqm,
            "budget_inr": payload.budget_inr,
            "timeline": payload.timeline or "unknown",
            "is_decision_maker": payload.is_decision_maker,
            "site_visit_interest": payload.site_visit_interest,
        }
        score_profile = payload.property_type or "industrial"
        score_result = calculate_score(score_data, profile_id=score_profile)

        partner_id = None
        if payload.partner_code:
            partner = db.scalar(select(Partner).where(Partner.code == payload.partner_code, Partner.active.is_(True)))
            if partner:
                partner_id = partner.id

        lead = Lead(
            client=payload.client or "Lakhotia",
            property_type=payload.property_type or "industrial",
            lead_type=payload.lead_type or "buyer",
            source=payload.source or "referral",
            evidence=payload.evidence or "",
            company_name=payload.company,
            contact_name=payload.name,
            email=payload.email or f"unknown_{uuid.uuid4().hex[:8]}@lead.local",
            phone=payload.phone or "",
            linkedin_url=payload.linkedin_url,
            dedup_phone=normalize_phone_last10(payload.phone),
            dedup_email=normalize_email_key(payload.email),
            dedup_linkedin=normalize_linkedin_key(payload.linkedin_url),
            consent_to_share=payload.consent,
            contact_consent=payload.consent,
            opted_out=payload.opted_out,
            consent_notice_version=settings.consent_notice_version,
            score=score_result.score,
            score_reasons=score_result.reasons,
            missing_fields=score_result.missing_fields,
            status=score_result.status,
            intent=score_result.intent,
            stage="new",
            owner=payload.owner,
            next_action=payload.next_action,
            next_action_date=payload.next_action_date,
            utm_source=payload.utm_source,
            utm_campaign=payload.utm_campaign,
            primary_partner_id=partner_id,
            industry=payload.industry or "other",
            business_requirements=payload.business_requirements or "",
            plot_size_sqm=payload.plot_size_sqm,
            budget_inr=payload.budget_inr,
            timeline=payload.timeline or "unknown",
            is_decision_maker=payload.is_decision_maker,
            site_visit_interest=payload.site_visit_interest,
            preferred_contact_channel="email" if not payload.phone else "phone",
        )
        db.add(lead)
        db.flush()

        submission = ReferralSubmission(
            lead_id=lead.id,
            partner_id=partner_id,
            submitted_company_name=payload.company,
            is_duplicate=False,
            status="accepted",
            idempotency_key=idempotency_key,
            payload_hash=digest,
        )
        db.add(submission)
        db.flush()
        _record_audit(db, "lead.created", lead.id, actor=payload.source or "api",
                      details={"submission_id": submission.id, "source": lead.source})
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail="Could not safely save lead. Check the idempotency key and retry.") from exc

        db.refresh(lead)
        _apply_analysis(lead, provider)
        lead.updated_at = utcnow()
        db.commit()
        db.refresh(lead)

        return {
            "lead_id": lead.id,
            "is_duplicate": False,
            "message": "Lead saved successfully in central database.",
            "lead": _lead_dict(lead),
        }

    @app.get("/api/v1/partners", tags=["referrals"], dependencies=[Depends(require_admin)])
    def list_partners(db: Session = Depends(get_db)):
        partners = db.scalars(select(Partner).order_by(Partner.id)).all()
        return [{"id": p.id, "code": p.code, "display_name": p.display_name, "active": p.active} for p in partners]

    @app.get("/api/v1/leads", tags=["leads"], dependencies=[Depends(require_admin)])
    def list_leads(
        status_filter: str | None = Query(default=None, alias="status"),
        client: str | None = Query(default=None),
        property_type: str | None = Query(default=None),
        source: str | None = Query(default=None),
        intent: str | None = Query(default=None),
        stage: str | None = Query(default=None),
        owner: str | None = Query(default=None),
        q: str | None = Query(default=None, description="Search across name, company, email, phone, evidence"),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        db: Session = Depends(get_db),
    ):
        query = select(Lead)
        if status_filter:
            query = query.where(Lead.status == status_filter)
        if client:
            query = query.where(Lead.client == client)
        if property_type:
            query = query.where(Lead.property_type == property_type)
        if source:
            query = query.where(Lead.source == source)
        if intent:
            query = query.where(Lead.intent == intent)
        if stage:
            query = query.where(or_(Lead.stage == stage, Lead.status == stage))
        if owner:
            query = query.where(Lead.owner == owner)
        if q:
            term = f"%{q.strip()}%"
            query = query.where(
                or_(
                    Lead.company_name.ilike(term),
                    Lead.contact_name.ilike(term),
                    Lead.email.ilike(term),
                    Lead.phone.ilike(term),
                    Lead.evidence.ilike(term),
                    Lead.linkedin_url.ilike(term),
                )
            )
        query = query.order_by(Lead.created_at.desc()).offset(offset).limit(limit)
        return [_lead_dict(lead) for lead in db.scalars(query).all()]

    @app.get("/api/v1/leads/{lead_id}", tags=["leads"], dependencies=[Depends(require_admin)])
    def get_lead(lead_id: str, db: Session = Depends(get_db)):
        lead = db.get(Lead, lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        submissions = db.scalars(select(ReferralSubmission).where(ReferralSubmission.lead_id == lead_id).order_by(ReferralSubmission.submitted_at)).all()
        approvals = db.scalars(select(ApprovalEvent).where(ApprovalEvent.lead_id == lead_id).order_by(ApprovalEvent.created_at)).all()
        visits = db.scalars(select(SiteVisit).where(SiteVisit.lead_id == lead_id).order_by(SiteVisit.created_at)).all()
        commission = db.scalar(select(CommissionReview).where(CommissionReview.lead_id == lead_id))
        audit_events = db.scalars(select(AuditEvent).where(AuditEvent.entity_type == "lead", AuditEvent.entity_id == lead_id).order_by(AuditEvent.created_at)).all()
        result = _lead_dict(lead)
        result["referral_history"] = [
            {"submission_id": s.id, "partner_id": s.partner_id, "submitted_company_name": s.submitted_company_name,
             "is_duplicate": s.is_duplicate, "status": s.status, "submitted_at": s.submitted_at.isoformat()}
            for s in submissions
        ]
        result["approval_history"] = [
            {"reviewer": a.reviewer, "decision": a.decision, "notes": a.notes, "draft_snapshot": a.draft_snapshot, "created_at": a.created_at.isoformat()}
            for a in approvals
        ]
        result["site_visits"] = [_site_visit_dict(v) for v in visits]
        result["commission_review"] = _commission_dict(commission) if commission else None
        result["audit_history"] = [_audit_dict(event) for event in audit_events]
        return result

    @app.post("/api/v1/leads/{lead_id}/reanalyze", tags=["AI analysis"], dependencies=[Depends(require_admin)])
    def reanalyze_lead(lead_id: str, db: Session = Depends(get_db)):
        lead = db.get(Lead, lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        previous_approval_state = lead.approval_state
        _apply_analysis(lead, provider)
        # A regenerated draft is a new artifact: a previous approval must never carry over.
        lead.approval_state = "pending_review"
        _record_audit(db, "ai.analysis.ready" if lead.ai_analysis_status == "ready" else "ai.analysis.failed", lead.id,
                      actor=provider.name, details={"provider": lead.ai_provider, "state": lead.ai_analysis_status,
                      "trigger": "manual_reanalysis", "previous_approval_state": previous_approval_state,
                      "approval_reset": True})
        lead.updated_at = utcnow()
        db.commit()
        db.refresh(lead)
        return {"lead_id": lead.id, "ai_provider": lead.ai_provider, "ai_analysis_status": lead.ai_analysis_status,
                "ai_summary": lead.ai_summary, "follow_up_draft": lead.follow_up_draft,
                "ai_concerns": lead.ai_concerns, "external_message_sent": False}

    @app.post("/api/v1/leads/{lead_id}/approval", tags=["approvals"], dependencies=[Depends(require_admin)])
    def review_follow_up(lead_id: str, payload: ApprovalRequest, db: Session = Depends(get_db)):
        lead = db.get(Lead, lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        if payload.decision == "approve_follow_up":
            if not lead.contact_consent:
                raise HTTPException(status_code=409, detail="Follow-up approval blocked: contact consent is not recorded")
            if lead.ai_analysis_status != "ready" or not lead.follow_up_draft:
                raise HTTPException(status_code=409, detail="Follow-up approval blocked: a validated draft is not available")
            lead.approval_state = "approved_for_follow_up"
        elif payload.decision == "hold":
            lead.approval_state = "held"
        else:
            lead.approval_state = "rejected"
        approved_snapshot = lead.follow_up_draft if payload.decision == "approve_follow_up" else ""
        event = ApprovalEvent(lead_id=lead.id, reviewer=payload.reviewer, decision=payload.decision,
                              notes=payload.notes, draft_snapshot=approved_snapshot)
        db.add(event)
        _record_audit(db, f"follow_up.{payload.decision}", lead.id, actor=payload.reviewer,
                      details={"approval_state": lead.approval_state,
                               "approved_draft_sha256": hashlib.sha256(approved_snapshot.encode("utf-8")).hexdigest() if approved_snapshot else None})
        lead.updated_at = utcnow()
        db.commit()
        db.refresh(lead)
        return {"lead_id": lead.id, "approval_state": lead.approval_state,
                "message": "Approval recorded. This prototype does not send external messages.", "lead": _lead_dict(lead)}

    @app.post("/api/v1/leads/{lead_id}/consent/withdraw-contact", tags=["consent"], dependencies=[Depends(require_admin)])
    def withdraw_contact_consent(lead_id: str, payload: ContactConsentWithdrawal, db: Session = Depends(get_db)):
        lead = db.get(Lead, lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        prior_consent = lead.contact_consent
        lead.contact_consent = False
        if lead.approval_state == "approved_for_follow_up":
            lead.approval_state = "held"
        _record_audit(db, "consent.contact_withdrawn", lead.id, actor=payload.requested_by,
                      details={"source": payload.source, "evidence_reference": payload.evidence_reference,
                               "previous_contact_consent": prior_consent, "approval_state": lead.approval_state})
        lead.updated_at = utcnow()
        db.commit()
        db.refresh(lead)
        return {"lead_id": lead.id, "contact_consent": lead.contact_consent, "approval_state": lead.approval_state,
                "message": "Contact permission withdrawn in the demo record. No outbound message was sent."}

    @app.post("/api/v1/leads/{lead_id}/site-visits", status_code=201, tags=["site visits"], dependencies=[Depends(require_admin)])
    def request_site_visit(lead_id: str, payload: SiteVisitCreate, db: Session = Depends(get_db)):
        lead = db.get(Lead, lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        visit = SiteVisit(lead_id=lead_id, status="requested", notes=f"Requested by {payload.requested_by}. {payload.notes}".strip())
        db.add(visit)
        db.flush()
        _record_audit(db, "site_visit.requested", lead_id, actor=payload.requested_by,
                      details={"visit_id": visit.id, "status": visit.status})
        db.commit()
        db.refresh(visit)
        return _site_visit_dict(visit)

    @app.patch("/api/v1/site-visits/{visit_id}", tags=["site visits"], dependencies=[Depends(require_admin)])
    def update_site_visit(visit_id: str, payload: SiteVisitUpdate, db: Session = Depends(get_db)):
        visit = db.get(SiteVisit, visit_id)
        if not visit:
            raise HTTPException(status_code=404, detail="Site visit not found")
        allowed_transitions = {
            "requested": {"scheduled", "cancelled"},
            "scheduled": {"completed", "cancelled"},
        }
        previous_status = visit.status
        if payload.status not in allowed_transitions.get(visit.status, set()):
            raise HTTPException(status_code=409, detail=f"Invalid site-visit transition: {visit.status} -> {payload.status}")
        if payload.status == "scheduled":
            scheduled_at = payload.scheduled_at
            if scheduled_at is None:
                raise HTTPException(status_code=422, detail="scheduled_at is required")
            if scheduled_at.tzinfo is None:
                scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
            if scheduled_at <= datetime.now(timezone.utc):
                raise HTTPException(status_code=422, detail="scheduled_at must be in the future")
            visit.scheduled_at = scheduled_at
        visit.status = payload.status
        if payload.notes is not None:
            visit.notes = (visit.notes + "\n" + payload.notes).strip()
        visit.updated_at = utcnow()
        _record_audit(db, f"site_visit.{payload.status}", visit.lead_id, actor="admin",
                      details={"visit_id": visit.id, "from_status": previous_status, "to_status": payload.status})
        db.commit()
        db.refresh(visit)
        return _site_visit_dict(visit)

    @app.post("/api/v1/leads/{lead_id}/commission/check", tags=["commission"], dependencies=[Depends(require_admin)])
    def check_commission(lead_id: str, db: Session = Depends(get_db)):
        lead = db.get(Lead, lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        completed_visit = db.scalar(select(SiteVisit).where(SiteVisit.lead_id == lead_id, SiteVisit.status == "completed"))
        reasons = []
        if completed_visit is None:
            reasons.append("No completed site visit is recorded.")
        if lead.attribution_disputed:
            reasons.append("Referral attribution is disputed and must be resolved.")
        if reasons:
            _record_audit(db, "commission.not_eligible", lead_id, actor="admin", details={"reason_count": len(reasons)})
            db.commit()
            return {"lead_id": lead_id, "eligible_for_human_review": False, "status": "not_eligible", "reasons": reasons,
                    "payout_executed": False}
        review = db.scalar(select(CommissionReview).where(CommissionReview.lead_id == lead_id))
        if review is None:
            review = CommissionReview(lead_id=lead_id, status="pending_human_review")
            db.add(review)
            db.flush()
        _record_audit(db, "commission.eligibility_checked", lead_id, actor="admin",
                      details={"review_status": review.status})
        db.commit()
        db.refresh(review)
        return {"lead_id": lead_id, "eligible_for_human_review": True, "status": review.status,
                "reasons": ["A completed site visit is recorded; company policy and partner agreement still require human verification."],
                "commission_review": _commission_dict(review), "payout_executed": False}

    @app.post("/api/v1/leads/{lead_id}/commission/review", tags=["commission"], dependencies=[Depends(require_admin)])
    def review_commission(lead_id: str, payload: CommissionDecision, db: Session = Depends(get_db)):
        lead = db.get(Lead, lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        review = db.scalar(select(CommissionReview).where(CommissionReview.lead_id == lead_id))
        if review is None or review.status != "pending_human_review":
            raise HTTPException(status_code=409, detail="Run commission eligibility check first; only pending reviews can be decided")
        if payload.decision == "approved_for_payout":
            completed = db.scalar(select(SiteVisit).where(SiteVisit.lead_id == lead_id, SiteVisit.status == "completed"))
            if completed is None or lead.attribution_disputed:
                raise HTTPException(status_code=409, detail="Commission approval blocked by missing visit evidence or disputed attribution")
            review.proposed_amount_inr = payload.proposed_amount_inr
        review.status = payload.decision
        review.reviewer = payload.reviewer
        review.notes = payload.notes
        review.updated_at = utcnow()
        _record_audit(db, f"commission.{payload.decision}", lead_id, actor=payload.reviewer,
                      details={"review_status": review.status, "amount_proposed": review.proposed_amount_inr is not None})
        db.commit()
        db.refresh(review)
        return {"lead_id": lead_id, "commission_review": _commission_dict(review),
                "payout_executed": False, "message": "Review state saved only; no payment or transfer was initiated."}

    @app.get("/api/v1/kpis", tags=["reporting"], dependencies=[Depends(require_admin)])
    def kpis(db: Session = Depends(get_db)):
        total_submissions = db.scalar(select(func.count()).select_from(ReferralSubmission)) or 0
        unique_leads = db.scalar(select(func.count()).select_from(Lead)) or 0
        duplicates = db.scalar(select(func.count()).select_from(ReferralSubmission).where(ReferralSubmission.is_duplicate.is_(True))) or 0
        qualified = db.scalar(select(func.count()).select_from(Lead).where(Lead.status.in_(["priority_review", "standard_review"]))) or 0
        completed_lead_ids = set(db.scalars(select(SiteVisit.lead_id).where(SiteVisit.status == "completed")).all())
        ai_failed = db.scalar(select(func.count()).select_from(Lead).where(Lead.ai_analysis_status == "failed_manual_review")) or 0
        pending_approvals = db.scalar(select(func.count()).select_from(Lead).where(Lead.approval_state == "pending_review")) or 0
        pending_commission = db.scalar(select(func.count()).select_from(CommissionReview).where(CommissionReview.status == "pending_human_review")) or 0
        valid_lead_rate = round(unique_leads / total_submissions * 100, 1) if total_submissions else 0.0
        conversion = round(len(completed_lead_ids) / qualified * 100, 1) if qualified else 0.0
        return {
            "total_referral_submissions": total_submissions,
            "unique_leads": unique_leads,
            "duplicate_submissions": duplicates,
            "valid_lead_rate_pct": valid_lead_rate,
            "qualified_inquiries": qualified,
            "completed_site_visit_leads": len(completed_lead_ids),
            "site_visit_conversion_pct": conversion,
            "leads_pending_approval": pending_approvals,
            "ai_failures_needing_review": ai_failed,
            "commission_reviews_pending": pending_commission,
            "definition_note": "Prototype KPIs; validate definitions with the business owner before operational use.",
        }

    @app.get("/api/v1/audit", tags=["audit"], dependencies=[Depends(require_admin)])
    def recent_audit_events(limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)):
        events = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)).all()
        return [_audit_dict(event) for event in events]

    return app


def _audit_dict(event: AuditEvent) -> dict:
    return {"id": event.id, "event_type": event.event_type, "entity_type": event.entity_type,
            "entity_id": event.entity_id, "actor": event.actor, "details": event.details or {},
            "created_at": event.created_at.isoformat()}


def _site_visit_dict(visit: SiteVisit) -> dict:
    return {"id": visit.id, "lead_id": visit.lead_id, "status": visit.status,
            "scheduled_at": visit.scheduled_at.isoformat() if visit.scheduled_at else None,
            "notes": visit.notes, "created_at": visit.created_at.isoformat(),
            "updated_at": visit.updated_at.isoformat()}


def _commission_dict(review: CommissionReview) -> dict:
    return {"id": review.id, "lead_id": review.lead_id, "status": review.status,
            "proposed_amount_inr": review.proposed_amount_inr, "reviewer": review.reviewer,
            "notes": review.notes, "created_at": review.created_at.isoformat(),
            "updated_at": review.updated_at.isoformat()}


app = create_app()

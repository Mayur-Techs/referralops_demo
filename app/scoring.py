"""Explainable deterministic scoring driven by separate JSON configuration profiles.

Unchanged from original except: ScoreResult now includes intent and intent_reasons
fields (with backward-compatible defaults) to support the hot/warm/cold rule.
"""
from dataclasses import dataclass, field
from typing import Literal

from .profiles import get_profile

IntentType = Literal["hot", "warm", "cold"]


@dataclass(frozen=True)
class ScoreResult:
    score: int
    status: str
    reasons: list[str]
    missing_fields: list[str]
    intent: IntentType = "cold"
    intent_reasons: list[str] = field(default_factory=list)


def _determine_intent(data: dict, score: int) -> tuple[IntentType, list[str]]:
    """Shared hot/warm/cold rule (coordinated across Matrix360 tools).

    HOT  → site-visit explicitly requested  OR  immediate timeline  OR
           (budget stated + decision-maker confirmed + score ≥ 70)
    WARM → timeline within_3_months / within_6_months  OR
           budget/size stated  OR  score ≥ 50
    COLD → everything else
    """
    timeline = str(data.get("timeline", "unknown")).lower()
    site_visit = bool(data.get("site_visit_interest"))
    has_budget = data.get("budget_inr") is not None
    is_dm = data.get("is_decision_maker") is True
    reasons: list[str] = []

    if site_visit:
        reasons.append("Hot: site-visit interest explicitly stated.")
        return "hot", reasons
    if timeline == "immediate":
        reasons.append("Hot: immediate decision timeline.")
        return "hot", reasons
    if has_budget and is_dm and score >= 70:
        reasons.append(f"Hot: decision-maker + budget + score {score}/100.")
        return "hot", reasons

    if timeline in {"within_3_months", "within_6_months"}:
        reasons.append(f"Warm: purchase timeline {timeline.replace('_', ' ')}.")
        return "warm", reasons
    if has_budget or data.get("plot_size_sqm") is not None:
        reasons.append("Warm: concrete budget or area requirement stated.")
        return "warm", reasons
    if score >= 50:
        reasons.append(f"Warm: qualification score {score}/100.")
        return "warm", reasons

    reasons.append("Cold: research stage, missing timeline/budget, or score < 50.")
    return "cold", reasons


def calculate_score(data: dict, profile_id: str = "industrial_land") -> ScoreResult:
    """Score explicit fields only; the LLM never sets a score or overrides consent gates."""
    profile = get_profile(profile_id)
    if profile is None:
        raise ValueError(f"Unknown qualification profile: {profile_id}")
    weights = profile["weights"]
    score = 0
    reasons: list[str] = []
    missing: list[str] = []

    industry = data.get("industry", "other")
    if industry in profile["accepted_industries"]:
        industry_points = weights["industry_fit"]
        score += industry_points
        reasons.append(f"Industry is accepted by profile '{profile_id}' (+{industry_points}).")
    else:
        industry_points = weights["other_industry"]
        score += industry_points
        reasons.append(
            f"Industry fit needs human confirmation under profile '{profile_id}' (+{industry_points})."
        )

    if data.get("plot_size_sqm") is not None:
        score += weights["plot_size_sqm"]
        reasons.append(f"Space requirement is stated (+{weights['plot_size_sqm']}).")
    else:
        missing.append("plot_size_sqm")
        reasons.append("Space requirement is missing (0 points; clarification needed).")

    if data.get("budget_inr") is not None:
        score += weights["budget_inr"]
        reasons.append(f"Budget or project-scale range is stated (+{weights['budget_inr']}).")
    else:
        missing.append("budget_inr")
        reasons.append("Budget or project-scale range is missing (0 points; clarification needed).")

    timeline = data.get("timeline", "unknown")
    timeline_score = weights["timeline"].get(timeline, 0)
    score += timeline_score
    if timeline_score:
        reasons.append(f"Purchase timeline is stated (+{timeline_score}).")
    else:
        missing.append("timeline")
        reasons.append("Purchase timeline is unknown (0 points; clarification needed).")

    decision_maker = data.get("is_decision_maker")
    if decision_maker is True:
        decision_points = weights["decision_maker"]
        score += decision_points
        reasons.append(
            f"Contact reports decision-making authority (+{decision_points}; verify in sales conversation)."
        )
    elif decision_maker is False:
        decision_points = weights["non_decision_maker"]
        score += decision_points
        reasons.append(f"Contact may be an influencer rather than final decision-maker (+{decision_points}).")
    else:
        missing.append("is_decision_maker")
        reasons.append("Decision-making role needs clarification (0 points).")

    if data.get("site_visit_interest"):
        score += weights["site_visit_interest"]
        reasons.append(f"Site-visit interest is stated (+{weights['site_visit_interest']}).")
    else:
        reasons.append("No site-visit interest is currently stated (0 points).")

    score = max(0, min(100, score))
    if any(field in missing for field in profile["clarification_fields"]):
        status = "needs_info"
    elif score >= profile["thresholds"]["priority_review"]:
        status = "priority_review"
    elif score >= profile["thresholds"]["standard_review"]:
        status = "standard_review"
    else:
        status = "nurture"

    intent, intent_reasons = _determine_intent(data, score)

    return ScoreResult(
        score=score,
        status=status,
        reasons=reasons,
        missing_fields=missing,
        intent=intent,
        intent_reasons=intent_reasons,
    )

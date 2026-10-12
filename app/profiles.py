"""Read-only qualification profiles stored as configuration, separate from route code."""
import json
from pathlib import Path
from typing import Any

PROFILE_PATH = Path(__file__).parent / "industry_profiles.json"
with PROFILE_PATH.open("r", encoding="utf-8") as file:
    INDUSTRY_PROFILES: dict[str, dict[str, Any]] = json.load(file)


def get_profile(profile_id: str) -> dict[str, Any] | None:
    return INDUSTRY_PROFILES.get(profile_id)


def public_profiles() -> list[dict[str, Any]]:
    return [
        {"id": profile_id, "display_name": profile["display_name"], "purpose": profile["purpose"],
         "accepted_industries": profile["accepted_industries"], "thresholds": profile["thresholds"]}
        for profile_id, profile in INDUSTRY_PROFILES.items()
    ]

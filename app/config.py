"""Environment-backed configuration for the Matrix360 / ReferralOps app."""
from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./referralops.db")
    admin_api_key: str = os.getenv("ADMIN_API_KEY", "demo-admin-key")
    ai_provider: str = os.getenv("AI_PROVIDER", "demo").strip().lower()

    # xAI / Grok
    xai_api_key: str = os.getenv("XAI_API_KEY", os.getenv("GROQ_API_Key", ""))
    xai_model: str = os.getenv("XAI_MODEL", "grok-beta")
    xai_timeout_seconds: float = float(os.getenv("XAI_TIMEOUT_SECONDS", "15"))

    # OpenAI (optional)
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_timeout_seconds: float = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "15"))

    consent_notice_version: str = os.getenv("CONSENT_NOTICE_VERSION", "referralops-demo-v1")


def get_settings() -> Settings:
    """Return a settings snapshot, useful for an app created in tests."""
    return Settings()

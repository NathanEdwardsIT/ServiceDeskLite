from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    app_name: str = "Help Desk Ticketing System"
    database_url: str = f"sqlite:///{DATA_DIR / 'helpdesk.db'}"
    secret_key: str = "dev-secret-change-in-production"
    session_cookie: str = "helpdesk_session"

    # SLA targets in minutes by priority
    sla_critical_minutes: int = 60
    sla_high_minutes: int = 240
    sla_medium_minutes: int = 480
    sla_low_minutes: int = 1440

    # Duplicate detection similarity threshold (0-1)
    duplicate_similarity_threshold: float = 0.72


settings = Settings()

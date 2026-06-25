"""Pydantic Settings - cau hinh tap trung, doc tu .env."""
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    LOCATION_COOLDOWN_EPISODES: int = 3
    SIMILARITY_THRESHOLD: float = 0.70
    # FIX #6: Nguong tuyet doi tu choi - neu similarity cao hon nay sau khi
    # fallback, audit se tra ve "rejected_high_similarity" de caller biet
    # nen retry thay vi gui script chat luong kem cho Showrunner.
    SIMILARITY_HARD_REJECT_THRESHOLD: float = 0.92
    AUDITOR_MAX_RETRY: int = 3
    RESOURCE_LOCK_MAX_CONCURRENT: int = 2
    RESOURCE_LOCK_MAX_RAM_PERCENT: float = 75.0
    FFMPEG_THREADS: int = 2
    FFMPEG_CRF: int = 28
    FFMPEG_PRESET: str = "veryfast"
    # FIX #2: Timeout cho Showrunner (default 24 gio).
    # Truoc day wait_for_showrunner() khong co timeout -> pipeline co the
    # treo vinh vien neu Showrunner khong phan hoi.
    SHOWRUNNER_TIMEOUT_HOURS: float = 24.0

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

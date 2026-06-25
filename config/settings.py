"""Pydantic Settings - cau hinh tap trung, doc tu .env."""
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    LOCATION_COOLDOWN_EPISODES: int = 3
    SIMILARITY_THRESHOLD: float = 0.70
    AUDITOR_MAX_RETRY: int = 3
    RESOURCE_LOCK_MAX_CONCURRENT: int = 2
    RESOURCE_LOCK_MAX_RAM_PERCENT: float = 75.0
    FFMPEG_THREADS: int = 2
    FFMPEG_CRF: int = 28
    FFMPEG_PRESET: str = "veryfast"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

"""Cấu hình toàn cục cho Project Chimera (V4.0 Phase-1 fix).

Thay đổi so với bản zip cũ:
- ``elevenlabs_keys``: collect 6 key ELEVENLABS_KEY1..6 (fallback ELEVENLABS_API_KEY).
- ``assets_dir`` + glitch transition path.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def _b(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in ("1", "true", "yes")


def _collect_gemini_keys() -> List[str]:
    keys: List[str] = []
    for i in range(1, 8):
        v = os.getenv(f"GEMINI_API_KEY{i}", "").strip()
        if v: keys.append(v)
    if not keys:
        legacy = os.getenv("GEMINI_API_KEY", "").strip()
        if legacy: keys = [legacy]
    return keys


def _collect_elevenlabs_keys() -> List[str]:
    """Gom 6 ELEVENLABS_KEY1..6 (rỗng -> bỏ). Fallback ELEVENLABS_API_KEY."""
    keys: List[str] = []
    for i in range(1, 7):
        v = os.getenv(f"ELEVENLABS_KEY{i}", "").strip()
        if v: keys.append(v)
    if not keys:
        legacy = os.getenv("ELEVENLABS_API_KEY", "").strip()
        if legacy: keys = [legacy]
    return keys


def _collect_mongo_uris() -> Tuple[str, str, str]:
    u1 = os.getenv("MONGODB_URL_NO1", "").strip()
    u2 = os.getenv("MONGODB_URL_NO2", "").strip()
    u3 = os.getenv("MONGODB_URL_NO3", "").strip()
    legacy = os.getenv("MONGO_URI", "").strip()
    return (u1 or legacy, u2 or legacy, u3 or legacy)


_PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    # ===== LLM =====
    gemini_keys: tuple = field(default_factory=lambda: tuple(_collect_gemini_keys()))
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    gemini_sayhi_timeout: int = 8
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = "llama-3.1-70b-versatile"
    max_output_tokens: int = 8192

    # ===== Image =====
    hf_token: str = os.getenv("HF_TOKEN", "")
    pollinations_url: str = "https://image.pollinations.ai/prompt/{prompt}?seed={seed}&nologo=true&width=1024&height=1920"
    pollinations_timeout: int = 20
    hf_model: str = "stabilityai/stable-diffusion-xl-base-1.0"

    # ===== TTS =====
    elevenlabs_keys: tuple = field(default_factory=lambda: tuple(_collect_elevenlabs_keys()))
    # giữ lại để code cũ không vỡ; nhưng renderer mới dùng rotator
    elevenlabs_api_key: str = os.getenv("ELEVENLABS_API_KEY", "")
    elevenlabs_monthly_quota: int = 10_000
    edge_voice: str = os.getenv("EDGE_VOICE", "vi-VN-NamMinhNeural")
    gtts_lang: str = "vi"

    # ===== Assets tĩnh =====
    assets_dir: Path = _PROJECT_ROOT / "assets"
    glitch_transition_path: Path = _PROJECT_ROOT / "assets" / "glitch_transition.mp4"

    # ===== Mongo =====
    mongo_uris: tuple = field(default_factory=lambda: _collect_mongo_uris())
    mongo_db_inputs: str = os.getenv("MONGO_DB_INPUTS", "chimera_inputs")
    mongo_db_scripts: str = os.getenv("MONGO_DB_SCRIPTS", "chimera_scripts")
    mongo_db_history: str = os.getenv("MONGO_DB_HISTORY", "chimera_history")
    mongo_pool: int = 6
    purgatory_ttl_seconds: int = 3 * 24 * 3600
    history_keep: int = 50

    # ===== Telegram =====
    bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    webhook_secret: str = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    telegram_size_limit_mb: int = 50

    # ===== FFmpeg =====
    video_width: int = 1080
    video_height: int = 1920
    video_crf: int = 28
    video_preset: str = "veryfast"
    ffmpeg_timeout_sec: int = 300

    # ===== Runtime =====
    debug_mode: bool = _b("DEBUG_MODE", False)
    scenes_per_episode: int = 15      # Phase-1: 15 phân cảnh (Scene 1 = video user)
    debug_scenes: int = 3
    max_workers: int = 4
    monte_carlo_branches: int = 20
    top_k_branches: int = 3
    soft_timeout_sec: int = 25 * 60

    retry_budget: Dict[str, int] = field(default_factory=lambda: {
        "json_error": 3, "duplicate": 4, "content_filter": 3, "total": 10,
    })

    anh_t_dup_threshold: float = 0.78
    anh_t_max_dup_retries: int = 3

    drama_weights: Dict[str, float] = field(default_factory=lambda: {
        "w1_delta_power": 0.4, "w2_betrayal": 0.35, "w3_max_loss": 0.25,
    })
    max_revives_per_episode: int = 2

    silence_padding_sec: float = 0.3
    bgm_volume_ratio: float = 0.25

    jitter_min_ms: int = 200
    jitter_max_ms: int = 900

    # Feature flags
    enable_t_checker: bool = _b("ENABLE_T_CHECKER", True)
    enable_context_mapper: bool = _b("ENABLE_CONTEXT_MAPPER", True)
    enable_glitch_curse: bool = _b("ENABLE_GLITCH_CURSE", True)
    enable_seed_lock: bool = _b("ENABLE_SEED_LOCK", True)
    enable_purgatory_watch: bool = _b("ENABLE_PURGATORY_WATCH", True)
    enable_meta_layer: bool = _b("ENABLE_META_LAYER", False)
    enable_soft_reboot: bool = _b("ENABLE_SOFT_REBOOT", False)
    enable_spinoff: bool = _b("ENABLE_SPINOFF", False)
    enable_plot_armor: bool = _b("ENABLE_PLOT_ARMOR", False)
    enable_co_creation: bool = _b("ENABLE_CO_CREATION", False)

    # V4.1
    enable_video_brief: bool = _b("ENABLE_VIDEO_BRIEF", True)
    enable_comic_sfx: bool = _b("ENABLE_COMIC_SFX", True)
    enable_transitions: bool = _b("ENABLE_TRANSITIONS", True)
    enable_ken_burns: bool = _b("ENABLE_KEN_BURNS", False)
    motion_scenes: tuple = (1, 4, 7)
    motion_fps: int = 15

    budget_llm_calls_hard_cap: int = 50
    budget_usd_hard_cap: float = 3.0
    budget_pool: Dict[str, int] = field(default_factory=lambda: {
        "T2_monte_carlo": 10, "T3_director": 6,
        "T2_3_t_checker": 4, "T3_5_compliance": 6,
    })
    budget_cost_table: Dict[str, float] = field(default_factory=lambda: {
        "T2": 0.02, "T3": 0.15, "T2_3": 0.02, "T3_5": 0.05,
    })

    t_checker_repetition_threshold: float = 0.85
    t_checker_novelty_threshold: float = 0.15
    t_checker_history_window: int = 50
    purgatory_warning_hours_before: int = 12
    soft_reboot_interval_episodes: int = 100
    entropy_reboot_threshold: int = 80


settings = Settings()
SCENES = settings.debug_scenes if settings.debug_mode else settings.scenes_per_episode

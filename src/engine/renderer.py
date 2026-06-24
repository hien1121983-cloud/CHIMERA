"""Renderer — sinh media song song.

V4.0 PHASE-1 FIX
================
- BỎ QUA sinh ảnh Scene 1 (do người dùng tự cung cấp video clip).
- Chỉ sinh ảnh tĩnh từ Scene 2 đến Scene N.
- TTS: dùng ``ElevenLabsRotator`` (6 key xoay vòng). Khi cạn cả 6 key, tự động
  fallback sang edge-tts → gTTS, TUYỆT ĐỐI không crash pipeline.
"""
from __future__ import annotations
import asyncio
import random
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Optional
from PIL import Image
from io import BytesIO
from ..config import settings
from ..utils import get_logger, jitter_sleep, retry
from . import seed_lock
from . import comic_overlay
from .elevenlabs_client import get_rotator, QuotaAllExhausted

log = get_logger("renderer")

UNSAFE_RE = re.compile(r"\b(blood|gore|kill|murder|weapon|gun|knife|nude|sex)\b", re.IGNORECASE)


def _sanitize_prompt(p: str) -> str:
    return UNSAFE_RE.sub("intense", p)


# ---------- Image ----------

def _pollinations(prompt: str, out: Path, seed: int | None = None) -> None:
    if seed is None:
        seed = random.randint(1, 10_000_000)
    url = settings.pollinations_url.format(
        prompt=requests.utils.quote(prompt),
        seed=seed,
    )
    r = requests.get(url, timeout=settings.pollinations_timeout)
    r.raise_for_status()
    img = Image.open(BytesIO(r.content)).convert("RGB")
    img.save(out, "JPEG", quality=80, optimize=True)


def _huggingface(prompt: str, out: Path) -> None:
    if not settings.hf_token:
        raise RuntimeError("HF_TOKEN missing")
    url = f"https://api-inference.huggingface.co/models/{settings.hf_model}"
    headers = {"Authorization": f"Bearer {settings.hf_token}"}
    r = requests.post(url, headers=headers, json={"inputs": prompt}, timeout=60)
    r.raise_for_status()
    img = Image.open(BytesIO(r.content)).convert("RGB")
    img.save(out, "JPEG", quality=80, optimize=True)


def render_image(prompt: str, out: Path, seed: int | None = None) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    safe = _sanitize_prompt(prompt)
    jitter_sleep()
    try:
        retry(lambda: _pollinations(safe, out, seed=seed), attempts=2, label="pollinations")
        return out
    except Exception as e:
        log.warning("pollinations fail: %s — fallback HF", e)
    retry(lambda: _huggingface(safe, out), attempts=2, label="hf")
    return out


# ---------- TTS ----------

async def _edge_tts(text: str, out: Path) -> None:
    import edge_tts
    communicate = edge_tts.Communicate(text, settings.edge_voice)
    await communicate.save(str(out))


def _gtts(text: str, out: Path) -> None:
    from gtts import gTTS
    gTTS(text=text, lang=settings.gtts_lang).save(str(out))


def render_voice(text: str, out: Path, *, prefer_eleven: bool = False) -> Path:
    """TTS chiến lược:
        - ``prefer_eleven=True`` (hook / CTA): thử ElevenLabs trước (xoay 6 key);
          khi ``QuotaAllExhausted`` -> fallback edge-tts -> gTTS.
        - ``prefer_eleven=False`` (scene thường): edge-tts -> gTTS.
    KHÔNG bao giờ raise nếu còn ít nhất 1 engine free hoạt động.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    jitter_sleep()

    if prefer_eleven:
        rot = get_rotator()
        if rot.total > 0 and not rot.all_exhausted():
            try:
                return rot.synth(text, out)
            except QuotaAllExhausted as e:
                log.warning("ElevenLabs cạn quota toàn bộ %d key -> fallback edge-tts: %s",
                            rot.total, e)
            except Exception as e:
                log.warning("ElevenLabs lỗi không mong đợi -> fallback edge-tts: %s", e)

    # Edge-TTS
    try:
        asyncio.run(_edge_tts(text, out))
        return out
    except Exception as e:
        log.warning("edge-tts fail: %s — fallback gTTS", e)
    # gTTS
    try:
        _gtts(text, out)
        return out
    except Exception as e:
        log.error("gTTS fail: %s", e)
    raise RuntimeError("Tất cả TTS engine đều fail.")


# ---------- Batch ----------

def render_all(script: dict, out_dir: Path, **_ignored) -> Dict[str, List[Path]]:
    """Sinh batch:
        - Ảnh: Scene 2..N (Scene 1 BỎ QUA — chờ user upload .mp4).
        - Audio: tất cả scene.
        - Overlays comic SFX: tất cả scene (PIL nhẹ).

    Trả về dict gồm cả mảng images (Scene 1 = None) và voices.
    """
    img_dir = out_dir / "images"
    voi_dir = out_dir / "voices"
    sfx_dir = out_dir / "sfx_overlays"
    img_dir.mkdir(parents=True, exist_ok=True)
    voi_dir.mkdir(parents=True, exist_ok=True)

    scenes = script["scenes"]
    images: List[Optional[Path]] = [None] * len(scenes)
    voices: List[Optional[Path]] = [None] * len(scenes)
    overlays: List[Optional[Path]] = [None] * len(scenes)

    # ---- Scene 1: KHÔNG sinh ảnh, chỉ ghi prompt video cho user ----
    s1 = scenes[0] if scenes else {}
    hook_prompt = (s1.get("cinematic_video_prompt") or "").strip()
    if hook_prompt:
        try:
            (out_dir / "scene_01_cinematic_video_prompt.txt").write_text(
                hook_prompt, encoding="utf-8"
            )
            log.info("Đã ghi scene_01_cinematic_video_prompt.txt (%d ký tự).",
                     len(hook_prompt))
        except Exception as e:
            log.warning("Ghi cinematic_video_prompt fail: %s", e)
    else:
        log.warning("Scene 1 thiếu cinematic_video_prompt — kịch bản LLM có vấn đề.")

    # ---- Images: chỉ scene 2..N ----
    with ThreadPoolExecutor(max_workers=settings.max_workers) as pool:
        futs = {}
        for i, s in enumerate(scenes):
            if i == 0:
                continue   # Scene 1 do user cung cấp video
            if "image_prompt" not in s:
                log.warning("Scene %d thiếu image_prompt — bỏ qua.", i + 1)
                continue
            seed = None
            prompt = s["image_prompt"]
            if settings.enable_seed_lock:
                primary = s.get("primary_character") or {}
                if primary:
                    seed = seed_lock.get_stable_seed(primary)
                    prompt = f"[SEED:{seed}] consistent_face, {prompt}"
            futs[pool.submit(render_image, prompt,
                             img_dir / f"scene_{i+1:02d}.jpg", seed)] = i
        for f in as_completed(futs):
            i = futs[f]
            try:
                images[i] = f.result()
            except Exception as e:
                log.error("scene %d image fail: %s", i + 1, e)
                images[i] = img_dir / f"scene_{i+1:02d}.jpg"   # rỗng, ffmpeg sẽ skip

    # ---- Comic SFX overlays ----
    if settings.enable_comic_sfx:
        for i, s in enumerate(scenes):
            try:
                overlays[i] = comic_overlay.render_overlay(
                    s.get("sfx_tag", "calm"),
                    (settings.video_width, settings.video_height),
                    sfx_dir / f"scene_{i+1:02d}_sfx.png",
                    comic_text=s.get("comic_text"),
                )
            except Exception as e:
                log.warning("scene %d sfx overlay fail: %s", i + 1, e)

    # ---- Voices ----
    n = len(scenes)
    for i, s in enumerate(scenes):
        prefer = (i == 0) or (i == n - 1)   # Hook + CTA ưu tiên ElevenLabs
        try:
            voices[i] = render_voice(
                s.get("dialogue", ""),
                voi_dir / f"scene_{i+1:02d}.mp3",
                prefer_eleven=prefer,
            )
        except Exception as e:
            log.error("scene %d voice fail: %s", i + 1, e)
            voices[i] = voi_dir / f"scene_{i+1:02d}.mp3"

    return {"images": images, "voices": voices, "overlays": overlays}

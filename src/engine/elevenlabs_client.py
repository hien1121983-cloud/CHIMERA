"""ElevenLabs Round-Robin client.

Quản trị ngân sách: dùng 6 key Free luân phiên (ELEVENLABS_KEY1..6).
- Khi key hiện tại hết quota (HTTP 401 / 429) -> mark dead, xoay sang key kế.
- Cạn cả 6 key -> raise QuotaAllExhausted để renderer fallback edge-tts.
- KHÔNG bao giờ crash luồng sản xuất.
"""
from __future__ import annotations
import threading
from pathlib import Path
from typing import List, Optional
import requests
from ..config import settings
from ..utils import get_logger

log = get_logger("elevenlabs")


class QuotaAllExhausted(RuntimeError):
    """Tất cả key ElevenLabs đều hết quota / bị chặn."""


class ElevenLabsRotator:
    """Round-robin pool cho ElevenLabs TTS."""

    DEFAULT_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"   # Bella (free tier)
    DEFAULT_MODEL = "eleven_multilingual_v2"
    BASE_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}"
    # Mã lỗi đồng nghĩa "key này hết hoặc bị chặn" -> phải xoay
    DEAD_STATUS = {401, 402, 403, 429}

    def __init__(self, keys: Optional[List[str]] = None,
                 voice_id: Optional[str] = None,
                 model_id: Optional[str] = None):
        keys = keys if keys is not None else list(settings.elevenlabs_keys)
        # loại bỏ key rỗng / trùng
        seen = set()
        self._keys: List[str] = []
        for k in keys:
            k = (k or "").strip()
            if k and k not in seen:
                seen.add(k)
                self._keys.append(k)
        self._dead: set[str] = set()
        self._cursor = 0
        self._lock = threading.Lock()
        self.voice_id = voice_id or self.DEFAULT_VOICE_ID
        self.model_id = model_id or self.DEFAULT_MODEL
        log.info("ElevenLabs Rotator khởi tạo với %d key.", len(self._keys))

    # ---------- introspection ----------
    @property
    def total(self) -> int: return len(self._keys)

    @property
    def alive(self) -> List[str]:
        return [k for k in self._keys if k not in self._dead]

    def all_exhausted(self) -> bool:
        return not self.alive

    # ---------- core ----------
    def _next_key(self) -> Optional[str]:
        with self._lock:
            n = len(self._keys)
            for _ in range(n):
                k = self._keys[self._cursor % n]
                self._cursor += 1
                if k not in self._dead:
                    return k
        return None

    def _mark_dead(self, key: str, reason: str = "") -> None:
        with self._lock:
            self._dead.add(key)
        log.warning("ElevenLabs key …%s bị loại (%s). Còn %d/%d key sống.",
                    key[-6:], reason, len(self.alive), self.total)

    def synth(self, text: str, out: Path,
              voice_id: Optional[str] = None,
              model_id: Optional[str] = None,
              timeout: int = 30) -> Path:
        """Gọi TTS, tự xoay key khi gặp lỗi quota. Raise QuotaAllExhausted khi cạn."""
        if not text or not text.strip():
            raise ValueError("Text rỗng.")
        if self.all_exhausted():
            raise QuotaAllExhausted("Tất cả ElevenLabs key đã hết quota.")

        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        url = self.BASE_URL.format(voice=voice_id or self.voice_id)
        payload = {"text": text, "model_id": model_id or self.model_id}

        attempts = 0
        last_error: Optional[str] = None
        # Mỗi lượt chỉ thử mỗi key đúng 1 lần để tránh vòng lặp vô tận
        while attempts < self.total:
            key = self._next_key()
            if key is None:
                break
            attempts += 1
            headers = {
                "xi-api-key": key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            }
            try:
                r = requests.post(url, headers=headers, json=payload, timeout=timeout)
            except requests.RequestException as e:
                last_error = f"network:{e}"
                log.warning("ElevenLabs network fail (key …%s): %s", key[-6:], e)
                # lỗi mạng — không mark dead, thử key kế
                continue

            if r.status_code == 200 and r.content:
                out.write_bytes(r.content)
                log.info("TTS OK bằng ElevenLabs key …%s (%d bytes).",
                         key[-6:], len(r.content))
                return out

            # Quota / auth fail -> mark dead và xoay
            if r.status_code in self.DEAD_STATUS:
                last_error = f"http_{r.status_code}"
                self._mark_dead(key, reason=last_error)
                continue

            # Lỗi server tạm thời 5xx — không mark dead, thử key kế
            if 500 <= r.status_code < 600:
                last_error = f"server_{r.status_code}"
                log.warning("ElevenLabs 5xx (key …%s) -> thử key kế.", key[-6:])
                continue

            # Lỗi khác (4xx ngoài dead-list): kết thúc luôn vì không phải vấn đề quota
            last_error = f"http_{r.status_code}:{r.text[:200]}"
            log.error("ElevenLabs lỗi không-quota %s: %s", r.status_code, r.text[:200])
            raise RuntimeError(f"ElevenLabs error: {last_error}")

        # Hết key sống
        raise QuotaAllExhausted(
            f"Đã thử {attempts} key ElevenLabs, tất cả lỗi quota. last={last_error}"
        )


# Singleton dùng chung cho toàn pipeline
_rotator: Optional[ElevenLabsRotator] = None


def get_rotator() -> ElevenLabsRotator:
    global _rotator
    if _rotator is None:
        _rotator = ElevenLabsRotator()
    return _rotator

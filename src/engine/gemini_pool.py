"""Gemini Key Pool — 7 API key, xoay tour theo scene.

- Trước khi xoay vào ca làm việc, MỖI key "say hi" để kiểm tra tình trạng.
- Key nào hỏng (timeout / 401 / quota) sẽ bị loại khỏi pool cho tới lần khởi động sau.
- Mỗi scene được giao cho 1 key duy nhất (round-robin theo scene index).
- Nếu key bị lỗi khi đang làm việc -> rotate sang key kế tiếp còn sống.
"""
from __future__ import annotations
import json
import threading
from typing import List, Optional
from ..config import settings
from ..utils import get_logger

log = get_logger("gemini_pool")

_lock = threading.Lock()
_alive_keys: Optional[List[str]] = None  # cache sau lần say-hi đầu tiên


def _gen_config(json_mode: bool = True, max_tokens: int | None = None):
    cfg = {
        "max_output_tokens": max_tokens or settings.max_output_tokens,
        "temperature": 0.9,
    }
    if json_mode:
        cfg["response_mime_type"] = "application/json"
    return cfg


def _say_hi(key: str) -> bool:
    """Ping 1 prompt cực ngắn. True nếu key sống & quota còn."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
        model = genai.GenerativeModel(
            settings.gemini_model,
            generation_config={"max_output_tokens": 16, "temperature": 0.0},
        )
        resp = model.generate_content("Say: hi")
        ok = bool((getattr(resp, "text", "") or "").strip())
        return ok
    except Exception as e:
        log.warning("say_hi fail (key …%s): %s", key[-6:], e)
        return False


def ensure_pool(force: bool = False) -> List[str]:
    """Kiểm tra sức khỏe 7 key 1 lần / process. Trả về danh sách key còn sống."""
    global _alive_keys
    with _lock:
        if _alive_keys is not None and not force:
            return _alive_keys
        configured = list(settings.gemini_keys)
        if not configured:
            log.error("Không có GEMINI_API_KEY1..7 nào được cấu hình.")
            _alive_keys = []
            return _alive_keys
        alive: List[str] = []
        for i, k in enumerate(configured, 1):
            ok = _say_hi(k)
            log.info("Gemini key #%d (…%s): %s", i, k[-6:], "ALIVE" if ok else "DEAD")
            if ok:
                alive.append(k)
        if not alive:
            log.error("Tất cả 7 Gemini key đều DEAD sau say-hi.")
        _alive_keys = alive
        return _alive_keys


def key_for_scene(scene_index: int) -> str:
    """Round-robin: scene 1 -> key 1, scene 8 -> key 1 (lặp lại). 0-indexed."""
    alive = ensure_pool()
    if not alive:
        raise RuntimeError("Gemini pool rỗng — không thể sinh kịch bản.")
    return alive[scene_index % len(alive)]


def generate_json(key: str, prompt: str, max_tokens: int | None = None) -> dict:
    """Gọi 1 lần Gemini với key cụ thể, parse JSON."""
    import google.generativeai as genai
    genai.configure(api_key=key)
    model = genai.GenerativeModel(
        settings.gemini_model,
        generation_config=_gen_config(json_mode=True, max_tokens=max_tokens),
    )
    resp = model.generate_content(prompt)
    text = (getattr(resp, "text", "") or "").strip()
    return json.loads(text)


def mark_dead(key: str) -> None:
    """Loại key khỏi pool nếu nó liên tục lỗi trong runtime."""
    global _alive_keys
    with _lock:
        if _alive_keys and key in _alive_keys:
            _alive_keys.remove(key)
            log.warning("Đã loại key …%s khỏi pool (còn %d).", key[-6:], len(_alive_keys))

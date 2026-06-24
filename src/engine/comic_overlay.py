"""Comic SFX Overlay — render PNG trong suốt cho tượng thanh (PIL).

- Đọc mapping tag -> {text, color, size} từ ``data/sfx_comic_map.json``.
- Cho phép override bằng ``comic_text`` do LLM sinh ra (ưu tiên hơn ``sfx_tag``).
- Sinh PNG RGBA xoay nhẹ -15..+15°, có viền đen để nổi trên mọi nền ảnh.

Module độc lập: chỉ phụ thuộc PIL (đã có trong requirements). FFmpeg sẽ overlay
PNG này lên video qua filter ``overlay`` (enable=lt(t,1.2)).
"""
from __future__ import annotations
import json
import random
from pathlib import Path
from typing import Optional, Dict, Tuple
from PIL import Image, ImageDraw, ImageFont

from ..config import settings
from ..utils import get_logger

log = get_logger("comic_sfx")

_DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "sfx_comic_map.json"
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/impact.ttf",
]


def _load_map() -> Dict[str, dict]:
    try:
        return json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("load sfx map fail: %s", e)
        return {}


_MAP = _load_map()


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def resolve_text(sfx_tag: str, comic_text: Optional[str] = None) -> Optional[dict]:
    """LLM ``comic_text`` ưu tiên hơn map tag; trả về None khi không cần overlay."""
    if comic_text and comic_text.strip():
        return {"text": comic_text.strip()[:24], "color": "#FFD700", "size": 150}
    cfg = _MAP.get(sfx_tag)
    if not cfg:
        return None
    return cfg


def render_overlay(sfx_tag: str, canvas_size: Tuple[int, int], out: Path,
                   comic_text: Optional[str] = None) -> Optional[Path]:
    """Sinh PNG trong suốt. Trả về path nếu thành công, None nếu skip."""
    if not settings.enable_comic_sfx:
        return None
    cfg = resolve_text(sfx_tag, comic_text)
    if not cfg:
        return None
    text = cfg["text"]
    color = cfg.get("color", "#FFFFFF")
    size = int(cfg.get("size", 130))

    pad = size  # khoảng đệm để xoay không bị clip
    img = Image.new("RGBA", (canvas_size[0], int(canvas_size[1] * 0.4)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _font(size)
    try:
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=6)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
    except Exception:
        tw, th = font.getsize(text) if hasattr(font, "getsize") else (size * len(text), size)
    x = (img.width - tw) // 2
    y = (img.height - th) // 2
    try:
        draw.text((x, y), text, font=font, fill=color,
                  stroke_width=6, stroke_fill="#000000")
    except TypeError:
        # fallback cho PIL cũ không có stroke
        for dx in (-2, 0, 2):
            for dy in (-2, 0, 2):
                draw.text((x + dx, y + dy), text, font=font, fill="#000000")
        draw.text((x, y), text, font=font, fill=color)

    rotated = img.rotate(random.randint(-15, 15), expand=True, resample=Image.BICUBIC)
    out.parent.mkdir(parents=True, exist_ok=True)
    rotated.save(out, "PNG", optimize=True)
    return out
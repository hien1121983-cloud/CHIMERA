"""Telegram delivery — V4.0 Phase-1 fix.

Bổ sung:
- ``send_script_for_approval``: gửi tin nhắn duyệt kịch bản, IN ĐẬM riêng
  cinematic_video_prompt của Scene 1 để user copy đi dựng video bên ngoài.
- Inline button [✅ DUYỆT] / [♻️ LÀM LẠI]. Khi user bấm DUYỆT, hệ thống
  chuyển sang trạng thái CHỜ UPLOAD .mp4 (xử lý ở webhook.py).
"""
from __future__ import annotations
import html
import json
from pathlib import Path
from typing import List, Dict
import requests
from ..config import settings
from ..utils import get_logger

log = get_logger("telegram")

API = "https://api.telegram.org/bot{token}/{method}"


def _post(method: str, **kwargs):
    url = API.format(token=settings.bot_token, method=method)
    r = requests.post(url, timeout=120, **kwargs)
    r.raise_for_status()
    return r.json()


def send_message(text: str, reply_markup: dict | None = None) -> Dict:
    payload = {
        "chat_id": settings.chat_id,
        "text": text[:4000],
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    return _post("sendMessage", data=payload)


def send_long_message(text: str, reply_markup: dict | None = None) -> List[Dict]:
    """Chia text thành nhiều tin nhắn <= 4000 ký tự nếu cần."""
    LIMIT = 3800
    chunks = []
    while text:
        if len(text) <= LIMIT:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, LIMIT)
        if cut == -1:
            cut = LIMIT
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")

    results = []
    for i, chunk in enumerate(chunks):
        markup = reply_markup if i == len(chunks) - 1 else None
        results.append(send_message(chunk, reply_markup=markup))
    return results


def send_document(path: Path, caption: str = "") -> Dict:
    with open(path, "rb") as f:
        return _post("sendDocument",
                     data={"chat_id": settings.chat_id, "caption": caption[:1024],
                           "parse_mode": "HTML"},
                     files={"document": (path.name, f)})


def send_photo(path: Path, caption: str = "") -> Dict:
    with open(path, "rb") as f:
        return _post("sendPhoto",
                     data={"chat_id": settings.chat_id, "caption": caption[:1024]},
                     files={"photo": (path.name, f)})


def send_video(path: Path, caption: str = "") -> Dict:
    data = {"chat_id": settings.chat_id, "caption": caption[:1024],
            "parse_mode": "HTML", "supports_streaming": "true"}
    with open(path, "rb") as f:
        return _post("sendVideo", data=data, files={"video": (path.name, f)})


# ---------------- V4 PHASE-1: Script approval ----------------

def _short_dialogue(s: dict) -> str:
    d = (s.get("dialogue") or "").strip().replace("\n", " ")
    return d[:140] + ("…" if len(d) > 140 else "")


def send_script_for_approval(episode_id: str, version: int, script: dict) -> Dict:
    """Gửi kịch bản chờ duyệt. Scene 1 in đậm cinematic_video_prompt riêng."""
    scenes = script.get("scenes") or []
    title = script.get("episode_title", "")
    emotion = script.get("emotion_tag", "")
    hook = scenes[0] if scenes else {}
    hook_prompt = (hook.get("cinematic_video_prompt") or "").strip()

    parts: List[str] = []
    parts.append(f"📝 <b>Episode {html.escape(episode_id)} — v{version}</b>")
    parts.append(f"🎭 <i>{html.escape(title)}</i> · cảm xúc: <code>{html.escape(emotion)}</code>")
    parts.append("")
    parts.append("🎬 <b>SCENE 1 — THE HOOK (bạn tự dựng video)</b>")
    parts.append(f"💬 {html.escape(_short_dialogue(hook))}")
    parts.append("")
    parts.append("👉 <b>Copy prompt dưới đây sang Runway / Pika / Kling / Sora để dựng clip 9:16 ~ 6–10s:</b>")
    parts.append("")
    # IN ĐẬM toàn bộ cinematic_video_prompt để dễ copy
    parts.append(f"<b>{html.escape(hook_prompt) or '(thiếu cinematic_video_prompt — kiểm tra LLM)'}</b>")
    parts.append("")
    parts.append("───── Scene 2..N (hệ thống tự sinh ảnh) ─────")
    for s in scenes[1:]:
        idx = s.get("scene", "?")
        actor = html.escape(str(s.get("actor", "?")))
        parts.append(f"<b>{idx}.</b> [{actor}] {html.escape(_short_dialogue(s))}")

    parts.append("")
    parts.append("⬇️ Bấm <b>DUYỆT</b> rồi <b>UPLOAD file .mp4 Scene 1</b> ngay tin nhắn tiếp theo.")

    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ DUYỆT — chờ upload Scene 1",
             "callback_data": f"approve:{episode_id}:{version}"},
            {"text": "♻️ LÀM LẠI",
             "callback_data": f"reject:{episode_id}:{version}"},
        ]]
    }
    return send_long_message("\n".join(parts), reply_markup=keyboard)


# ---------------- Phase 2: deliver final videos ----------------

def _split_file(file_path: Path, chunk_mb: int) -> List[Path]:
    """Chia MP4 thành các part phát được bằng FFmpeg segment."""
    import subprocess
    size = file_path.stat().st_size
    if size <= chunk_mb * 1024 * 1024:
        return [file_path]

    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(file_path)],
        capture_output=True, text=True,
    )
    try:
        import json as _json
        duration = float(_json.loads(probe.stdout)["format"]["duration"])
    except Exception:
        duration = 120.0

    size_mb = size / (1024 * 1024)
    segment_time = max(10, int(duration * chunk_mb / size_mb))

    seg_pattern = file_path.parent / f"{file_path.stem}_part%02d.mp4"
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(file_path),
            "-c", "copy",
            "-f", "segment",
            "-segment_time", str(segment_time),
            "-segment_format", "mp4",
            "-reset_timestamps", "1",
            str(seg_pattern),
        ],
        capture_output=True, text=True,
    )
    parts = sorted(file_path.parent.glob(f"{file_path.stem}_part*.mp4"))
    if result.returncode != 0 or not parts:
        log.warning("FFmpeg segment fail — gửi file gốc nguyên: %s", result.stderr[:200])
        return [file_path]
    return parts


def deliver_videos(videos: List[Dict], episode_id: str,
                   preview_image: Path | None = None) -> None:
    if preview_image and preview_image.exists():
        try:
            send_photo(preview_image, caption=f"📸 Preview tập {episode_id}")
        except Exception as e:
            log.warning("send_photo fail: %s", e)

    for v in videos:
        cap = (f"🎬 <b>{episode_id} — v{v['version']}</b>\n"
               f"drama={v['drama_score']:.2f} | {v['title']}")
        path: Path = v["path"]
        parts = _split_file(path, settings.telegram_size_limit_mb - 1)
        if len(parts) == 1:
            try:
                send_video(parts[0], caption=cap)
            except Exception as e:
                log.warning("sendVideo fail (%s), fallback sendDocument: %s", path.name, e)
                send_document(parts[0], caption=cap)
        else:
            for idx, p in enumerate(parts, 1):
                send_document(p, caption=f"{cap} — Part {idx}/{len(parts)}")

    keyboard = {
        "inline_keyboard": [[
            {"text": f"✅ Chốt v{v['version']}",
             "callback_data": f"canon:{episode_id}:{v['version']}"}
            for v in videos
        ]]
    }
    lines = [f"🎬 <b>Episode {episode_id}</b> — chọn bản phát hành chính thức:"]
    for v in videos:
        lines.append(f"• <b>v{v['version']}</b> | drama={v['drama_score']:.2f} | {v['title']}")
    send_message("\n".join(lines), reply_markup=keyboard)


def status_message(text: str) -> None:
    try:
        send_message(f"🟢 STATUS\n{text}")
    except Exception as e:
        log.warning("status fail: %s", e)

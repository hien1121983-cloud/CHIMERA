"""Telegram delivery — V4.0.

Thêm:
  - ``send_skeleton_for_approval(episode_id, version, brief)``: gửi TÓM TẮT
    1 khung kịch bản (text-only, KHÔNG gọi LLM ở Stage A). Inline button
    [✅ DUYỆT v#] sẽ trigger Stage B qua webhook.

Giữ:
  - ``send_script_for_approval`` (legacy, dùng khi đã có script chi tiết).
  - ``deliver_videos`` — nay nhận **list[Path]** (part1/part2/full) cho mỗi
    version: tự gửi từng file kèm caption.
"""
from __future__ import annotations
import html
import json
from pathlib import Path
from typing import List, Dict, Union
import requests
import subprocess
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
    payload = {"chat_id": settings.chat_id, "text": text[:4000],
               "parse_mode": "HTML", "disable_web_page_preview": "true"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    return _post("sendMessage", data=payload)


def send_long_message(text: str, reply_markup: dict | None = None) -> List[Dict]:
    LIMIT = 3800
    chunks: List[str] = []
    while text:
        if len(text) <= LIMIT:
            chunks.append(text); break
        cut = text.rfind("\n", 0, LIMIT)
        if cut == -1: cut = LIMIT
        chunks.append(text[:cut]); text = text[cut:].lstrip("\n")
    out = []
    for i, ch in enumerate(chunks):
        m = reply_markup if i == len(chunks) - 1 else None
        out.append(send_message(ch, reply_markup=m))
    return out


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


# ---------------- V4.0: SKELETON APPROVAL ----------------

def _format_skeleton_brief(episode_id: str, version: int, brief: Dict) -> str:
    parts: List[str] = []
    parts.append(f"📋 <b>Episode {html.escape(episode_id)} — Khung v{version}</b>")
    parts.append(f"⚡ drama={brief.get('drama_score', 0):.2f}  "
                 f"· archetype: <code>{html.escape(str(brief.get('archetype', 'n/a')))}</code>")
    gl = brief.get("glitch_at")
    if gl:
        parts.append(f"🌀 Glitch tại Scene <b>{gl}</b> (sẽ split video part1/part2)")
    if brief.get("forced_injection"):
        fi = brief["forced_injection"]
        if fi.get("hidden_item"):
            parts.append(f"🔒 Hidden item ép vào: <i>{html.escape(fi['hidden_item'].get('name', ''))}</i>")
        if fi.get("destiny_dice"):
            parts.append(f"🎲 Destiny dice: <i>{html.escape(fi['destiny_dice'].get('name', ''))}</i>")
    parts.append("")
    parts.append("<b>Beat list:</b>")
    for s in brief.get("scenes", []):
        tag = " 🌀" if s.get("is_glitch") else ""
        beat = html.escape((s.get("beat") or "")[:140])
        parts.append(f"  {int(s.get('scene', 0)):>2}.{tag} {beat}")
    return "\n".join(parts)


def send_skeleton_for_approval(episode_id: str, version: int, brief: Dict) -> List[Dict]:
    """Gửi 1 khung kịch bản (TÓM TẮT, text-only) kèm 2 nút duyệt/làm lại."""
    text = _format_skeleton_brief(episode_id, version, brief)
    markup = {"inline_keyboard": [[
        {"text": f"✅ DUYỆT v{version}",
         "callback_data": f"approve_skel:{episode_id}:{version}"},
        {"text": "♻️ Làm lại tất cả",
         "callback_data": f"regen_all:{episode_id}"},
    ]]}
    return send_long_message(text, reply_markup=markup)


# ---------------- Legacy: SCRIPT APPROVAL ----------------

def _short_dialogue(s: dict) -> str:
    d = (s.get("dialogue") or "").strip().replace("\n", " ")
    return d[:140] + ("…" if len(d) > 140 else "")


def send_script_for_approval(episode_id: str, version: int, script: dict) -> List[Dict]:
    scenes = script.get("scenes") or []
    title = script.get("episode_title", "")
    emotion = script.get("emotion_tag", "")
    hook = scenes[0] if scenes else {}
    hook_prompt = (hook.get("cinematic_video_prompt") or "").strip()

    parts: List[str] = []
    parts.append(f"📝 <b>Episode {html.escape(episode_id)} — Script v{version}</b>")
    parts.append(f"🎭 <i>{html.escape(title)}</i> · cảm xúc: <code>{html.escape(emotion)}</code>")
    parts.append("")
    if hook_prompt:
        parts.append("🎬 <b>CINEMATIC VIDEO PROMPT (Scene 1 — copy đi dựng video):</b>")
        parts.append(f"<b>{html.escape(hook_prompt)}</b>")
        parts.append("")
    parts.append("<b>Scene list:</b>")
    for s in scenes:
        role = s.get("speaker_role", "?")
        parts.append(f"  {int(s.get('scene', 0)):>2}. [{role}] {_short_dialogue(s)}")
    markup = {"inline_keyboard": [[
        {"text": f"✅ DUYỆT v{version}",
         "callback_data": f"approve_script:{episode_id}:{version}"},
    ]]}
    return send_long_message("\n".join(parts), reply_markup=markup)


# ---------------- DELIVER VIDEOS ----------------

def _split_file(file_path: Path, chunk_mb: int) -> List[Path]:
    size = file_path.stat().st_size
    if size <= chunk_mb * 1024 * 1024:
        return [file_path]
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)],
            capture_output=True, text=True, check=True,
        )
        duration = float(probe.stdout.strip() or 0)
    except Exception:
        return [file_path]
    size_mb = size / (1024 * 1024)
    if duration <= 0 or size_mb <= 0: return [file_path]
    segment_time = max(10, int(duration * chunk_mb / size_mb))
    seg_pattern = file_path.parent / f"{file_path.stem}_part%02d.mp4"
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", str(file_path), "-c", "copy", "-f", "segment",
         "-segment_time", str(segment_time), "-segment_format", "mp4",
         "-reset_timestamps", "1", str(seg_pattern)],
        capture_output=True, text=True,
    )
    parts = sorted(file_path.parent.glob(f"{file_path.stem}_part*.mp4"))
    if r.returncode != 0 or not parts:
        return [file_path]
    return parts


def deliver_videos(videos: List[Dict], episode_id: str,
                   preview_image: Path | None = None) -> None:
    """``videos[i]['path']`` có thể là 1 ``Path`` hoặc ``list[Path]`` (split)."""
    if preview_image and Path(preview_image).exists():
        try: send_photo(preview_image, caption=f"📸 Preview tập {episode_id}")
        except Exception as e: log.warning("send_photo fail: %s", e)

    for v in videos:
        paths_raw: Union[Path, List[Path]] = v["path"]
        paths: List[Path] = list(paths_raw) if isinstance(paths_raw, (list, tuple)) else [paths_raw]
        for k, p in enumerate(paths, 1):
            label = ""
            if len(paths) > 1:
                if p.name.endswith("part1.mp4"): label = " · PART 1/2"
                elif p.name.endswith("part2.mp4"): label = " · PART 2/2"
                else: label = f" · clip {k}/{len(paths)}"
            cap = (f"🎬 <b>{episode_id} — v{v['version']}</b>{label}\n"
                   f"drama={v.get('drama_score', 0):.2f} | {v.get('title', '')}\n"
                   f"<i>(Showrunner tự ghép với Scene 1 + glitch transition)</i>")
            for piece in _split_file(p, settings.telegram_size_limit_mb - 1):
                try:
                    send_video(piece, caption=cap)
                except Exception as e:
                    log.warning("sendVideo fail (%s), fallback sendDocument: %s", piece.name, e)
                    send_document(piece, caption=cap)


def status_message(text: str) -> None:
    try: send_message(f"🟢 STATUS\n{text}")
    except Exception as e: log.warning("status fail: %s", e)

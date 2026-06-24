"""Timeline Mapper — đo độ dài MP3, sinh SRT + timeline.json, ghép BGM, chèn ads.

- SRT format HH:MM:SS,mmm
- Silence padding 0.3s giữa scene
- BGM giảm xuống 20-30% rồi ghép overlay
- Chèn ads ngẫu nhiên (1 slide), bỏ qua scene có no_ad=true
"""
from __future__ import annotations
import json
import random
from pathlib import Path
from typing import List, Dict, Optional
from ..config import settings
from ..utils import get_logger

log = get_logger("timeline")

_TRANSITIONS_DIR = Path(__file__).resolve().parents[2] / "data" / "transitions"


def select_transition(scene_from: dict, scene_to: dict,
                      is_glitch: bool = False) -> Optional[str]:
    """Chọn clip transition phù hợp. Trả về path tuyệt đối hoặc None."""
    if not settings.enable_transitions:
        return None
    candidates = []
    if is_glitch and int(scene_from.get("scene", 0)) == 7:
        candidates.append(_TRANSITIONS_DIR / "transition_glitch.mp4")
    if (scene_to.get("sfx_tag") in {"twist", "dramatic", "betrayal", "revenge"}):
        candidates.append(_TRANSITIONS_DIR / "transition_dramatic.mp4")
    candidates.append(_TRANSITIONS_DIR / "transition_standard.mp4")
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def _fmt_srt(t: float) -> str:
    h = int(t // 3600); m = int((t % 3600) // 60); s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _duration_sec(path: Path) -> float:
    try:
        from mutagen.mp3 import MP3
        return MP3(str(path)).info.length
    except Exception:
        return 2.0


def build_timeline(
    script: dict,
    media: Dict[str, List[Path]],
    out_dir: Path,
    bgm_path: str | None,
    ads_dir: Path = Path("ads"),
) -> Dict:
    voices = media["voices"]
    images = media["images"]
    scenes = script["scenes"]
    pad = settings.silence_padding_sec

    cursor = 0.0
    srt_lines = []
    timeline: List[Dict] = []
    for idx, scene in enumerate(scenes):
        dur = _duration_sec(voices[idx]) if (voices[idx] is not None and voices[idx].exists()) else 2.0
        start = cursor
        end = start + dur
        srt_lines.append(f"{idx+1}")
        srt_lines.append(f"{_fmt_srt(start)} --> {_fmt_srt(end)}")
        srt_lines.append(scene.get("dialogue", ""))
        srt_lines.append("")
        prev = scenes[idx - 1] if idx > 0 else {}
        trans = select_transition(prev, scene) if idx > 0 else None
        timeline.append({
            "scene": idx + 1,
            "start": round(start, 3),
            "end": round(end, 3),
            "image": str(images[idx].name) if (images[idx] is not None and images[idx].exists()) else None,
            "voice": str(voices[idx].name) if (voices[idx] is not None and voices[idx].exists()) else None,
            "no_ad": bool(scene.get("no_ad", False)),
            "sfx_tag": scene.get("sfx_tag", ""),
            "comic_text": scene.get("comic_text", ""),
            "video_brief": scene.get("video_brief", ""),
            "transition_in": trans,
            "is_hook_video": bool(scene.get("video_brief")) and (idx == 0),
        })
        cursor = end + pad

    # Write SRT + JSON
    (out_dir / "timeline.srt").write_text("\n".join(srt_lines), encoding="utf-8")
    (out_dir / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
    # Mapping {scene_01: duration_sec, ...} cho FFmpeg builder
    durations = {f"scene_{t['scene']:02d}": round(t["end"] - t["start"], 3) for t in timeline}
    (out_dir / "timeline_durations.json").write_text(
        json.dumps(durations, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Ads insertion (chọn 1 ad chèn vào slot có thể) — chỉ thông tin metadata,
    # việc render video sẽ do client-side (CapCut/FFmpeg) đảm nhận.
    ad_slot = None
    if ads_dir.exists():
        ads = list(ads_dir.glob("*.jpg")) + list(ads_dir.glob("*.png"))
        candidates = [t for t in timeline if not t["no_ad"] and 0 < t["scene"] < len(timeline)]
        if ads and candidates:
            slot = random.choice(candidates)
            ad_file = random.choice(ads)
            ad_slot = {"after_scene": slot["scene"], "ad_file": ad_file.name, "duration_sec": 3.0}

    # Mix BGM nếu có (export bgm.mp3 đã ducked, tổng độ dài = cursor)
    if bgm_path and Path(bgm_path).exists():
        try:
            from pydub import AudioSegment
            bgm = AudioSegment.from_file(bgm_path)
            total_ms = int(cursor * 1000) + 1000
            # loop hoặc cắt cho đủ
            while len(bgm) < total_ms:
                bgm = bgm + bgm
            bgm = bgm[:total_ms]
            # Giảm volume: dùng apply_gain (API chính thức), KHÔNG dùng `bgm + float`
            # vì một số pydub version coi `+ float` là nối segment.
            ratio = settings.bgm_volume_ratio
            import math
            if ratio and ratio > 0:
                bgm = bgm.apply_gain(20 * math.log10(ratio))
            bgm.export(out_dir / "bgm.mp3", format="mp3", bitrate="96k")
        except Exception as e:
            log.warning("BGM mix fail: %s", e)
            try:
                # fallback: copy file gốc
                from shutil import copyfile
                copyfile(bgm_path, out_dir / "bgm.mp3")
            except Exception:
                pass

    summary = {
        "total_duration_sec": round(cursor, 2),
        "scenes_count": len(scenes),
        "ad_slot": ad_slot,
    }
    if ad_slot:
        (out_dir / "ad_slot.json").write_text(json.dumps(ad_slot, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
    return summary

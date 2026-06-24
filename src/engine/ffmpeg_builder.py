"""FFmpeg Builder — ghép Scene 1 video (do user upload) + ảnh tĩnh Scene 2..N
+ voice + BGM + hardsub SRT, có CHRONO-GLITCH TRANSITION TĨNH.

V4.0 PHASE-1 FIX
================
1. Scene 1 LÀ MỘT VIDEO CLIP (``scene_01.mp4``) do người dùng tự sinh bên ngoài.
   FFmpeg sẽ concat clip này ở đầu chuỗi.
2. Glitch transition là FILE TĨNH có sẵn trong ``assets/glitch_transition.mp4``.
   Nếu scene K trong kịch bản có ``is_glitch=true``, FFmpeg sẽ chèn cứng file
   này NGAY SAU scene K (ví dụ Scene 8 trong tập 15 phân cảnh).
   -> KHÔNG gọi API, KHÔNG sinh prompt.

Cách triển khai: dùng filter ``concat`` (chứ không phải demuxer ``-f concat``)
để chuẩn hoá mọi nguồn (image-loop / video) về cùng resolution & SAR trước khi nối.
"""
from __future__ import annotations
import json
import subprocess
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from ..config import settings
from ..utils import get_logger

log = get_logger("ffmpeg")

# File transition tĩnh, nằm cố định trong source
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
GLITCH_TRANSITION_PATH = _PROJECT_ROOT / "assets" / "glitch_transition.mp4"


def _escape_subtitle_path(p: Path) -> str:
    return str(p.resolve()).replace("\\", "/").replace(":", "\\:")


def _scene_inputs(out_dir: Path,
                  timing: Dict[str, float],
                  scenes_meta: List[dict]) -> List[Tuple[str, Path, float, bool]]:
    """Tạo danh sách (scene_id, path, duration, is_video).

    - Scene 1: ``scene_01.mp4`` từ ``out_dir`` (user upload). Bắt buộc tồn tại.
    - Scene k>=2: ``images/scene_kk.jpg``.
    - Sau bất kỳ scene nào có ``is_glitch=true`` -> chèn 1 input bonus là
      ``assets/glitch_transition.mp4`` (đánh dấu scene_id = ``glitch_after_KK``).
    """
    inputs: List[Tuple[str, Path, float, bool]] = []
    images_dir = out_dir / "images"
    scene1_video = out_dir / "scene_01.mp4"

    for idx, sid in enumerate(timing.keys()):
        dur = float(timing[sid])
        if idx == 0:
            if not scene1_video.exists():
                log.error("KHÔNG TÌM THẤY %s — user chưa upload video Scene 1.",
                          scene1_video)
                raise FileNotFoundError(str(scene1_video))
            inputs.append((sid, scene1_video, dur, True))
        else:
            img = images_dir / f"{sid}.jpg"
            if not img.exists():
                log.warning("Thiếu ảnh %s — bỏ qua scene.", img.name)
                continue
            inputs.append((sid, img, dur, False))

        # Glitch transition tĩnh sau scene này nếu đánh dấu
        meta = scenes_meta[idx] if idx < len(scenes_meta) else {}
        if meta.get("is_glitch"):
            if GLITCH_TRANSITION_PATH.exists():
                inputs.append((f"glitch_after_{sid}",
                               GLITCH_TRANSITION_PATH, 0.0, True))
                log.info("Chèn CHRONO-GLITCH tĩnh sau %s.", sid)
            else:
                log.warning("is_glitch=true nhưng thiếu %s — bỏ qua.",
                            GLITCH_TRANSITION_PATH)

    return inputs


def build_video(out_dir: Path,
                bgm_path: Optional[Path] = None,
                scenes_meta: Optional[List[dict]] = None) -> Optional[Path]:
    """Ghép final video. ``scenes_meta`` = ``script["scenes"]`` để đọc is_glitch."""
    out_dir = Path(out_dir)
    video_path = out_dir / "final_video.mp4"
    voices_dir = out_dir / "voices"
    srt_path = out_dir / "timeline.srt"
    timing_json = out_dir / "timeline_durations.json"
    scenes_meta = scenes_meta or []

    if not timing_json.exists():
        log.warning("Thiếu timeline_durations.json — bỏ qua build_video.")
        return None

    try:
        timing: Dict[str, float] = json.loads(timing_json.read_text(encoding="utf-8"))
        if not timing:
            log.warning("timing rỗng.")
            return None

        scene_inputs = _scene_inputs(out_dir, timing, scenes_meta)
        if not scene_inputs:
            log.error("Không có input video/image hợp lệ.")
            return None

        # ---- Concat voice (Scene 1..N) ----
        voice_list = out_dir / "_voice_list.txt"
        with voice_list.open("w", encoding="utf-8") as f:
            for sid in timing.keys():
                v = voices_dir / f"{sid}.mp3"
                if v.exists():
                    f.write(f"file '{v.resolve()}'\n")
        voices_concat = out_dir / "_voices_concat.mp3"
        r = subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", str(voice_list), "-c", "copy", str(voices_concat)],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                 "-i", str(voice_list), "-c:a", "libmp3lame", "-b:a", "128k",
                 str(voices_concat)],
                check=True, capture_output=True,
            )

        # ---- Build ffmpeg command với filter_complex concat ----
        W, H = settings.video_width, settings.video_height
        cmd: List[str] = ["ffmpeg", "-y"]
        filter_parts: List[str] = []
        concat_inputs: List[str] = []

        for i, (sid, path, dur, is_video) in enumerate(scene_inputs):
            if is_video:
                # BP-2: glitch transition là file tĩnh, suppress audio track để
                # tránh xung đột với voices_concat khi map [n:a].
                if sid.startswith("glitch_after_"):
                    cmd += ["-an", "-i", str(path)]
                else:
                    cmd += ["-i", str(path)]
                # Chuẩn hoá: scale + pad + setsar
                filter_parts.append(
                    f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
                    f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[v{i}]"
                )
            else:
                # ảnh tĩnh -> loop trong `dur` giây
                cmd += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(path)]
                filter_parts.append(
                    f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
                    f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[v{i}]"
                )
            concat_inputs.append(f"[v{i}]")

        # Concat tất cả nhánh video
        n = len(scene_inputs)
        filter_parts.append(
            "".join(concat_inputs) + f"concat=n={n}:v=1:a=0[vcat]"
        )

        # Subtitle hardsub (nếu có)
        last_vlabel = "vcat"
        if srt_path.exists():
            sub_path = _escape_subtitle_path(srt_path)
            filter_parts.append(f"[vcat]subtitles='{sub_path}'[vout]")
            last_vlabel = "vout"

        # Audio: voice concat + (optional) BGM duck
        cmd += ["-i", str(voices_concat)]   # index = n
        voice_idx = n
        has_bgm = bool(bgm_path and Path(bgm_path).exists())
        if has_bgm:
            cmd += ["-i", str(bgm_path)]    # index = n+1
            filter_parts.append(
                f"[{voice_idx+1}:a]volume={settings.bgm_volume_ratio}[bgm_d]"
            )
            filter_parts.append(
                f"[{voice_idx}:a][bgm_d]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )
        else:
            filter_parts.append(f"[{voice_idx}:a]anull[aout]")

        filter_complex = "; ".join(filter_parts)
        cmd += [
            "-filter_complex", filter_complex,
            "-map", f"[{last_vlabel}]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", settings.video_preset,
            "-crf", str(settings.video_crf),
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p", "-shortest",
            str(video_path),
        ]

        log.info("FFmpeg: %d inputs (bgm=%s, glitch=%s)", n, has_bgm,
                 any(sid.startswith("glitch_after_") for sid, *_ in scene_inputs))
        result = subprocess.run(
            cmd, cwd=str(out_dir), capture_output=True, text=True,
            timeout=settings.ffmpeg_timeout_sec,
        )
        if result.returncode == 0 and video_path.exists():
            log.info("MP4 ra lò: %s (%.1f MB)", video_path.name,
                     video_path.stat().st_size / 1_048_576)
            for p in [voice_list, voices_concat]:
                try: p.unlink()
                except Exception: pass
            return video_path

        (out_dir / "ffmpeg_error.log").write_text(result.stderr or "", encoding="utf-8")
        log.error("FFmpeg fail (exit=%s), xem ffmpeg_error.log", result.returncode)
        return None

    except FileNotFoundError as e:
        log.error("Thiếu file: %s", e)
        return None
    except subprocess.TimeoutExpired:
        log.error("FFmpeg timeout %ds", settings.ffmpeg_timeout_sec)
        return None
    except Exception as e:
        log.error("build_video lỗi: %s", e)
        return None

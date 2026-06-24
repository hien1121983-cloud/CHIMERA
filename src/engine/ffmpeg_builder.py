"""FFmpeg Builder — V4.0 SPLIT RENDERING.

LUẬT MỚI:
  - KHÔNG ghép Scene 1 (video do Showrunner tự dựng — sẽ ghép bên ngoài).
  - KHÔNG chèn file glitch transition — Showrunner sẽ tự chèn.
  - Hệ thống chỉ render KHỐI scene 2..15:

    * Tập bình thường  : 1 khối duy nhất ``system_video_full.mp4``
      (concat scene 2 -> 15).
    * Tập có Glitch    : nếu scene K (2 ≤ K ≤ 15) có ``is_glitch=true``,
      cắt thành 2 file:
        - ``system_video_part1.mp4`` : scene 2 -> scene (K-1).
        - ``system_video_part2.mp4`` : scene K -> scene 15.

  Trả về **list[Path]** các MP4 đã render (1 hoặc 2 phần).
"""
from __future__ import annotations
import json
import subprocess
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from ..config import settings
from ..utils import get_logger

log = get_logger("ffmpeg")


def _escape_subtitle_path(p: Path) -> str:
    return str(p.resolve()).replace("\\", "/").replace(":", "\\:")


def _glitch_index_1based(scenes_meta: List[dict]) -> Optional[int]:
    """Trả về chỉ số 1-based của scene đầu tiên có is_glitch=true, hoặc None."""
    for s in scenes_meta or []:
        if s.get("is_glitch"):
            try:
                idx = int(s.get("scene"))
                if 2 <= idx <= len(scenes_meta):
                    return idx
            except Exception:
                continue
    return None


def _render_segment(out_dir: Path,
                    scene_indices: List[int],            # 1-based, đã loại scene 1
                    timing: Dict[str, float],
                    bgm_path: Optional[Path],
                    out_name: str,
                    srt_path: Optional[Path]) -> Optional[Path]:
    if not scene_indices:
        log.warning("[%s] không có scene nào để render.", out_name)
        return None

    out_path  = out_dir / out_name
    img_dir   = out_dir / "images"
    voice_dir = out_dir / "voices"

    # ---- Concat voice cho đoạn này ----
    seg_voice_list = out_dir / f"_voice_list_{out_path.stem}.txt"
    have_voice = False
    with seg_voice_list.open("w", encoding="utf-8") as f:
        for idx in scene_indices:
            sid = f"scene_{idx:02d}"
            v = voice_dir / f"{sid}.mp3"
            if v.exists():
                f.write(f"file '{v.resolve()}'\n"); have_voice = True

    voices_concat = out_dir / f"_voices_concat_{out_path.stem}.mp3"
    if have_voice:
        r = subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", str(seg_voice_list), "-c", "copy", str(voices_concat)],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                 "-i", str(seg_voice_list), "-c:a", "libmp3lame", "-b:a", "128k",
                 str(voices_concat)],
                check=True, capture_output=True,
            )

    W, H = settings.video_width, settings.video_height
    cmd: List[str] = ["ffmpeg", "-y"]
    filter_parts: List[str] = []
    concat_inputs: List[str] = []
    valid_count = 0

    for i, scene_idx in enumerate(scene_indices):
        sid = f"scene_{scene_idx:02d}"
        path = img_dir / f"{sid}.jpg"
        dur = float(timing.get(sid) or 3.0)
        if not path.exists():
            log.warning("[%s] thiếu %s — bỏ scene.", out_name, path.name); continue
        cmd += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(path)]
        filter_parts.append(
            f"[{valid_count}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[v{valid_count}]"
        )
        concat_inputs.append(f"[v{valid_count}]")
        valid_count += 1

    if valid_count == 0:
        log.error("[%s] không có input ảnh hợp lệ.", out_name); return None

    filter_parts.append("".join(concat_inputs) + f"concat=n={valid_count}:v=1:a=0[vcat]")

    last_vlabel = "vcat"
    if srt_path and srt_path.exists():
        filter_parts.append(f"[vcat]subtitles='{_escape_subtitle_path(srt_path)}'[vout]")
        last_vlabel = "vout"

    # Audio
    if have_voice:
        cmd += ["-i", str(voices_concat)]
        voice_idx = valid_count
        if bgm_path and Path(bgm_path).exists():
            cmd += ["-i", str(bgm_path)]
            filter_parts.append(
                f"[{voice_idx+1}:a]volume={settings.bgm_volume_ratio}[bgm_d]")
            filter_parts.append(
                f"[{voice_idx}:a][bgm_d]amix=inputs=2:duration=first:dropout_transition=2[aout]")
        else:
            filter_parts.append(f"[{voice_idx}:a]anull[aout]")
        audio_map = ["-map", "[aout]"]
    else:
        audio_map = ["-an"]

    cmd += [
        "-filter_complex", "; ".join(filter_parts),
        "-map", f"[{last_vlabel}]", *audio_map,
        "-c:v", "libx264", "-preset", settings.video_preset,
        "-crf", str(settings.video_crf),
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p", "-shortest",
        str(out_path),
    ]

    log.info("[%s] FFmpeg: %d ảnh, voice=%s, bgm=%s",
             out_name, valid_count, have_voice, bool(bgm_path))
    result = subprocess.run(cmd, cwd=str(out_dir), capture_output=True, text=True,
                            timeout=settings.ffmpeg_timeout_sec)
    # dọn temp
    for p in [seg_voice_list, voices_concat]:
        try: p.unlink()
        except Exception: pass

    if result.returncode == 0 and out_path.exists():
        log.info("[%s] OK (%.1f MB).", out_name, out_path.stat().st_size / 1_048_576)
        return out_path

    err_log = out_dir / f"ffmpeg_error_{out_path.stem}.log"
    err_log.write_text(result.stderr or "", encoding="utf-8")
    log.error("[%s] FFmpeg fail (exit=%s) — xem %s", out_name, result.returncode, err_log.name)
    return None
def render_final_episodes(all_scenes, has_glitch=False, glitch_scene_num=8):
    """
    Bảo toàn cấu trúc UI 14 phân cảnh (từ Scene 2 đến 15).
    all_scenes: Danh sách 15 object scene.
    """
    # 1. Bỏ qua Scene 1 (The Hook), chỉ render từ Scene 2 (index 1) trở đi
    render_scenes = all_scenes[1:] 
    
    if not has_glitch:
        print("🎬 Kết xuất: system_video_full.mp4 (Scene 2 -> 15)")
        build_video(render_scenes, "system_video_full.mp4")
    else:
        # Toán học chia mảng: Vị trí cắt = Scene Number - 2 (Vì render_scenes bắt đầu từ Scene 2 [index 0])
        split_idx = glitch_scene_num - 2 
        
        part_1 = render_scenes[:split_idx]  # Từ Scene 2 đến trước Glitch
        part_2 = render_scenes[split_idx:]  # Từ Glitch đến Scene 15
        
        print("✂️ Tách Video phần 1 (Trước Glitch)")
        build_video(part_1, "system_video_part1.mp4")
        
        print("✂️ Tách Video phần 2 (Sau Glitch)")
        build_video(part_2, "system_video_part2.mp4")

def build_video(scenes_list, output_filename):
    # Lệnh ghép FFmpeg của bạn (concat ảnh và âm thanh đã xử lý)
    pass
  

def build_video(out_dir: Path,
                bgm_path: Optional[Path] = None,
                scenes_meta: Optional[List[dict]] = None) -> Optional[List[Path]]:
    """Render khối scene 2..N. Trả về list các MP4 đã sinh ra
    (1 file ``system_video_full.mp4`` hoặc 2 file ``system_video_part1/2.mp4``).
    """
    out_dir = Path(out_dir)
    timing_json = out_dir / "timeline_durations.json"
    srt_path = out_dir / "timeline.srt"
    scenes_meta = scenes_meta or []

    if not timing_json.exists():
        log.warning("Thiếu timeline_durations.json — bỏ qua build_video.")
        return None
    try:
        timing: Dict[str, float] = json.loads(timing_json.read_text(encoding="utf-8"))
    except Exception as e:
        log.error("Đọc timing fail: %s", e); return None
    if not timing:
        log.warning("timing rỗng."); return None

    total = len(scenes_meta) or len([k for k in timing if k.startswith("scene_")])
    all_idx = list(range(2, total + 1))   # bỏ scene 1
    if not all_idx:
        log.error("Không có scene 2..N nào."); return None

    glitch = _glitch_index_1based(scenes_meta)
    outputs: List[Path] = []

    if glitch is None or glitch <= 2 or glitch > total:
        log.info("Render 1 khối liền mạch scene 2..%d.", total)
        out = _render_segment(out_dir, all_idx, timing, bgm_path,
                              "system_video_full.mp4", srt_path)
        if out: outputs.append(out)
    else:
        log.info("Glitch tại scene %d -> tách 2 phần (2..%d) + (%d..%d).",
                 glitch, glitch - 1, glitch, total)
        part1_idx = [i for i in all_idx if i < glitch]
        part2_idx = [i for i in all_idx if i >= glitch]
        out1 = _render_segment(out_dir, part1_idx, timing, bgm_path,
                               "system_video_part1.mp4", srt_path)
        out2 = _render_segment(out_dir, part2_idx, timing, bgm_path,
                               "system_video_part2.mp4", srt_path)
        if out1: outputs.append(out1)
        if out2: outputs.append(out2)

    return outputs or None

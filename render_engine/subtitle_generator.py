"""Sinh file .srt tu audio timing (Va M-04: enumerate)."""
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SubtitleGenerator:
    @staticmethod
    def generate(scene_timings, dialogues, temp_dir: str) -> str:
        """Sinh .srt tu danh sach timing.

        Va M-04: Dung enumerate thay list.index() de tranh sai khi co dialogue trung.
        """
        Path(f"{temp_dir}/subtitles").mkdir(parents=True, exist_ok=True)
        srt_path = f"{temp_dir}/subtitles/episode.srt"

        cursor_ms = 0
        subtitle_index = 1
        lines = []
        for i, timing in enumerate(scene_timings):
            duration = timing.get("duration_ms", 1500)
            start = cursor_ms
            end = cursor_ms + duration
            text = ""
            if i < len(dialogues):
                text = dialogues[i].get("line", "")
            lines.append(str(subtitle_index))
            lines.append(
                f"{SubtitleGenerator._ms_to_srt_time(start)} --> "
                f"{SubtitleGenerator._ms_to_srt_time(end)}"
            )
            lines.append(text)
            lines.append("")
            cursor_ms = end
            subtitle_index += 1

        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.info(f"[Subtitle] {srt_path}: {subtitle_index - 1} subtitles")
        return srt_path

    @staticmethod
    def _ms_to_srt_time(ms: int) -> str:
        hours = ms // 3600000
        ms %= 3600000
        minutes = ms // 60000
        ms %= 60000
        seconds = ms // 1000
        millis = ms % 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"

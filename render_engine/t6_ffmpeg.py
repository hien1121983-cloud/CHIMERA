"""Tram T6: Lo co khi FFmpeg - render video tu anh + audio + bgm + sub."""
import logging
import subprocess
from pathlib import Path

from core.helpers import _select_bgm
from render_engine.ffmpeg_builder import FFmpegCommandBuilder
from render_engine.subtitle_generator import SubtitleGenerator
from render_engine.part_splitter import PartSplitter

logger = logging.getLogger(__name__)


class T6FFmpeg:
    def __init__(self, execution_json: dict, temp_dir: str):
        self.execution_json = execution_json
        self.temp_dir = temp_dir
        self.episode_number = execution_json["meta"]["episode_number"]
        Path(f"{temp_dir}/video_parts").mkdir(parents=True, exist_ok=True)

    def render(self, merged_audio: str, log: dict) -> list:
        """Render hoan chinh -> tra ve danh sach video parts (<=50MB)."""
        # 1. Render draft video (anh + audio)
        draft_video = self._render_draft(merged_audio)

        # 2. Sinh subtitle
        dialogues = []
        for scene in self.execution_json.get("scenes", []):
            dialogues.extend(scene.get("dialogues", []))
        srt_path = SubtitleGenerator.generate(
            log.get("scene_timings", []), dialogues, self.temp_dir
        )

        # 3. Them BGM + subtitle
        bgm_mood = self.execution_json.get("scenes", [{}])[0].get("bgm_mood", "default")
        final_video = self._add_bgm_and_subtitles(
            draft_video, srt_path, bgm_mood
        )

        # 4. Cat part neu > 50MB
        return PartSplitter.split(final_video, self.temp_dir, self.episode_number)

    def _render_draft(self, merged_audio: str) -> str:
        draft_path = f"{self.temp_dir}/video_parts/draft.mp4"
        builder = (
            FFmpegCommandBuilder()
            .add_concat_demuxer(f"{self.temp_dir}/images_list.txt")
            .add_input(merged_audio)
            .add_cpu_protection()
            .add_output(draft_path)
        )
        self._run(builder.build())
        return draft_path

    def _add_bgm_and_subtitles(
        self, draft_video: str, srt_path: str, bgm_mood: str
    ) -> str:
        final_path = f"{self.temp_dir}/episode_{self.episode_number}_final.mp4"
        bgm_path = _select_bgm(bgm_mood)
        builder = FFmpegCommandBuilder()
        builder.add_input(draft_video)
        builder.add_bgm(bgm_path)
        builder.args.extend(["-map", "0:v", "-map", "[aout]"])
        builder.add_subtitles(srt_path)
        builder.add_cpu_protection()
        builder.add_output(final_path)
        self._run(builder.build())
        return final_path

    def _run(self, cmd: list, timeout: int = 1800):
        logger.info(f"[T6] FFmpeg: {' '.join(cmd[:6])}...")
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            logger.error(f"[T6] FFmpeg loi: {result.stderr[:500]}")
            raise RuntimeError("[T6] FFmpeg render fail")

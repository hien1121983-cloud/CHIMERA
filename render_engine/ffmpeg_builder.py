"""Builder pattern cho FFmpeg args (Va: -threads/-crf/-preset tu settings)."""
import logging

from config.settings import settings

logger = logging.getLogger(__name__)


class FFmpegCommandBuilder:
    def __init__(self):
        self.args = ["ffmpeg", "-y"]

    def add_input(self, path: str, extra=None):
        if extra:
            self.args.extend(extra)
        self.args.extend(["-i", path])
        return self

    def add_concat_demuxer(self, list_path: str):
        self.args.extend(["-f", "concat", "-safe", "0", "-i", list_path])
        return self

    def add_bgm(self, bgm_path: str, bgm_volume: float = 0.25):
        self.args.extend(["-i", bgm_path])
        self.args.extend([
            "-filter_complex",
            f"[1:a]volume={bgm_volume}[bgm];[0:a][bgm]amix=inputs=2:duration=first[aout]",
        ])
        return self

    def add_subtitles(self, srt_path: str):
        self.args.extend(["-vf", f"subtitles={srt_path}"])
        return self

    def add_cpu_protection(self):
        """BAT BUOC: -threads -crf -preset tu settings."""
        self.args.extend([
            "-threads", str(settings.FFMPEG_THREADS),
            "-crf", str(settings.FFMPEG_CRF),
            "-preset", settings.FFMPEG_PRESET,
        ])
        return self

    def add_output(self, output_path: str, video_codec: str = "libx264"):
        self.args.extend([
            "-c:v", video_codec,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            output_path,
        ])
        return self

    def build(self):
        return list(self.args)

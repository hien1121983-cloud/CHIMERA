"""Cat Part 1/2 neu video > 50MB (ffprobe + -ss + -t)."""
import os
import logging
import subprocess

logger = logging.getLogger(__name__)

MAX_SIZE_BYTES = 50 * 1024 * 1024  # 50MB


class PartSplitter:
    @staticmethod
    def needs_split(video_path: str) -> bool:
        """Kiem tra file co > 50MB khong."""
        return os.path.getsize(video_path) > MAX_SIZE_BYTES

    @staticmethod
    def get_duration_seconds(video_path: str) -> float:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", video_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        try:
            return float(result.stdout.strip())
        except ValueError:
            return 0.0

    @staticmethod
    def split(video_path: str, temp_dir: str, episode_number: int) -> list:
        """Cat video thanh nhieu part <= 50MB."""
        if not PartSplitter.needs_split(video_path):
            return [video_path]

        total_size = os.path.getsize(video_path)
        duration = PartSplitter.get_duration_seconds(video_path)
        num_parts = (total_size // MAX_SIZE_BYTES) + 1
        part_duration = duration / num_parts

        parts = []
        for i in range(int(num_parts)):
            start = i * part_duration
            part_path = f"{temp_dir}/episode_{episode_number}_part{i + 1}.mp4"
            cmd = [
                "ffmpeg", "-y", "-ss", str(start), "-t", str(part_duration),
                "-i", video_path,
                "-c:v", "libx264", "-c:a", "aac",
                "-b:a", "128k", "-movflags", "+faststart",
                part_path,
            ]
            logger.info(f"[PartSplitter] Rendering part {i + 1}/{int(num_parts)}...")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"[PartSplitter] Loi part {i + 1}: {result.stderr[:300]}")
                raise RuntimeError("[PartSplitter] FFmpeg split fail")
            parts.append(part_path)
        return parts

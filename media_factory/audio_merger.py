"""Ghep audio rieng le thanh merged_audio.mp3 (FFmpeg concat)."""
import glob
import logging
import subprocess

logger = logging.getLogger(__name__)


class AudioMerger:
    @staticmethod
    def merge(temp_dir: str) -> str:
        """Ghep tat ca file audio trong temp_dir/audio thanh 1 file.

        Dung FFmpeg filter_complex concat (an toan cho audio).
        """
        audio_dir = f"{temp_dir}/audio"
        audio_files = sorted(glob.glob(f"{audio_dir}/*.mp3"))
        if not audio_files:
            raise RuntimeError(f"[AudioMerger] Khong tim thay file audio trong {audio_dir}")

        output_path = f"{temp_dir}/merged_audio.mp3"
        list_path = f"{temp_dir}/audio_concat_list.txt"
        with open(list_path, "w", encoding="utf-8") as f:
            for af in audio_files:
                f.write(f"file '{af}'\n")

        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_path, "-c", "copy", output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # Fallback: re-encode
            cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", list_path, "-c:a", "libmp3lame", output_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"[AudioMerger] FFmpeg loi: {result.stderr[:500]}")

        logger.info(f"[AudioMerger] Ghep {len(audio_files)} files -> {output_path}")
        return output_path

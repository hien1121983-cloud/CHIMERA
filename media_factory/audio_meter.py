"""Do mili-giay audio chinh xac bang pydub."""
import logging

logger = logging.getLogger(__name__)


class AudioMeter:
    @staticmethod
    def get_duration_ms(audio_path: str) -> int:
        """Tra ve thoi luong audio (ms) chinh xac."""
        from pydub import AudioSegment

        audio = AudioSegment.from_file(audio_path)
        return len(audio)

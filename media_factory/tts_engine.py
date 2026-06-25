"""ElevenLabs + Edge-TTS wrapper voi fallback."""
import asyncio
import logging

from core.credential_manager import ELEVENLABS_POOL

logger = logging.getLogger(__name__)


class TTSEngine:
    async def synthesize(self, text: str, voice_id: str, output_path: str) -> bool:
        """Tao audio tu text. Uu tien ElevenLabs, fallback Edge-TTS."""
        success = await self._try_elevenlabs(text, voice_id, output_path)
        if success:
            return True

        logger.warning(f"[TTS] ElevenLabs fail cho '{text[:30]}...', fallback Edge-TTS")
        return await self._try_edge_tts(text, output_path)

    async def _try_elevenlabs(self, text: str, voice_id: str, output_path: str) -> bool:
        key = ELEVENLABS_POOL.get_next()
        if not key:
            return False
        try:
            from elevenlabs.client import ElevenLabs

            client = ElevenLabs(api_key=key)
            audio = client.generate(text=text, voice=voice_id)
            with open(output_path, "wb") as f:
                for chunk in audio:
                    f.write(chunk)
            return True
        except Exception as e:
            logger.error(f"[TTS] ElevenLabs loi: {e}")
            ELEVENLABS_POOL.mark_failed(key)
            return False

    async def _try_edge_tts(self, text: str, output_path: str) -> bool:
        try:
            import edge_tts

            communicate = edge_tts.Communicate(text, "vi-VN-NamMinhNeural")
            await communicate.save(output_path)
            return True
        except Exception as e:
            logger.error(f"[TTS] Edge-TTS loi: {e}")
            return False

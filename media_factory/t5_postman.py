"""Tram T5: Dieu phoi API anh/am thanh (bi gioi han boi ResourceLock)."""
import asyncio
import os
import logging
from pathlib import Path
from typing import List, Dict

from media_factory.resource_lock import ResourceLock
from media_factory.tts_engine import TTSEngine
from media_factory.image_generator import ImageGenerator
from media_factory.audio_meter import AudioMeter

logger = logging.getLogger(__name__)


class T5Postman:
    """Dieu phoi sinh anh + audio cho tung scene, co kiem soat tai nguyen."""

    def __init__(self):
        self.resource_lock = ResourceLock()
        self.tts = TTSEngine()
        self.image_gen = ImageGenerator()

    async def process(self, execution_json: dict, temp_dir: str, log: Dict) -> Dict:
        scenes = execution_json.get("scenes", [])
        Path(f"{temp_dir}/audio").mkdir(parents=True, exist_ok=True)
        Path(f"{temp_dir}/images").mkdir(parents=True, exist_ok=True)

        # === 1. Sinh anh cho tung scene ===
        image_tasks = []
        for scene in scenes:
            image_path = f"{temp_dir}/images/{scene['scene_id']}.jpg"
            image_tasks.append(
                self._gen_image(scene, image_path, log)
            )
        await asyncio.gather(*image_tasks)

        # === 2. Sinh audio cho tung dialogue ===
        audio_index = 0
        for scene in scenes:
            for dlg in scene.get("dialogues", []):
                output_path = f"{temp_dir}/audio/{audio_index:04d}.mp3"
                await self._gen_audio(dlg, output_path, log)
                audio_index += 1

        # === 3. Sinh images_list.txt cho FFmpeg ===
        self._write_images_list(scenes, temp_dir)
        return log

    async def _gen_image(self, scene: Dict, image_path: str, log: Dict):
        async with self.resource_lock:
            ok = await self.image_gen.generate(
                scene.get("visual_prompt_en", ""),
                image_path,
                seed=scene.get("visual_lock_seed", 0),
            )
            if ok:
                log["images_count"] += 1
            else:
                log["errors"].append(f"Image fail: {image_path}")

    async def _gen_audio(self, dlg: Dict, output_path: str, log: Dict):
        async with self.resource_lock:
            try:
                ok = await self.tts.synthesize(
                    dlg.get("line", ""),
                    dlg.get("voice_id", "premade/Adam"),
                    output_path,
                )
                if ok:
                    log["audio_count"] += 1
                    duration = AudioMeter.get_duration_ms(output_path)
                    log["scene_timings"].append(
                        {"file": os.path.basename(output_path), "duration_ms": duration}
                    )
                    if "Edge-TTS" in str(log):
                        log["fallback_count"] += 1
                else:
                    log["errors"].append(f"Audio fail: {output_path}")
            except Exception as e:
                log["errors"].append(f"Audio exception: {e}")

    def _write_images_list(self, scenes: List[Dict], temp_dir: str):
        list_path = f"{temp_dir}/images_list.txt"
        last_image_path = None
        with open(list_path, "w", encoding="utf-8") as f:
            for scene in scenes:
                image_path = f"{temp_dir}/images/{scene['scene_id']}.jpg"
                if os.path.exists(image_path):
                    f.write(f"file '{image_path}'\n")
                    last_image_path = image_path
                elif last_image_path:
                    f.write(f"file '{last_image_path}'\n")
            if last_image_path:
                f.write(f"file '{last_image_path}'\n")
        logger.info(f"[T5] images_list.txt: {len(scenes)} entries")

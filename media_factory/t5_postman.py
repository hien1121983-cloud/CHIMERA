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
        # Theo doi duration thuc te cua tung audio file theo scene
        scene_audio_durations: Dict[str, float] = {}  # scene_id -> tong ms
        audio_index = 0
        for scene in scenes:
            scene_id = scene["scene_id"]
            scene_total_ms = 0.0
            for dlg in scene.get("dialogues", []):
                output_path = f"{temp_dir}/audio/{audio_index:04d}.mp3"
                duration_ms = await self._gen_audio(dlg, output_path, log)
                scene_total_ms += duration_ms
                audio_index += 1
            scene_audio_durations[scene_id] = scene_total_ms

        # === 3. Sinh images_list.txt cho FFmpeg ===
        # FIX #4: Truyen duration thuc te de FFmpeg biet moi anh hien bao lau.
        self._write_images_list(scenes, temp_dir, scene_audio_durations)
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

    async def _gen_audio(self, dlg: Dict, output_path: str, log: Dict) -> float:
        """Sinh audio cho mot dong thoai. Tra ve duration thuc te (ms)."""
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
                    return duration
                else:
                    log["errors"].append(f"Audio fail: {output_path}")
                    # Fallback: uoc tinh tu estimated_duration_ms
                    return float(dlg.get("estimated_duration_ms", 3000))
            except Exception as e:
                log["errors"].append(f"Audio exception: {e}")
                return float(dlg.get("estimated_duration_ms", 3000))

    def _write_images_list(
        self,
        scenes: List[Dict],
        temp_dir: str,
        scene_audio_durations: Dict[str, float],
    ):
        """Tao images_list.txt cho FFmpeg concat demuxer.

        FIX #4: FFmpeg concat demuxer yeu cau chi thi 'duration' cho moi entry
        de biet moi anh can hien bao lau. Khong co 'duration', toan bo anh
        co the duoc hien voi cung thoi luong mac dinh (thay vi khop voi audio),
        dan den video bi sai timing nghiem trong.

        Format dung:
            file '/path/to/image.jpg'
            duration 3.500
            file '/path/to/image.jpg'   <- entry cuoi lap lai (FFmpeg requirement)
        """
        list_path = f"{temp_dir}/images_list.txt"
        last_image_path = None

        with open(list_path, "w", encoding="utf-8") as f:
            for scene in scenes:
                scene_id = scene["scene_id"]
                image_path = f"{temp_dir}/images/{scene_id}.jpg"

                # Tinh duration: uu tien duration thuc te tu audio,
                # fallback ve estimated_duration_ms tu dialogues.
                actual_ms = scene_audio_durations.get(scene_id)
                if actual_ms and actual_ms > 0:
                    duration_s = actual_ms / 1000.0
                else:
                    # Fallback: cong don estimated_duration_ms cua tat ca dialogues
                    estimated_ms = sum(
                        d.get("estimated_duration_ms", 3000)
                        for d in scene.get("dialogues", [])
                    )
                    duration_s = estimated_ms / 1000.0 if estimated_ms > 0 else 3.0

                # Dam bao toi thieu 1 giay/frame
                duration_s = max(duration_s, 1.0)

                target_path = image_path if os.path.exists(image_path) else last_image_path
                if target_path:
                    f.write(f"file '{target_path}'\n")
                    f.write(f"duration {duration_s:.3f}\n")
                    if os.path.exists(image_path):
                        last_image_path = image_path

            # FFmpeg concat demuxer yeu cau entry cuoi khong co 'duration'
            # hoac lap lai entry cuoi mot lan nua de tranh last-frame blink.
            if last_image_path:
                f.write(f"file '{last_image_path}'\n")

        total_duration = sum(
            (scene_audio_durations.get(s["scene_id"], 0) or
             sum(d.get("estimated_duration_ms", 3000) for d in s.get("dialogues", [])))
            / 1000.0
            for s in scenes
        )
        logger.info(
            f"[T5] images_list.txt: {len(scenes)} scenes, "
            f"tong thoi luong uoc tinh ~{total_duration:.1f}s"
        )

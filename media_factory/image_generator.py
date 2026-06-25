"""Image Generator: Pollinations AI (mien phi, khong can key) + retry."""
import asyncio
import logging
import urllib.parse

import aiohttp

logger = logging.getLogger(__name__)


class ImageGenerator:
    BASE_URL = "https://image.pollinations.ai/prompt"

    async def generate(
        self,
        prompt: str,
        output_path: str,
        seed: int = 0,
        width: int = 720,
        height: int = 1280,
        max_retries: int = 3,
    ) -> bool:
        for attempt in range(max_retries):
            ok = await self._call_pollinations(
                prompt, output_path, seed, width, height
            )
            if ok:
                return True
            wait = 2 ** (attempt + 1)
            logger.warning(
                f"[Image] Attempt {attempt + 1}/{max_retries} fail, cho {wait}s"
            )
            await asyncio.sleep(wait)
        logger.error(f"[Image] That bai sau {max_retries} retry: {output_path}")
        return False

    async def _call_pollinations(
        self, prompt: str, output_path: str, seed: int, width: int, height: int
    ) -> bool:
        """Goi Pollinations AI API."""
        encoded_prompt = urllib.parse.quote(prompt)
        url = (
            f"{self.BASE_URL}/{encoded_prompt}"
            f"?width={width}&height={height}&seed={seed}&nologo=true"
        )
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=120)
                ) as resp:
                    if resp.status != 200:
                        return False
                    data = await resp.read()
                    with open(output_path, "wb") as f:
                        f.write(data)
            return True
        except Exception as e:
            logger.error(f"[Image] Pollinations loi: {e}")
            return False

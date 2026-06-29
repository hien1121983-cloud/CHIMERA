import json
import logging
import os
from pathlib import Path
from typing import Optional, Tuple

# BỎ DÒNG NÀY: import google.generativeai as genai
# THÊM DÒNG NÀY:
from cerebras.cloud.sdk import Cerebras

from core.db_client import ChimeraDB
# ĐỔI GEMINI_POOL THÀNH CEREBRAS_POOL:
from core.credential_manager import CEREBRAS_POOL
from simulator.models_genesis import GenesisOutput
from simulator.engines.world_map_engine import WorldMapEngine
from simulator.engines.world_history_engine import WorldHistoryEngine
from simulator.engines.world_rules_engine import WorldRulesEngine

logger = logging.getLogger(__name__)

SEED_PATH = Path("database_seeds/world/world_genesis_seed.json")
GENESIS_FLAG_COLLECTION = "world_info"
# SỬ DỤNG MODEL LLAMA CỦA CEREBRAS:
MODEL_NAME = "llama3.3-70b" 

GENESIS_SYSTEM_PROMPT = """Bạn là kiến trúc sư thế giới của CHIMERA... 
(GIỮ NGUYÊN TOÀN BỘ NỘI DUNG PROMPT NÀY CỦA BẠN)
"""

class WorldGenesis:
    # ... (Giữ nguyên hàm __init__, run, _load_seed, _enrich_seed_with_db_factions)

    def _health_check_key(self, key: str) -> bool:
        """Say hi với Cerebras để xác nhận key còn sống."""
        try:
            client = Cerebras(api_key=key)
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": "Say hi"}],
                max_completion_tokens=10,
                temperature=0.0
            )
            is_live = bool(resp.choices and resp.choices[0].message.content)
            if is_live:
                logger.info(f"[WorldGenesis] Key {key[:12]}... ✅ live")
            else:
                logger.warning(f"[WorldGenesis] Key {key[:12]}... ⚠️ empty response")
            return is_live
        except Exception as e:
            logger.warning(f"[WorldGenesis] Key {key[:12]}... ❌ failed: {e}")
            return False

    def _call_llm_with_healthcheck(self, seed: dict) -> Tuple[Optional[str], Optional[GenesisOutput]]:
        """Xoay vòng key Cerebras: health-check trước, LLM call sau."""
        max_attempts = CEREBRAS_POOL.active_count + 1

        for attempt in range(max_attempts):
            key = CEREBRAS_POOL.get_next()
            if not key:
                logger.error("[WorldGenesis] Pool hết key.")
                break

            if not self._health_check_key(key):
                CEREBRAS_POOL.mark_failed(key)
                continue

            try:
                output = self._call_genesis_llm(key, seed)
                if output:
                    return key, output
            except Exception as e:
                logger.error(f"[WorldGenesis] LLM call thất bại (attempt {attempt+1}): {e}")
                CEREBRAS_POOL.mark_failed(key)

        return None, None

    def _call_genesis_llm(self, key: str, seed: dict) -> Optional[GenesisOutput]:
        """Gọi Cerebras API để sinh thế giới (Bắt buộc trả JSON)."""
        client = Cerebras(api_key=key)

        schema_str = json.dumps(GenesisOutput.model_json_schema(), ensure_ascii=False, indent=2)
        system_prompt = (
            GENESIS_SYSTEM_PROMPT
            + f"\n\nJSON SCHEMA BẮT BUỘC:\n{schema_str}"
        )

        user_content = (
            f"Hãy sinh WorldMap ({seed.get('num_zones', 12)} zones), "
            f"WorldHistory ({seed.get('num_history_events', 20)} events), "
            f"WorldRules ({seed.get('num_rules', 15)} rules) "
            f"cho thế giới:\n{json.dumps(seed, ensure_ascii=False, indent=2)}"
        )

        logger.info(f"[WorldGenesis] Gọi Cerebras ({MODEL_NAME}) — seed: {seed.get('world_name')}")

        # GỌI CHUẨN OPENAI FORMAT TRÊN CEREBRAS:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            response_format={"type": "json_object"},
            temperature=0.85,
            max_completion_tokens=8192
        )

        raw = response.choices[0].message.content
        logger.debug(f"[WorldGenesis] Raw response length: {len(raw)} chars")

        # Fallback strip markdown nếu cần
        if raw.strip().startswith("```"):
            raw = raw.strip().lstrip("`").lstrip("json").strip()
            if raw.endswith("```"):
                raw = raw[: raw.rfind("```")].strip()

        data = json.loads(raw)
        validated = GenesisOutput(**data)
        logger.info(
            f"[WorldGenesis] ✅ Parse OK — "
            f"{len(validated.world_map.zones)} zones, "
            f"{len(validated.world_history.founding_events)} history events, "
            f"{len(validated.world_rules.rules)} rules."
        )
        return validated

    # ... (Giữ nguyên _persist và _set_completed_flag)
  

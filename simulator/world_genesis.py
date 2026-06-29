"""WorldGenesis — 1 LLM call Gemini để sinh nền móng thế giới.

Luồng:
  1. Đọc world_genesis_seed.json + faction list từ MongoDB
  2. Health-check Gemini pool (say hi với flash 2.5)
  3. 1 LLM call → JSON 3 tầng (WorldMap + WorldHistory + WorldRules)
  4. Parse Pydantic → validate → upsert MongoDB
  5. Set flag genesis_completed = True
"""
import json
import logging
import os
from pathlib import Path
from typing import Optional, Tuple

# THÊM DÒNG NÀY (Nếu chưa có):
from cerebras.cloud.sdk import Cerebras

from core.db_client import ChimeraDB
# ĐẢM BẢO DÙNG CEREBRAS_POOL THAY VÌ GEMINI_POOL:
from core.credential_manager import CEREBRAS_POOL
from simulator.models_genesis import GenesisOutput
from simulator.engines.world_map_engine import WorldMapEngine
from simulator.engines.world_history_engine import WorldHistoryEngine
from simulator.engines.world_rules_engine import WorldRulesEngine

# ... (Tiếp tục code ở dưới)

logger = logging.getLogger(__name__)

SEED_PATH = Path("database_seeds/world/world_genesis_seed.json")
GENESIS_FLAG_COLLECTION = "world_info"
MODEL_NAME = "gemini-2.5-flash"

GENESIS_SYSTEM_PROMPT = """Bạn là kiến trúc sư thế giới của CHIMERA — hệ thống kể chuyện tự động.
Nhiệm vụ: Sinh ra nền móng của một thế giới drama tối tăm dựa trên seed đầu vào.

Trả về JSON hợp lệ với cấu trúc CHÍNH XÁC:
{
  "world_map": {
    "zones": [
      {
        "zone_id": "zone_001",
        "name": "tên zone",
        "controlling_faction": "faction_id",
        "contested_by": [],
        "terrain_type": "tech_hub|underground|neutral_ground|residential|industrial",
        "strategic_value": 0-100,
        "description": "mô tả ngắn",
        "control_pct": 0-100
      }
    ],
    "total_zones": N,
    "generated_at_tick": 0
  },
  "world_history": {
    "era_name": "tên kỷ nguyên",
    "era_tagline": "khẩu hiệu",
    "founding_events": [
      {
        "era": "Before Tick 1",
        "tick_range": "Before Tick 1",
        "event": "mô tả sự kiện",
        "impact": "tác động",
        "involved_factions": ["faction_id"],
        "significance": 0-100
      }
    ],
    "generated_at_tick": 0
  },
  "world_rules": {
    "rules": [
      {
        "rule_id": "wr_001",
        "name": "tên rule",
        "description": "mô tả rule",
        "condition_type": "faction_power_gap|world_pressure_category|tick_modulo|character_count",
        "condition_value": "giá trị ngưỡng",
        "condition_op": "gte|lte|eq|gt|lt",
        "effects": [
          {
            "effect_type": "template_weight|stat_modifier|pressure_multiplier",
            "target": "id hoặc tên stat",
            "value": số_thực
          }
        ],
        "is_active": true,
        "scope": "global|faction|character"
      }
    ],
    "generated_at_tick": 0
  }
}

QUAN TRỌNG:
- Chỉ trả về JSON thuần, không markdown, không giải thích.
- zone_id phải là "zone_001", "zone_002", ...
- rule_id phải là "wr_001", "wr_002", ...
- Mỗi zone có đúng 1 controlling_faction từ danh sách faction_seeds.
- Rules phải có condition và effects hợp lệ.
- Tông: tối tăm, drama, chính trị nội bộ."""


class WorldGenesis:

    def __init__(self, db: Optional[ChimeraDB] = None):
        self.db = db or ChimeraDB()
        self.map_engine     = WorldMapEngine(self.db)
        self.history_engine = WorldHistoryEngine(self.db)
        self.rules_engine   = WorldRulesEngine(self.db)

    # ── Public API ───────────────────────────────────────────────────────────

    def is_completed(self) -> bool:
        doc = self.db.permanent[GENESIS_FLAG_COLLECTION].find_one(
            {"genesis_completed": True}, {"_id": 0}
        )
        return doc is not None

    def run(self, force: bool = False) -> bool:
        """Chạy WorldGenesis. Trả về True nếu thành công."""
        if self.is_completed() and not force:
            logger.info("[WorldGenesis] Đã chạy trước đó. Dùng --force để chạy lại.")
            return True

        logger.info("[WorldGenesis] === BẮT ĐẦU WORLD GENESIS ===")

        # Bước 1: Đọc seed
        seed = self._load_seed()
        if not seed:
            logger.error("[WorldGenesis] Không đọc được seed file.")
            return False
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


    def _persist(self, output: GenesisOutput):
        """Ghi 3 tầng vào MongoDB qua từng engine."""
        self.map_engine.seed_from_genesis(output.world_map.model_dump())
        self.history_engine.seed_from_genesis(output.world_history.model_dump())
        self.rules_engine.seed_from_genesis(output.world_rules.model_dump())
        logger.info("[WorldGenesis] Đã persist 3 tầng vào MongoDB.")

    def _set_completed_flag(self, world_name: str):
        from datetime import datetime, timezone
        self.db.permanent[GENESIS_FLAG_COLLECTION].update_one(
            {},
            {
                "$set": {
                    "genesis_completed": True,
                    "world_name": world_name,
                    "genesis_at": datetime.now(timezone.utc).isoformat(),
                }
            },
            upsert=True,
        )
        logger.info("[WorldGenesis] Flag genesis_completed = True đã lưu.")

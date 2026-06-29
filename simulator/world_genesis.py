"""WorldGenesis — Tách 3 bước LLM call để sinh nền móng thế giới ổn định."""
import json
import logging
from pathlib import Path
from typing import Optional

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from core.db_client import ChimeraDB
from core.credential_manager import GEMINI_POOL
from simulator.models_genesis import GenesisOutput, WorldMap, WorldHistory, WorldRules
from simulator.engines.world_map_engine import WorldMapEngine
from simulator.engines.world_history_engine import WorldHistoryEngine
from simulator.engines.world_rules_engine import WorldRulesEngine

logger = logging.getLogger(__name__)

SEED_PATH = Path("database_seeds/world/world_genesis_seed.json")
GENESIS_FLAG_COLLECTION = "world_info"
MODEL_NAME = "gemini-2.5-flash"

# ✅ TẮT TRIỆT ĐỂ SAFETY FILTER
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

# ── PROMPTS VỚI JSON SCHEMA CỤ THỂ CHO TỪNG BƯỚC ─────────────────────────

PROMPT_MAP = """Bạn là kiến trúc sư bản đồ cho một thế giới giả tưởng phức tạp.
Sinh ra JSON cho WorldMap.
Yêu cầu:
- Trả về ĐÚNG format schema bên dưới. Không markdown, không giải thích.
- BẮT BUỘC phải có TẤT CẢ các field: zone_id, name, controlling_faction, contested_by, terrain_type, strategic_value, description, control_pct, total_zones, generated_at_tick.
- terrain_type phải là một trong: tech_hub, underground, neutral_ground, residential, industrial.
- Mỗi zone phải có controlling_faction từ danh sách faction_seeds.

JSON SCHEMA BẮT BUỘC:
{
  "zones": [
    {
      "zone_id": "zone_001",
      "name": "tên zone",
      "controlling_faction": "faction_id",
      "contested_by": [],
      "terrain_type": "tech_hub",
      "strategic_value": 50,
      "description": "mô tả ngắn",
      "control_pct": 100
    }
  ],
  "total_zones": 1,
  "generated_at_tick": 0
}
"""

PROMPT_HISTORY = """Bạn là sử gia ghi chép lại lịch sử hình thành của một thế giới giả tưởng.
Sinh ra JSON cho WorldHistory.
Yêu cầu:
- Trả về ĐÚNG format schema bên dưới. Không markdown, không giải thích.
- BẮT BUỘC phải có TẤT CẢ các field: era_name, era_tagline, founding_events (với era, tick_range, event, impact, involved_factions, significance), generated_at_tick.
- Các sự kiện phải logic với bản đồ (WorldMap) đã có.

JSON SCHEMA BẮT BUỘC:
{
  "era_name": "tên kỷ nguyên",
  "era_tagline": "khẩu hiệu",
  "founding_events": [
    {
      "era": "Before Tick 1",
      "tick_range": "Before Tick 1",
      "event": "mô tả sự kiện",
      "impact": "tác động",
      "involved_factions": ["faction_id"],
      "significance": 80
    }
  ],
  "generated_at_tick": 0
}
"""

PROMPT_RULES = """Bạn là nhà thiết kế hệ thống luật lệ cho một thế giới giả tưởng.
Sinh ra JSON cho WorldRules.
Yêu cầu:
- Trả về ĐÚNG format schema bên dưới. Không markdown, không giải thích.
- BẮT BUỘC phải có TẤT CẢ các field: rule_id, name, description, condition_type, condition_value, condition_op, effects (với effect_type, target, value), is_active, scope, generated_at_tick.
- condition_type phải là một trong: faction_power_gap, world_pressure_category, tick_modulo, character_count.
- condition_op phải là một trong: gte, lte, eq, gt, lt.
- effect_type phải là một trong: template_weight, stat_modifier, pressure_multiplier.
- scope phải là một trong: global, faction, character.

JSON SCHEMA BẮT BUỘC:
{
  "rules": [
    {
      "rule_id": "wr_001",
      "name": "tên rule",
      "description": "mô tả rule",
      "condition_type": "faction_power_gap",
      "condition_value": "10",
      "condition_op": "gte",
      "effects": [
        {
          "effect_type": "stat_modifier",
          "target": "morale",
          "value": -0.5
        }
      ],
      "is_active": true,
      "scope": "global",
      "generated_at_tick": 0
    }
  ],
  "generated_at_tick": 0
}
"""


class WorldGenesis:
    def __init__(self, db: Optional[ChimeraDB] = None):
        self.db = db or ChimeraDB()
        self.map_engine = WorldMapEngine(self.db)
        self.history_engine = WorldHistoryEngine(self.db)
        self.rules_engine = WorldRulesEngine(self.db)

    # ── PUBLIC API ───────────────────────────────────────────────────────────

    def is_completed(self) -> bool:
        doc = self.db.permanent[GENESIS_FLAG_COLLECTION].find_one(
            {"genesis_completed": True}, {"_id": 0}
        )
        return doc is not None

    def run(self, force: bool = False) -> bool:
        if self.is_completed() and not force:
            logger.info("[WorldGenesis] Đã chạy trước đó. Bỏ qua.")
            return True

        logger.info("[WorldGenesis] === BẮT ĐẦU WORLD GENESIS (3-BƯỚC) ===")
        seed = self._load_seed()
        if not seed:
            return False
        seed = self._enrich_seed_with_db_factions(seed)

        # Lấy 1 key sống để dùng cho cả 3 bước
        key = self._get_live_key()
        if not key:
            logger.critical("[WorldGenesis] Không có key nào hoạt động.")
            return False

        try:
            # BƯỚC 1: SINH MAP
            logger.info("➡️  [Bước 1/3] Đang sinh WorldMap...")
            map_dict = self._execute_llm_call(
                key, PROMPT_MAP,
                f"Sinh WorldMap ({seed.get('num_zones', 12)} zones).\nSeed: {json.dumps(seed, ensure_ascii=False)}"
            )
            world_map = WorldMap(**map_dict)

            # BƯỚC 2: SINH HISTORY (Truyền kèm Map để LLM viết sử logic)
            logger.info("➡️  [Bước 2/3] Đang sinh WorldHistory...")
            history_dict = self._execute_llm_call(
                key, PROMPT_HISTORY,
                f"Sinh WorldHistory ({seed.get('num_history_events', 20)} events).\nSeed: {json.dumps(seed)}\nContext Map: {json.dumps(map_dict, ensure_ascii=False)}"
            )
            world_history = WorldHistory(**history_dict)

            # BƯỚC 3: SINH RULES
            logger.info("➡️  [Bước 3/3] Đang sinh WorldRules...")
            rules_dict = self._execute_llm_call(
                key, PROMPT_RULES,
                f"Sinh WorldRules ({seed.get('num_rules', 15)} rules).\nSeed: {json.dumps(seed)}\nContext: {json.dumps({'map': map_dict, 'history': history_dict}, ensure_ascii=False)}"
            )
            world_rules = WorldRules(**rules_dict)

            # GHÉP LẠI VÀ LƯU
            genesis_output = GenesisOutput(
                world_map=world_map,
                world_history=world_history,
                world_rules=world_rules
            )

            self._persist(genesis_output)
            self._set_completed_flag(seed.get("world_name", "Chimerean Nexus"))
            logger.info("[WorldGenesis] === HOÀN TẤT 3 BƯỚC ===")
            return True

        except Exception as e:
            logger.error(f"[WorldGenesis] Lỗi trong quá trình sinh: {e}")
            if "API_KEY_INVALID" in str(e) or "403" in str(e):
                GEMINI_POOL.mark_failed(key)
            return False

    # ── INTERNAL HELPERS ─────────────────────────────────────────────────────

    def _get_live_key(self) -> Optional[str]:
        """Tìm 1 key còn sống. Dùng prompt vô hại nhất để tránh bị block."""
        max_tries = GEMINI_POOL.active_count + 1
        for _ in range(max_tries):
            key = GEMINI_POOL.get_next()
            if not key:
                break

            try:
                genai.configure(api_key=key)
                model = genai.GenerativeModel(MODEL_NAME)
                # Test bằng số "1" - không thể bị Safety Filter chặn
                resp = model.generate_content(
                    "Reply with the number 1",
                    generation_config={"max_output_tokens": 5, "temperature": 0.0},
                    safety_settings=SAFETY_SETTINGS
                )
                if resp.text and "1" in resp.text:
                    logger.info(f"✅ Chọn key {key[:12]}... để chạy genesis.")
                    return key
                else:
                    logger.warning(f"Key {key[:12]}... trả về kết quả lạ. Bỏ qua.")
                    GEMINI_POOL.mark_failed(key)
            except Exception as e:
                logger.warning(f"Key {key[:12]}... lỗi: {e}. Bỏ qua.")
                GEMINI_POOL.mark_failed(key)
        return None

    def _execute_llm_call(self, key: str, system_prompt: str, user_prompt: str) -> dict:
        """Gọi LLM, ép JSON, trả về dict."""
        genai.configure(api_key=key)
        model = genai.GenerativeModel(
            MODEL_NAME,
            system_instruction=system_prompt,
        )

        response = model.generate_content(
            user_prompt,
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.8,
                "max_output_tokens": 16384,  # 16k tokens cho mỗi component
            },
            safety_settings=SAFETY_SETTINGS,
        )

        # Xử lý lỗi block hoặc rỗng
        if not response.candidates:
            raise ValueError("Response không có candidates.")
        
        if response.candidates[0].finish_reason == 2:
            raise ValueError("Response bị chặn bởi Safety Filter của Google.")

        raw = response.text
        if not raw:
            raise ValueError("LLM trả về text rỗng.")

        # Strip markdown
        if raw.strip().startswith("```"):
            raw = raw.strip().lstrip("`").lstrip("json").strip()
            if raw.endswith("```"):
                raw = raw[: raw.rfind("```")].strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"JSON Decode Error: {e}\nRaw text: {raw[:500]}...")
            raise ValueError(f"LLM trả về JSON lỗi: {e}")

    def _load_seed(self) -> Optional[dict]:
        try:
            with open(SEED_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Lỗi đọc seed: {e}")
            return None

    def _enrich_seed_with_db_factions(self, seed: dict) -> dict:
        try:
            blueprints = list(
                self.db.permanent.character_blueprints.find(
                    {}, {"_id": 0, "blueprint_id": 1, "archetype_name": 1}
                )
            )
            if blueprints:
                seed["db_blueprints"] = blueprints
        except Exception as e:
            logger.warning(f"Không lấy được blueprints: {e}")
        return seed

    def _persist(self, output: GenesisOutput):
        self.map_engine.seed_from_genesis(output.world_map.model_dump())
        self.history_engine.seed_from_genesis(output.world_history.model_dump())
        self.rules_engine.seed_from_genesis(output.world_rules.model_dump())
        logger.info("Đã persist 3 tầng vào MongoDB.")

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

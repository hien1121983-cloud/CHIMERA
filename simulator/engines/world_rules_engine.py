"""WorldRulesEngine: Đọc và áp dụng WorldRules vào simulation."""
import logging
from typing import List, Dict, Any

from core.db_client import ChimeraDB

logger = logging.getLogger(__name__)

COLLECTION = "world_rules"


class WorldRulesEngine:

    def __init__(self, db: ChimeraDB):
        self.db = db

    # ── Seed ────────────────────────────────────────────────────────────────

    def seed_from_genesis(self, world_rules_data: Dict):
        """Ghi WorldRules từ WorldGenesis vào MongoDB."""
        self.db.permanent[COLLECTION].delete_many({})
        self.db.permanent[COLLECTION].insert_one(world_rules_data)
        logger.info(
            f"[WorldRulesEngine] Đã seed "
            f"{len(world_rules_data.get('rules', []))} rules."
        )

    # ── Read ────────────────────────────────────────────────────────────────

    def get_active_rules(self) -> List[Dict]:
        doc = self.db.permanent[COLLECTION].find_one({}, {"_id": 0})
        if not doc:
            return []
        return [r for r in doc.get("rules", []) if r.get("is_active", True)]

    def _evaluate_condition(self, rule: Dict, world_context: Dict) -> bool:
        """Kiểm tra xem điều kiện của rule có được kích hoạt không."""
        ctype = rule.get("condition_type", "")
        cval  = rule.get("condition_value", "")
        cop   = rule.get("condition_op", "gte")

        try:
            if ctype == "faction_power_gap":
                powers = world_context.get("faction_powers", {})
                if len(powers) < 2:
                    return False
                gap = max(powers.values()) - min(powers.values())
                return self._compare(gap, float(cval), cop)

            if ctype == "world_pressure_category":
                categories = world_context.get("pressure_categories", [])
                return cval in categories

            if ctype == "tick_modulo":
                tick = world_context.get("tick", 0)
                mod_val, mod_rem = cval.split(":")
                return (tick % int(mod_val)) == int(mod_rem)

            if ctype == "character_count":
                count = world_context.get("alive_character_count", 0)
                return self._compare(count, float(cval), cop)

        except Exception as e:
            logger.warning(f"[WorldRulesEngine] Lỗi evaluate rule {rule.get('rule_id')}: {e}")

        return False

    @staticmethod
    def _compare(actual: float, threshold: float, op: str) -> bool:
        if op == "gte":  return actual >= threshold
        if op == "lte":  return actual <= threshold
        if op == "eq":   return actual == threshold
        if op == "gt":   return actual > threshold
        if op == "lt":   return actual < threshold
        return False

    # ── Apply ────────────────────────────────────────────────────────────────

    def get_template_multipliers(
        self, world_context: Dict
    ) -> Dict[str, float]:
        """Trả về Dict[template_id → multiplier] cho các rule đang kích hoạt."""
        multipliers: Dict[str, float] = {}
        for rule in self.get_active_rules():
            if not self._evaluate_condition(rule, world_context):
                continue
            for effect in rule.get("effects", []):
                if effect.get("effect_type") == "template_weight":
                    tid = effect.get("target", "")
                    val = float(effect.get("value", 1.0))
                    multipliers[tid] = multipliers.get(tid, 1.0) * val
                    logger.debug(
                        f"[WorldRulesEngine] Rule {rule['rule_id']} → "
                        f"template {tid} × {val}"
                    )
        return multipliers

    def get_stat_modifiers(
        self, faction_id: str, world_context: Dict
    ) -> Dict[str, float]:
        """Trả về Dict[stat → delta] áp dụng cho faction/nhân vật trong faction đó."""
        modifiers: Dict[str, float] = {}
        for rule in self.get_active_rules():
            scope = rule.get("scope", "global")
            if scope == "faction" and world_context.get("faction_id") != faction_id:
                continue
            if not self._evaluate_condition(rule, world_context):
                continue
            for effect in rule.get("effects", []):
                if effect.get("effect_type") == "stat_modifier":
                    stat = effect.get("target", "")
                    val  = float(effect.get("value", 0.0))
                    modifiers[stat] = modifiers.get(stat, 0.0) + val
        return modifiers

    def get_pressure_multipliers(self, world_context: Dict) -> Dict[str, float]:
        """Trả về Dict[pressure_category → multiplier] từ rules đang active."""
        multipliers: Dict[str, float] = {}
        for rule in self.get_active_rules():
            if not self._evaluate_condition(rule, world_context):
                continue
            for effect in rule.get("effects", []):
                if effect.get("effect_type") == "pressure_multiplier":
                    cat = effect.get("target", "")
                    val = float(effect.get("value", 1.0))
                    multipliers[cat] = multipliers.get(cat, 1.0) * val
        return multipliers

    def get_active_rules_summary(self, world_context: Dict) -> List[Dict]:
        """Danh sách rule đang kích hoạt — đưa vào ContextSliceV2."""
        return [
            {
                "rule_id":     r["rule_id"],
                "name":        r["name"],
                "description": r.get("description", ""),
                "scope":       r.get("scope", "global"),
            }
            for r in self.get_active_rules()
            if self._evaluate_condition(r, world_context)
        ]

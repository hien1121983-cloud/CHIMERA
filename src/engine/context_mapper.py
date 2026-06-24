"""Context Mapper (Vá #4) — dịch character_state khi chuyển world.

Đọc data/mapping_dictionary.json. Nếu không tìm thấy rule cho cặp
(from_world, to_world) → giữ nguyên state + log warning.
"""
from __future__ import annotations
import json
from copy import deepcopy
from pathlib import Path
from typing import Dict, Optional

from ..utils import get_logger

log = get_logger("context_mapper")

_ROOT = Path(__file__).resolve().parents[2]
_MAPPING_PATH = _ROOT / "data" / "mapping_dictionary.json"


class ContextMapper:
    def __init__(self, mapping_path: Optional[Path] = None) -> None:
        path = mapping_path or _MAPPING_PATH
        try:
            self.mapping: Dict[str, dict] = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("Không load được mapping_dictionary: %s", e)
            self.mapping = {}

    def _get_rules(self, from_world: str, to_world: str) -> Optional[dict]:
        key = f"{from_world} → {to_world}"
        return self.mapping.get(key) or self.mapping.get(f"any → {to_world}")

    def map_state_to_world(self, character_state: dict, from_world: str, to_world: str) -> dict:
        if from_world == to_world:
            return character_state
        rules = self._get_rules(from_world, to_world)
        if not rules:
            log.warning("Không có rule cho %s → %s, giữ nguyên state.", from_world, to_world)
            return character_state

        s = deepcopy(character_state)
        currency_map = rules.get("currency_map", {})
        item_map = rules.get("item_map", {})
        concept_map = rules.get("concept_map", {})

        # Debts
        for debt in s.get("debts", []) or []:
            cur = debt.get("currency")
            if cur and cur in currency_map:
                rule = currency_map[cur]
                rate = rule.get("rate", 1.0)
                debt["amount"] = round(float(debt.get("amount", 0)) * rate, 2)
                debt["currency"] = rule.get("target", cur)
            if debt.get("item_name") in item_map:
                debt["item_name"] = item_map[debt["item_name"]]

        # Items
        for item in s.get("items", []) or []:
            name = item.get("name")
            if name in item_map:
                item["original_name"] = name
                item["name"] = item_map[name]

        # Secrets / concepts
        for sec in s.get("secrets", []) or []:
            concept = sec.get("concept")
            if concept and concept in concept_map:
                sec["original_concept"] = concept
                sec["concept"] = concept_map[concept]
                if "description" in sec:
                    sec["description"] = concept_map[concept]

        s["_mapped_from"] = from_world
        s["_mapped_to"] = to_world
        return s


_DEFAULT: Optional[ContextMapper] = None


def default_mapper() -> ContextMapper:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = ContextMapper()
    return _DEFAULT

def apply_context(character_state: dict, from_world: str, to_world: str) -> dict:
    """Module-level wrapper — dịch character_state khi chuyển world.

    Dùng singleton ``default_mapper()``. Nếu thiếu rule sẽ giữ nguyên state
    (xem ``ContextMapper.map_state_to_world``).
    """
    return default_mapper().map_state_to_world(character_state, from_world, to_world)

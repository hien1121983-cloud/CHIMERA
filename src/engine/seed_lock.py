"""Character Seed Locking (Vá #6).

Sinh seed cố định cho mỗi nhân vật (SHA-256 → mod 2**32) và cache vào
Mongo NO1 collection `character_seeds`. Fallback: in-process cache nếu
Mongo offline.
"""
from __future__ import annotations
import hashlib
from typing import Dict

from ..utils import get_logger

log = get_logger("seed_lock")

_LOCAL_CACHE: Dict[str, int] = {}


def compute_seed(full_name: str, blueprint_origin: str = "", visual_anchor: str = "") -> int:
    raw = f"{full_name}|{blueprint_origin}|{visual_anchor}".encode("utf-8")
    h = hashlib.sha256(raw).hexdigest()
    return int(h, 16) % (2 ** 32)


def get_stable_seed(character: dict) -> int:
    eid = str(character.get("entity_id") or character.get("id") or character.get("full_name", ""))
    if not eid:
        return 0
    if eid in _LOCAL_CACHE:
        return _LOCAL_CACHE[eid]

    # Thử Mongo NO1
    try:
        from ..storage import mongo
        col = mongo.db_inputs()["character_seeds"]
        doc = col.find_one({"entity_id": eid})
        if doc and "seed" in doc:
            _LOCAL_CACHE[eid] = int(doc["seed"])
            return _LOCAL_CACHE[eid]

        seed = compute_seed(
            character.get("full_name", eid),
            character.get("blueprint_origin", ""),
            character.get("visual_anchor", ""),
        )
        col.update_one(
            {"entity_id": eid},
            {"$set": {"entity_id": eid, "seed": seed,
                      "full_name": character.get("full_name", "")}},
            upsert=True,
        )
        _LOCAL_CACHE[eid] = seed
        return seed
    except Exception as e:
        log.warning("Mongo seed cache fail (%s) — local only.", e)
        seed = compute_seed(
            character.get("full_name", eid),
            character.get("blueprint_origin", ""),
            character.get("visual_anchor", ""),
        )
        _LOCAL_CACHE[eid] = seed
        return seed
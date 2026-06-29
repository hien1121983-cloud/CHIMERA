"""WorldMapEngine: Quản lý lãnh thổ faction trên WorldMap."""
import logging
from typing import List, Dict, Optional

from core.db_client import ChimeraDB

logger = logging.getLogger(__name__)


class WorldMapEngine:
    COLLECTION = "world_map"

    def __init__(self, db: ChimeraDB):
        self.db = db

    # ── Read ────────────────────────────────────────────────────────────────

    def get_all_zones(self) -> List[Dict]:
        doc = self.db.permanent[self.COLLECTION].find_one({}, {"_id": 0})
        if not doc:
            return []
        return doc.get("zones", [])

    def get_faction_territory(self, faction_id: str) -> Dict:
        """Trả về % kiểm soát và danh sách zone của faction."""
        zones = self.get_all_zones()
        if not zones:
            return {"faction_id": faction_id, "control_pct": 0, "zones": []}

        controlled = [
            z for z in zones if z.get("controlling_faction") == faction_id
        ]
        total_value = sum(z.get("strategic_value", 0) for z in zones) or 1
        faction_value = sum(z.get("strategic_value", 0) for z in controlled)

        return {
            "faction_id": faction_id,
            "zone_count": len(controlled),
            "strategic_control_pct": round(faction_value / total_value * 100, 1),
            "zones": [z["zone_id"] for z in controlled],
        }

    def get_contested_zones(self) -> List[Dict]:
        """Trả về các zone đang có tranh chấp (contested_by không rỗng)."""
        return [
            z for z in self.get_all_zones()
            if z.get("contested_by")
        ]

    def get_strategic_map_summary(self) -> Dict:
        """Tóm tắt bản đồ cho ContextSliceV2."""
        zones = self.get_all_zones()
        if not zones:
            return {"status": "genesis_not_run", "zones": []}

        faction_control: Dict[str, int] = {}
        for z in zones:
            fid = z.get("controlling_faction", "unknown")
            faction_control[fid] = faction_control.get(fid, 0) + 1

        return {
            "total_zones": len(zones),
            "contested_count": len(self.get_contested_zones()),
            "faction_control": faction_control,
            "hotspots": [
                {
                    "zone_id": z["zone_id"],
                    "name": z.get("name", ""),
                    "contested_by": z.get("contested_by", []),
                }
                for z in self.get_contested_zones()
            ],
        }

    # ── Write ───────────────────────────────────────────────────────────────

    def apply_territory_delta(
        self,
        faction_id: str,
        zone_id: str,
        action: str,  # "take" | "contest" | "release"
    ):
        """Cập nhật trạng thái lãnh thổ của một zone."""
        zones = self.get_all_zones()
        changed = False

        for z in zones:
            if z.get("zone_id") != zone_id:
                continue

            if action == "take":
                z["controlling_faction"] = faction_id
                z["contested_by"] = []
                changed = True
            elif action == "contest":
                if faction_id not in z.get("contested_by", []):
                    z.setdefault("contested_by", []).append(faction_id)
                    changed = True
            elif action == "release":
                z["contested_by"] = [
                    f for f in z.get("contested_by", []) if f != faction_id
                ]
                changed = True
            break

        if changed:
            doc = self.db.permanent[self.COLLECTION].find_one({})
            if doc:
                self.db.permanent[self.COLLECTION].update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"zones": zones}},
                )
                logger.info(
                    f"[WorldMapEngine] Zone {zone_id}: {action} by {faction_id}"
                )

    def seed_from_genesis(self, world_map_data: Dict):
        """Ghi WorldMap từ WorldGenesis vào MongoDB (chỉ chạy 1 lần)."""
        self.db.permanent[self.COLLECTION].delete_many({})
        self.db.permanent[self.COLLECTION].insert_one(world_map_data)
        logger.info(
            f"[WorldMapEngine] Đã seed {len(world_map_data.get('zones', []))} zones."
        )

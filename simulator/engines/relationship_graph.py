"""Engine quan ly do thi quan he giua nhan vat."""
import logging
from typing import Dict

from core.db_client import ChimeraDB

logger = logging.getLogger(__name__)


class RelationshipGraph:
    def __init__(self, db: ChimeraDB):
        self.db = db

    def apply(self, delta: Dict):
        source = delta.get("source")
        target = delta.get("target")
        changes = delta.get("changes", {})
        if not source or not target or not changes:
            logger.warning(f"[RelationshipGraph] Delta khong hop le: {delta}")
            return

        inc = {f"edges.{target}.{k}": v for k, v in changes.items()}
        self.db.permanent.relationships.update_one(
            {"source": source},
            {"$inc": inc},
            upsert=True,
        )
        logger.info(f"[RelationshipGraph] {source}->{target}: {changes}")

    def get_hot_edges(self, limit: int = 50) -> Dict:
        """Lay cac canh quan he 'nong' (giam tai cho context slice)."""
        result: Dict = {}
        for doc in self.db.permanent.relationships.find({}, {"_id": 0}).limit(limit):
            result[doc.get("source", "?")] = doc.get("edges", {})
        return result

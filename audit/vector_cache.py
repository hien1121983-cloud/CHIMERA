"""Cache embedding cua 50 tap gan nhat."""
import logging

from core.db_client import ChimeraDB

logger = logging.getLogger(__name__)


class VectorCache:
    """Quan ly cache embeddings cac tap cu (Canon)."""

    def __init__(self, max_episodes: int = 50):
        self.db = ChimeraDB()
        self.max_episodes = max_episodes
        self.embeddings = []  # list[list[float]]
        self.texts = []       # list[str]

    def load_recent(self):
        """Load embedding cua max_episodes tap gan nhat."""
        self.embeddings = []
        self.texts = []
        docs = list(
            self.db.canon.episode_embeddings.find({}, {"_id": 0})
            .sort("episode_number", -1)
            .limit(self.max_episodes)
        )
        for d in docs:
            if d.get("embedding") is not None:
                self.embeddings.append(d["embedding"])
                self.texts.append(d.get("summary", ""))
        logger.info(f"[VectorCache] Loaded {len(self.embeddings)} embeddings")
        return self.embeddings

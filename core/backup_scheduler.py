"""Export collection ra Google Cloud Storage voi retry + backoff."""
import os
import json
import gzip
import time
import logging
from datetime import datetime

import pymongo

logger = logging.getLogger(__name__)


def export_to_gcs(collection_name: str, db, max_retries: int = 3) -> bool:
    """Export collection ra GCS voi retry 3 lan + exponential backoff."""
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(os.getenv("GCS_BUCKET_NAME"))

    for attempt in range(max_retries):
        try:
            data = list(db[collection_name].find({}, {"_id": 0}))
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"backups/{collection_name}/{timestamp}.json.gz"

            compressed = gzip.compress(
                json.dumps(data, ensure_ascii=False).encode("utf-8")
            )
            blob = bucket.blob(filename)
            blob.upload_from_string(compressed, content_type="application/gzip")

            logger.info(f"[Backup] {collection_name}: {len(data)} docs -> GCS:{filename}")
            return True
        except Exception as e:
            wait_time = 2 ** (attempt + 1)
            logger.warning(
                f"[Backup] Attempt {attempt + 1}/{max_retries} fail: {e}. "
                f"Cho {wait_time}s..."
            )
            time.sleep(wait_time)

    logger.critical(f"[Backup] {collection_name} that bai sau {max_retries} lan retry")
    return False


def run_full_backup():
    """Chay backup toan bo collection quan trong (cron moi 6 gio)."""
    client = pymongo.MongoClient(os.getenv("MONGODB_URI_PERMANENT"))

    critical_collections = [
        ("chimera_permanent", "character_blueprints"),
        ("chimera_permanent", "world_rules"),
        ("chimera_permanent", "secret_items"),
        ("chimera_permanent", "location_settings"),
        ("chimera_permanent", "archetypes"),
        ("chimera_canon", "episode_summaries"),
        ("chimera_canon", "episode_embeddings"),
    ]

    results = []
    for db_name, coll_name in critical_collections:
        db = client[db_name]
        success = export_to_gcs(coll_name, db)
        results.append((coll_name, success))

    logger.info(
        f"[Backup] Hoan tat: {sum(1 for _, s in results if s)}/{len(results)} thanh cong"
    )
    return results

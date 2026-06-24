"""MongoDB layer — 3 cụm dữ liệu độc lập (3 URI khác nhau).

NO1 (inputs)  : biến + nhân vật + từ khóa + bối cảnh + macguffin pool.
                Collections: entities, contexts, trending_cache, macguffins,
                             current_state (vĩnh viễn, không TTL).
NO2 (scripts) : kịch bản trung gian truyền cho các "xúc tu" (renderer).
                Collections: purgatory (TTL 3 ngày), partial_output, scene_jobs.
NO3 (history) : 50 tập canon để "anh T" đối chiếu chống trùng.
                Collections: canon (FIFO 50 doc), eleven_quota.
"""
from __future__ import annotations
import datetime as dt
import functools
from typing import Dict, List, Optional
import gridfs as _gridfs
from pymongo import MongoClient, ASCENDING, IndexModel, DESCENDING
from ..config import settings
from ..utils import get_logger

log = get_logger("mongo")

_clients: Dict[int, MongoClient] = {}


def _client(idx: int) -> MongoClient:
    """idx ∈ {1,2,3} -> cụm tương ứng."""
    if idx in _clients:
        return _clients[idx]
    uris = settings.mongo_uris
    uri = uris[idx - 1] if 1 <= idx <= len(uris) else ""
    if not uri:
        raise RuntimeError(f"MONGODB_URL_NO{idx} chưa cấu hình.")
    c = MongoClient(uri, maxPoolSize=settings.mongo_pool)
    _clients[idx] = c
    _ensure_indexes(idx, c)
    return c


def db_inputs():
    return _client(1)[settings.mongo_db_inputs]


def db_scripts():
    return _client(2)[settings.mongo_db_scripts]


def db_history():
    return _client(3)[settings.mongo_db_history]


def _ensure_indexes(idx: int, c: MongoClient) -> None:
    if idx == 1:
        d = c[settings.mongo_db_inputs]
        d["current_state"].create_indexes([
            IndexModel([("character_id", ASCENDING)], unique=True),
        ])
        # V4.0 collections
        d["character_seeds"].create_indexes([
            IndexModel([("entity_id", ASCENDING)], unique=True),
        ])
        d["character_souls"].create_indexes([
            IndexModel([("entity_id", ASCENDING)], unique=True),
        ])
        d["entropy_history"].create_indexes([
            IndexModel([("episode_id", ASCENDING)]),
            IndexModel([("timestamp", DESCENDING)]),
        ])
        d["spinoffs"].create_indexes([
            IndexModel([("spinoff_id", ASCENDING)], unique=True),
        ])
    elif idx == 2:
        d = c[settings.mongo_db_scripts]
        d["purgatory"].create_indexes([
            IndexModel([("episode_id", ASCENDING)]),
            IndexModel([("created_at", ASCENDING)],
                       expireAfterSeconds=settings.purgatory_ttl_seconds),
        ])
        d["partial_output"].create_indexes([
            IndexModel([("episode_id", ASCENDING), ("branch_id", ASCENDING), ("stage", ASCENDING)]),
        ])
        d["active_votes"].create_indexes([
            IndexModel([("poll_id", ASCENDING)], unique=True),
            IndexModel([("expires_at", ASCENDING)]),
        ])
        d["comments"].create_indexes([
            IndexModel([("episode_id", ASCENDING)]),
        ])
        d["episode_states"].create_indexes([
            IndexModel([("episode_id", ASCENDING)], unique=True),
            IndexModel([("state", ASCENDING)]),
            IndexModel([("updated_at", ASCENDING)]),
        ])
    elif idx == 3:
        d = c[settings.mongo_db_history]
        d["canon"].create_indexes([
            IndexModel([("episode_id", ASCENDING)], unique=True),
            IndexModel([("committed_at", DESCENDING)]),
        ])


# ============================ NO1 — INPUTS ============================

def load_current_state() -> List[Dict]:
    return list(db_inputs()["current_state"].find({}, {"_id": 0}))


def save_current_state(entities: List[Dict]) -> None:
    col = db_inputs()["current_state"]
    for e in entities:
        col.update_one({"character_id": e["id"]},
                       {"$set": {"character_id": e["id"], **e}},
                       upsert=True)


def load_keywords() -> List[str]:
    doc = db_inputs()["trending_cache"].find_one({"_id": "current"}) or {}
    return doc.get("keywords", [])


def save_keywords(keywords: List[str]) -> None:
    db_inputs()["trending_cache"].update_one(
        {"_id": "current"},
        {"$set": {"keywords": keywords, "at": dt.datetime.utcnow()}},
        upsert=True,
    )


# ============================ NO2 — SCRIPTS ============================

def save_purgatory(episode_id: str, versions: List[Dict]) -> None:
    col = db_scripts()["purgatory"]
    col.delete_many({"episode_id": episode_id})
    col.insert_many([
        {"episode_id": episode_id, "created_at": dt.datetime.utcnow(), **v}
        for v in versions
    ])


def get_purgatory(episode_id: str) -> List[Dict]:
    return list(db_scripts()["purgatory"].find({"episode_id": episode_id}, {"_id": 0}))


def clear_purgatory(episode_id: str) -> None:
    db_scripts()["purgatory"].delete_many({"episode_id": episode_id})


def push_scene_job(episode_id: str, version: int, scene_doc: Dict) -> None:
    """Lưu từng scene đã enrich -> renderer (xúc tu) pull về."""
    db_scripts()["scene_jobs"].insert_one({
        "episode_id": episode_id, "version": version,
        "scene": scene_doc.get("scene"),
        "payload": scene_doc, "at": dt.datetime.utcnow(),
    })


def save_partial(episode_id: str, branch_id: str, stage: str, payload: Dict) -> None:
    db_scripts()["partial_output"].update_one(
        {"episode_id": episode_id, "branch_id": branch_id, "stage": stage},
        {"$set": {"payload": payload, "at": dt.datetime.utcnow()}},
        upsert=True,
    )


def load_partial(episode_id: str, branch_id: str, stage: str) -> Optional[Dict]:
    doc = db_scripts()["partial_output"].find_one(
        {"episode_id": episode_id, "branch_id": branch_id, "stage": stage}
    )
    return (doc or {}).get("payload")


# ============================ NO3 — HISTORY (50 tập) ============================

def commit_canon(episode_id: str, version: int, script: Dict, character_state: List[Dict]) -> None:
    col = db_history()["canon"]
    col.update_one(
        {"episode_id": episode_id},
        {"$set": {
            "episode_id": episode_id, "version": version, "script": script,
            "character_state": character_state, "committed_at": dt.datetime.utcnow(),
        }},
        upsert=True,
    )
    _fifo_trim(settings.history_keep)


def _fifo_trim(keep: int) -> None:
    col = db_history()["canon"]
    total = col.count_documents({})
    if total <= keep:
        return
    overflow = total - keep
    olds = list(col.find({}, {"_id": 1}).sort("committed_at", ASCENDING).limit(overflow))
    if olds:
        col.delete_many({"_id": {"$in": [o["_id"] for o in olds]}})
        log.info("FIFO trim: xoá %d tập canon cũ.", len(olds))


def get_canon(episode_id: str) -> Optional[Dict]:
    return db_history()["canon"].find_one({"episode_id": episode_id}, {"_id": 0})


def list_canon_recent(limit: int = 50) -> List[Dict]:
    return list(db_history()["canon"]
                .find({}, {"_id": 0})
                .sort("committed_at", DESCENDING)
                .limit(limit))


# ---------- ElevenLabs quota (đặt ở NO3 cùng cụm history) ----------

def eleven_quota_remaining() -> int:
    month = dt.datetime.utcnow().strftime("%Y-%m")
    doc = db_history()["eleven_quota"].find_one({"month": month}) or {}
    used = doc.get("chars_used", 0)
    return max(0, settings.elevenlabs_monthly_quota - used)


def eleven_quota_consume(n: int) -> None:
    month = dt.datetime.utcnow().strftime("%Y-%m")
    db_history()["eleven_quota"].update_one(
        {"month": month}, {"$inc": {"chars_used": n}}, upsert=True,
    )


# ============================================================
# V4.0 — Helpers cho các collection mới
# ============================================================
def list_recent_canon_with_tags(limit: int = 50) -> List[Dict]:
    """Trả 50 tập canon gần nhất (mới → cũ) cho T-Checker đối chiếu."""
    return list_canon_recent(limit)


# --- character_seeds ---
def get_character_seed(entity_id: str) -> Optional[int]:
    doc = db_inputs()["character_seeds"].find_one({"entity_id": entity_id})
    return int(doc["seed"]) if doc and "seed" in doc else None


def set_character_seed(entity_id: str, seed: int, full_name: str = "") -> None:
    db_inputs()["character_seeds"].update_one(
        {"entity_id": entity_id},
        {"$set": {"entity_id": entity_id, "seed": int(seed), "full_name": full_name}},
        upsert=True,
    )


# --- entropy_history ---
def save_entropy(episode_id: int, metrics: Dict, action_taken: str) -> None:
    db_inputs()["entropy_history"].insert_one({
        "episode_id": episode_id,
        "timestamp": dt.datetime.utcnow(),
        "metrics": metrics,
        "action_taken": action_taken,
    })


def latest_entropy() -> Optional[Dict]:
    return db_inputs()["entropy_history"].find_one(
        {}, sort=[("timestamp", DESCENDING)]
    )


# --- character_souls (Soft Reboot) ---
def save_character_soul(soul: Dict) -> None:
    db_inputs()["character_souls"].update_one(
        {"entity_id": soul["entity_id"]},
        {"$set": soul},
        upsert=True,
    )


def load_character_souls() -> List[Dict]:
    return list(db_inputs()["character_souls"].find({}, {"_id": 0}))


# --- spinoffs ---
def insert_spinoff(spinoff: Dict) -> None:
    db_inputs()["spinoffs"].update_one(
        {"spinoff_id": spinoff["spinoff_id"]},
        {"$set": spinoff},
        upsert=True,
    )


def list_active_spinoffs() -> List[Dict]:
    return list(db_inputs()["spinoffs"].find({"status": {"$ne": "completed"}}, {"_id": 0}))


# --- purgatory escalation ---
def find_expiring_purgatory(within_hours: int) -> List[Dict]:
    cutoff = dt.datetime.utcnow() - dt.timedelta(
        seconds=settings.purgatory_ttl_seconds - within_hours * 3600
    )
    return list(db_scripts()["purgatory"].find({
        "reviewed": {"$ne": True},
        "created_at": {"$lt": cutoff},
    }))


def find_expired_purgatory() -> List[Dict]:
    cutoff = dt.datetime.utcnow() - dt.timedelta(seconds=settings.purgatory_ttl_seconds)
    return list(db_scripts()["purgatory"].find({
        "reviewed": {"$ne": True},
        "created_at": {"$lt": cutoff},
    }))


def mark_purgatory_reviewed(episode_id: str) -> None:
    db_scripts()["purgatory"].update_many(
        {"episode_id": episode_id},
        {"$set": {"reviewed": True}},
    )


# ============================ EPISODE STATE (NO2) ============================

def set_episode_state(episode_id: str, state: dict) -> None:
    """Lưu/cập nhật trạng thái episode. state là dict chứa ít nhất key 'state'."""
    db_scripts()["episode_states"].update_one(
        {"episode_id": episode_id},
        {"$set": {"episode_id": episode_id, "updated_at": dt.datetime.utcnow(), **state}},
        upsert=True,
    )
    log.info("episode_state %s -> %s", episode_id, state.get("state"))


def find_episode_in_state(state_name: str) -> Optional[Dict]:
    """Tìm episode đầu tiên đang ở trạng thái state_name. Trả None nếu không có."""
    doc = db_scripts()["episode_states"].find_one(
        {"state": state_name},
        {"_id": 0},
        sort=[("updated_at", ASCENDING)],
    )
    return doc or None


# ============================ SCENE 1 BLOB (NO2 — GridFS) ============================



@functools.lru_cache(maxsize=1)
def _gridfs_scripts():
    """GridFS bucket trên db_scripts (NO2) — dùng để lưu scene_01.mp4."""
    client = _client(2)
    db = client[settings.mongo_db_scripts]
    return _gridfs.GridFS(db, collection="scene1_blobs")


def save_scene1_blob(episode_id: str, version: int, data: bytes) -> None:
    """Lưu blob scene_01.mp4 vào GridFS. Ghi đè nếu đã tồn tại."""
    fs = _gridfs_scripts()
    for f in fs.find({"episode_id": episode_id, "version": version}):
        fs.delete(f._id)
    fs.put(
        data,
        episode_id=episode_id,
        version=version,
        filename=f"scene_01_{episode_id}_v{version}.mp4",
        content_type="video/mp4",
        upload_date=dt.datetime.utcnow(),
    )
    log.info("Đã lưu scene1_blob GridFS: %s v%d (%d KB)", episode_id, version, len(data) // 1024)


def load_scene1_blob(episode_id: str, version: int) -> Optional[bytes]:
    """Tải blob scene_01.mp4 từ GridFS. Trả None nếu không tìm thấy."""
    fs = _gridfs_scripts()
    try:
        f = fs.find_one({"episode_id": episode_id, "version": version})
        if f is None:
            log.warning("load_scene1_blob: không tìm thấy %s v%d", episode_id, version)
            return None
        return f.read()
    except Exception as e:
        log.error("load_scene1_blob lỗi: %s", e)
        return None

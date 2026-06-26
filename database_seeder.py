"""
Công cụ Nạp Dữ liệu Nền (Database Seeder) cho CHIMERA V5.0.1
Đọc toàn bộ file JSON từ thư mục local và nạp lên MongoDB Permanent.
"""
import os
import json
import logging
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# Thiết lập hệ thống Log báo cáo
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    handlers=[
        logging.FileHandler("seeding_report.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("DB_SEEDER")

def load_json(filepath):
    """Đọc file JSON an toàn."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"KHÔNG TÌM THẤY FILE: {filepath}. Bỏ qua...")
        return None
    except json.JSONDecodeError:
        logger.error(f"LỖI ĐỊNH DẠNG JSON TẠI: {filepath}. Bỏ qua...")
        return None

def main():
    logger.info("=== BẮT ĐẦU CHIẾN DỊCH NẠP DỮ LIỆU NỀN (SEEDING) ===")
    
    mongo_uri = os.getenv("MONGODB_URI_PERMANENT")
    if not mongo_uri:
        logger.critical("LỖI CRITICAL: Không tìm thấy biến môi trường MONGODB_URI_PERMANENT.")
        return

    try:
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        db = client['chimera_permanent']
        logger.info("Đã kết nối thành công đến Cụm Não Số 1 (MongoDB Atlas).")
    except ConnectionFailure:
        logger.critical("LỖI KẾT NỐI: MongoDB Atlas timeout hoặc sai URI.")
        return

    # === DANH SÁCH NHIỆM VỤ NẠP DỮ LIỆU ===
    
    # 1. Nạp 9 Blueprints (Khung Gen)
    blueprint_dir = "database_seeds/blueprints/"
    if os.path.exists(blueprint_dir):
        db.character_blueprints.delete_many({}) # Xóa cũ nạp mới
        bp_count = 0
        for filename in os.listdir(blueprint_dir):
            if filename.endswith(".json"):
                data = load_json(os.path.join(blueprint_dir, filename))
                if data:
                    db.character_blueprints.insert_one(data)
                    bp_count += 1
        logger.info(f"[SUCCESS] Đã nạp {bp_count}/9 Khung Nhân vật (Blueprints).")

    # 2. Nạp Archetypes (Khung Kịch Bản)
    arc_data = load_json("cache/archetypes_cache.json")
    if arc_data and "story_archetypes" in arc_data:
        db.archetypes.delete_many({})
        # Chuyển object thành mảng để insert
        arcs_to_insert = []
        for arc_id, arc_info in arc_data["story_archetypes"].items():
            arc_info["arc_id"] = arc_id
            arcs_to_insert.append(arc_info)
        db.archetypes.insert_many(arcs_to_insert)
        logger.info(f"[SUCCESS] Đã nạp {len(arcs_to_insert)} Khung Kịch bản (Archetypes).")

    # 3. Nạp Multiverses (Bối cảnh đa vũ trụ)
    multi_data = load_json("database_seeds/world/multiverses.json")
    if multi_data and "multiverses" in multi_data:
        db.world_multiverses.delete_many({})
        db.world_multiverses.insert_many(multi_data["multiverses"])
        logger.info(f"[SUCCESS] Đã nạp {len(multi_data['multiverses'])} Bối cảnh Đa vũ trụ.")

    # 4. Nạp Glitch Curses (Lời nguyền Dị Không)
    curses_data = load_json("database_seeds/world/glitch_curses.json")
    if curses_data and "glitch_curses" in curses_data:
        db.world_glitch_curses.delete_many({})
        db.world_glitch_curses.insert_many(curses_data["glitch_curses"])
        logger.info(f"[SUCCESS] Đã nạp {len(curses_data['glitch_curses'])} Lời nguyền Dị Không.")

    # 5. Nạp Secret Items (Vật phẩm bí mật)
    items_data = load_json("database_seeds/world/secret_items.json")
    if items_data and "items" in items_data:
        db.world_secret_items.delete_many({})
        db.world_secret_items.insert_many(items_data["items"])
        logger.info(f"[SUCCESS] Đã nạp {len(items_data['items'])} Vật phẩm bí mật.")

    # 6. Nạp Voice Mapping (Bảng giọng nói)
    voice_data = load_json("database_seeds/voice_mapping.json")
    if voice_data:
        db.voice_mapping.delete_many({})
        db.voice_mapping.insert_one(voice_data)
        logger.info("[SUCCESS] Đã nạp Bảng gán Giọng nói (Voice Mapping).")

    # 7. Nạp Cấu hình (Config Layer)
    configs = {
        "config_platform_rules": "config/platform_rules.json",
        "config_pattern_map": "config/pattern_to_chimera.json",
        "config_word_substitution": "config/word_substitution_map.json"
    }
    for coll_name, filepath in configs.items():
        data = load_json(filepath)
        if data:
            db[coll_name].delete_many({})
            db[coll_name].insert_one(data)
            logger.info(f"[SUCCESS] Đã nạp cấu hình hệ thống: {filepath}.")

    logger.info("=== HOÀN TẤT CHIẾN DỊCH NẠP DỮ LIỆU ===")

if __name__ == "__main__":
    main()


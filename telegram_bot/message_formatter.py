"""Format thong ke the gioi thanh text dep cho Telegram."""
import os
from typing import Dict

def format_world_stats(master_payload: dict) -> Dict:
    """Trich xuat thong ke the gioi tu Master_Payload."""
    ctx = master_payload.get("context_slice_v2", {})
    return {
        "episode": master_payload.get("meta", {}).get("episode_number", "?"),
        "num_characters": len(ctx.get("layer_2_character_states", {})),
        "num_mandatory": len(ctx.get("layer_6_mandatory_tasks", [])),
        "num_ticking_bombs": len(ctx.get("layer_7_ticking_bombs", [])),
        "num_overdue_hooks": len(ctx.get("layer_8_overdue_hooks", [])),
    }

def export_drafts_to_txt(drafts: list, filepath: str = "cache/all_drafts.txt") -> str:
    """Xuat 3 ban nhap ra file text de Showrunner doc tren Telegram."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("=== XƯỞNG KỊCH BẢN CHIMERA - 3 BẢN NHÁP ===\n")
        f.write("Vui lòng đọc kỹ nội dung và chọn bản ưng ý nhất trên Telegram.\n\n")

        for i, draft in enumerate(drafts):
            f.write(f"{'='*20} BẢN NHÁP SỐ {i+1} {'='*20}\n")
            f.write(f"Mã Draft: {draft.get('draft_id', 'N/A')}\n")
            f.write(f"Điểm sáng tạo: {draft.get('creativity_score', 'N/A')}\n")
            f.write(f"Tóm tắt: {draft.get('synopsis', '')}\n\n")
            f.write("--- NỘI DUNG CHI TIẾT ---\n")
            for scene in draft.get("scenes", []):
                f.write(f"🎬 Cảnh {scene.get('scene_id')} - {scene.get('location_name', 'Unknown')}\n")
                f.write(f"Hành động: {scene.get('action', '')}\n")
                for d in scene.get("dialogues", []):
                    f.write(f"  [{d.get('character')}] ({d.get('emotion')}): {d.get('line')}\n")
                f.write("\n")
            f.write("\n\n")
    return filepath

"""Format thong ke the gioi thanh text dep cho Telegram."""
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


def format_script_summary(master_script: dict) -> str:
    """Tom tat kich ban thanh text HTML dep cho Telegram."""
    meta = master_script.get("meta", {})
    script = master_script.get("script", {})
    scenes = script.get("scenes", [])
    lines = [
        f"<b>Episode {meta.get('episode_number', '?')}</b>",
        f"Synopsis: {script.get('synopsis', '(khong co)')[:300]}",
        f"So phan canh: {len(scenes)}",
        f"Resolved hooks: {', '.join(master_script.get('resolved_hooks', [])) or '-'}",
        f"Similarity: {meta.get('similarity_score', 'n/a')}",
    ]
    return "\n".join(lines)

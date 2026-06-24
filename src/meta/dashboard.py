"""Sinh file Markdown dashboard tóm tắt entropy + canon gần nhất.
Ghi vào history/dashboard.md (idempotent)."""
from __future__ import annotations
import datetime as dt
from pathlib import Path

from ..utils import get_logger

log = get_logger("meta.dashboard")
ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "history" / "dashboard.md"


def generate() -> Path:
    lines = [
        f"# Chimera V4.0 Dashboard",
        f"_Generated: {dt.datetime.utcnow().isoformat()}Z_",
        "",
    ]
    try:
        from . import entropy_monitor
        latest = entropy_monitor.latest()
        if latest:
            lines += [
                "## Latest Entropy",
                f"- Episode: `{latest.get('episode_id')}`",
                f"- Action: **{latest.get('action_taken')}**",
                f"- Metrics: `{latest.get('metrics')}`",
                "",
            ]
    except Exception as e:
        lines.append(f"_entropy fetch error: {e}_")
    try:
        from ..storage import mongo
        recent = mongo.list_canon_recent(10)
        lines.append("## Last 10 canon episodes")
        for d in recent:
            t = (d.get("script") or {}).get("episode_title", "")
            lines.append(f"- `{d.get('episode_id')}` — {t}")
    except Exception as e:
        lines.append(f"_canon fetch error: {e}_")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    log.info("dashboard written -> %s", OUT)
    return OUT


if __name__ == "__main__":
    generate()
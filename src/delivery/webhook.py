"""FastAPI webhook — V4.0 Phase-1 fix.

Trạng thái mới:
- ``approve:<ep>:<ver>`` -> chuyển episode sang trạng thái
  ``awaiting_scene1_upload`` (lưu trong Mongo) rồi nhắc user upload .mp4.
- Khi user gửi message có ``document``/``video`` (.mp4) và episode đang ở
  trạng thái chờ -> tải file qua Telegram getFile, lưu vào storage chung
  (cloud bucket hoặc artifact GitHub) rồi gọi
  ``workflow_dispatch -> assemble_video.yml`` với episode_id + version.
- ``canon:<ep>:<ver>`` (Phase 2) — không thay đổi.

LƯU Ý KIẾN TRÚC TIME-OUT:
Vì GitHub Actions không thể "ngủ" chờ user upload (timeout 30 phút),
workflow ``daily_production.yml`` chỉ làm Stage A (sinh script + gửi duyệt),
sau đó kết thúc. Stage B (sinh ảnh 2..N + ghép FFmpeg + gửi MP4) chạy ở
workflow ``assemble_video.yml`` do webhook này trigger SAU khi nhận đủ
scene_01.mp4. Như vậy máy ảo không bao giờ phải "chờ".
"""
from __future__ import annotations
import os
from pathlib import Path
import requests
from fastapi import FastAPI, Request, Header, HTTPException
from ..config import settings
from ..storage import mongo
from ..utils import get_logger

log = get_logger("webhook")
app = FastAPI(title="Chimera Webhook v4.1")

GH_REPO = os.getenv("GITHUB_REPO", "")
GH_PAT = os.getenv("PAT_GITHUB", "")
TG_API = "https://api.telegram.org/bot{token}/{method}"
TG_FILE = "https://api.telegram.org/file/bot{token}/{path}"


# ---------------- helpers ----------------

def _tg_post(method: str, payload: dict) -> dict:
    r = requests.post(TG_API.format(token=settings.bot_token, method=method),
                      json=payload, timeout=15)
    if not r.ok:
        log.error("TG %s fail: %s", method, r.text[:200])
    return r.json() if r.headers.get("content-type", "").startswith("application/json") else {}


def _trigger_workflow(workflow: str, inputs: dict) -> None:
    if not (GH_REPO and GH_PAT):
        log.warning("Thiếu GITHUB_REPO / PAT_GITHUB — bỏ qua trigger %s.", workflow)
        return
    url = f"https://api.github.com/repos/{GH_REPO}/actions/workflows/{workflow}/dispatches"
    headers = {"Authorization": f"Bearer {GH_PAT}",
               "Accept": "application/vnd.github+json"}
    payload = {"ref": "main", "inputs": {k: str(v) for k, v in inputs.items()}}
    r = requests.post(url, headers=headers, json=payload, timeout=15)
    if not r.ok:
        log.error("Trigger %s fail %s: %s", workflow, r.status_code, r.text)
    else:
        log.info("Trigger workflow %s OK: %s", workflow, inputs)


def _download_telegram_file(file_id: str, dest: Path) -> Path:
    info = _tg_post("getFile", {"file_id": file_id})
    file_path = info.get("result", {}).get("file_path")
    if not file_path:
        raise RuntimeError(f"getFile thiếu file_path: {info}")
    url = TG_FILE.format(token=settings.bot_token, path=file_path)
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        for chunk in r.iter_content(8192):
            if chunk:
                f.write(chunk)
    return dest


# ---------------- routes ----------------

@app.get("/health")
def health(): return {"status": "ok"}


@app.post("/telegram")
async def telegram(request: Request,
                   x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    if settings.webhook_secret and x_telegram_bot_api_secret_token != settings.webhook_secret:
        raise HTTPException(403, "Invalid secret token")
    update = await request.json()

    # ---------- 1) Callback từ inline keyboard ----------
    cq = update.get("callback_query")
    if cq:
        return await _handle_callback(cq)

    # ---------- 2) Message với document/video (.mp4) ----------
    msg = update.get("message") or update.get("edited_message")
    if msg:
        return await _handle_message(msg)

    return {"ok": True}


# ---------------- callback handler ----------------

async def _handle_callback(cq: dict) -> dict:
    data = cq.get("data", "")
    cb_id = cq.get("id")

    if data.startswith("approve:"):
        _, ep, ver = data.split(":", 2)
        # Chuyển sang trạng thái chờ upload
        try:
            mongo.set_episode_state(ep, {
                "state": "awaiting_scene1_upload",
                "version_pending": int(ver),
            })
        except Exception as e:
            log.error("Mongo set_state fail: %s", e)
        if cb_id:
            _tg_post("answerCallbackQuery",
                     {"callback_query_id": cb_id,
                      "text": "Đã duyệt. Hãy upload file .mp4 Scene 1."})
        _tg_post("sendMessage", {
            "chat_id": settings.chat_id,
            "parse_mode": "HTML",
            "text": (f"📥 <b>{ep} v{ver}</b>: đang chờ bạn gửi file <b>.mp4 Scene 1</b>.\n"
                     "Gửi dưới dạng <i>file</i> (Document) hoặc <i>video</i> đều được. "
                     "Tối đa 50MB theo giới hạn Telegram Bot."),
        })
        return {"ok": True, "state": "awaiting_scene1_upload",
                "episode_id": ep, "version": int(ver)}

    if data.startswith("reject:"):
        _, ep, ver = data.split(":", 2)
        try: mongo.set_episode_state(ep, {"state": "rejected",
                                          "version_pending": int(ver)})
        except Exception: pass
        if cb_id:
            _tg_post("answerCallbackQuery",
                     {"callback_query_id": cb_id, "text": "Đã huỷ phiên bản này."})
        return {"ok": True, "state": "rejected"}

    if data.startswith("canon:"):
        return await _handle_canon(cq, data)

    return {"ok": True}


async def _handle_canon(cq: dict, data: str) -> dict:
    _, episode_id, ver_str = data.split(":", 2)
    version = int(ver_str)
    drafts = mongo.get_purgatory(episode_id)
    chosen = next((d for d in drafts if d["version"] == version), None)
    if not chosen:
        return {"ok": False, "error": "draft_not_found"}
    mongo.save_current_state(chosen["character_state"])
    mongo.commit_canon(episode_id, version, chosen["script"], chosen["character_state"])
    mongo.clear_purgatory(episode_id)
    _trigger_workflow("canon_commit.yml",
                      {"episode_id": episode_id, "version": version})
    cb_id = cq.get("id")
    if cb_id:
        _tg_post("answerCallbackQuery",
                 {"callback_query_id": cb_id, "text": f"Đã chốt v{version}"})
    return {"ok": True, "canon": {"episode_id": episode_id, "version": version}}


# ---------------- message (file upload) handler ----------------

async def _handle_message(msg: dict) -> dict:
    # --- Xác thực sender: chỉ chấp nhận message từ đúng chat_id ---
    sender_chat_id = str((msg.get("chat") or {}).get("id", ""))
    if sender_chat_id != str(settings.chat_id):
        log.warning("_handle_message: bỏ qua message từ chat_id lạ: %s", sender_chat_id)
        return {"ok": True, "ignored": "unauthorized_sender"}

    doc = msg.get("document") or msg.get("video")
    if not doc:
        return {"ok": True}
    mime = (doc.get("mime_type") or "").lower()
    name = (doc.get("file_name") or "").lower()
    if "mp4" not in mime and not name.endswith(".mp4"):
        return {"ok": True, "ignored": "not_mp4"}

    # Tìm episode đang chờ
    try:
        pending = mongo.find_episode_in_state("awaiting_scene1_upload")
    except Exception as e:
        log.error("Mongo find pending fail: %s", e)
        pending = None
    if not pending:
        # BP-5: nếu user upload .mp4 trong lúc episode vẫn ở awaiting_approval
        # (chưa bấm Approve), nhắc rõ thứ tự thao tác thay vì im lặng bỏ file.
        try:
            waiting_approval = mongo.find_episode_in_state("awaiting_approval")
        except Exception:
            waiting_approval = None
        if waiting_approval:
            _tg_post("sendMessage", {
                "chat_id": settings.chat_id,
                "text": ("⚠️ Episode đang chờ bạn bấm <b>Approve</b> trước.\n"
                         "Vui lòng duyệt bản kịch bản, sau đó mới upload "
                         "<code>scene_01.mp4</code>."),
                "parse_mode": "HTML",
            })
            return {"ok": True, "ignored": "awaiting_approval_first"}
        _tg_post("sendMessage", {
            "chat_id": settings.chat_id,
            "text": "⚠️ Không có episode nào đang chờ Scene 1. Bỏ qua file."})
        return {"ok": True, "ignored": "no_pending_episode"}

    episode_id = pending["episode_id"]
    version = pending.get("version_pending", 1)

    # Tải file về staging dir
    staging = Path(os.getenv("CHIMERA_STAGING", "/tmp/chimera_staging"))
    dest = staging / episode_id / f"version_{version}" / "scene_01.mp4"
    try:
        _download_telegram_file(doc["file_id"], dest)
    except Exception as e:
        log.error("Tải scene_01.mp4 fail: %s", e)
        _tg_post("sendMessage", {
            "chat_id": settings.chat_id,
            "text": f"❌ Tải file Scene 1 fail: {e}"})
        return {"ok": False, "error": "download_failed"}

    # Lưu blob vào Mongo GridFS-like store để workflow B đọc lại
    try:
        mongo.save_scene1_blob(episode_id, version, dest.read_bytes())
        mongo.set_episode_state(episode_id, {
            "state": "scene1_uploaded",
            "version_pending": version,
        })
    except Exception as e:
        log.error("Lưu scene1 blob fail: %s", e)

    _tg_post("sendMessage", {
        "chat_id": settings.chat_id,
        "parse_mode": "HTML",
        "text": (f"✅ Nhận đủ <b>scene_01.mp4</b> cho {episode_id} v{version} "
                 f"({dest.stat().st_size//1024} KB). Đang khởi động workflow ráp video…"),
    })

    _trigger_workflow("assemble_video.yml", {
        "episode_id": episode_id,
        "version": version,
    })
    return {"ok": True, "assembled": False, "triggered": True}

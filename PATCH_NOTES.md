# Chimera V4.0 — Phase 1 Fix Pack

Bộ vá này **chỉ chứa các file cần sửa/mới**. Copy đè lên repo gốc theo cấu trúc:

```
chimera/
├── assets/
│   ├── README.md                       # NEW — hướng dẫn drop glitch_transition.mp4
│   └── glitch_transition.mp4           # ⚠️ BẠN TỰ THÊM (file tĩnh do bạn dựng)
├── .env.example                        # SỬA — thêm 6 ELEVENLABS_KEY1..6
├── .github/workflows/
│   ├── daily_production.yml            # SỬA — chỉ chạy Stage A (script)
│   └── assemble_video.yml              # NEW — Stage B (sau khi user upload)
└── src/
    ├── config.py                       # SỬA — collect 6 elevenlabs key + assets path
    ├── main.py                         # SỬA — tách 2 stage (--stage produce_script | assemble)
    ├── engine/
    │   ├── elevenlabs_client.py        # NEW — Round-Robin Rotator class
    │   ├── llm_reader.py               # SỬA — Scene 1 dùng cinematic_video_prompt
    │   ├── renderer.py                 # SỬA — bỏ qua Scene 1, dùng Rotator + fallback
    │   └── ffmpeg_builder.py           # SỬA — concat scene_01.mp4 + glitch tĩnh
    └── delivery/
        ├── telegram_bot.py             # SỬA — send_script_for_approval (in đậm prompt)
        └── webhook.py                  # SỬA — flow approve -> wait .mp4 -> trigger Stage B
```

## Tóm tắt 3 yêu cầu đã thực hiện

### 1) Chrono-Glitch Transition = file tĩnh
- File cố định: `chimera/assets/glitch_transition.mp4`.
- `ffmpeg_builder.py` đọc `script["scenes"][i]["is_glitch"]` (do LLM gắn ở
  outline) và **concat cứng** file `.mp4` đó NGAY SAU scene tương ứng,
  bằng filter `concat=n=N:v=1:a=0`. Không API, không prompt.
- Nếu file không có, log cảnh báo và bỏ qua — không crash.

### 2) Scene 1 = Human-in-the-loop
- `llm_reader.py`:
  - Schema mới `SCENE1_SCHEMA` **bắt buộc** `cinematic_video_prompt`
    (tiếng Anh, ≥40 ký tự) và **cấm** `image_prompt`.
  - Scenes 2..N giữ `SCENE_SCHEMA` cũ (vẫn có `image_prompt`).
  - Có hàm tiện ích `extract_hook_video_prompt(script)`.
- `renderer.py`:
  - Hoàn toàn **bỏ qua** Pollinations cho Scene 1.
  - Ghi `scene_01_cinematic_video_prompt.txt` ra ver_dir để audit.
- `telegram_bot.send_script_for_approval()`:
  - Trích `cinematic_video_prompt` riêng, **bọc `<b>…</b>`** (HTML bold)
    để user nhấn-giữ-copy dễ.
  - Inline keyboard: `[✅ DUYỆT — chờ upload Scene 1]` / `[♻️ LÀM LẠI]`.
- `webhook.py`:
  - `approve:` → set Mongo state `awaiting_scene1_upload`.
  - Khi user gửi message kèm document/video `.mp4`, webhook tải file qua
    Telegram getFile, lưu vào Mongo blob store, set state
    `scene1_uploaded`, rồi gọi `repository_dispatch` workflow
    `assemble_video.yml` với inputs `episode_id` + `version`.

### 3) ElevenLabs Round-Robin 6 key + fallback edge-tts
- `engine/elevenlabs_client.py` — `ElevenLabsRotator`:
  - Pool 6 key, cursor xoay vòng có lock thread-safe.
  - Khi HTTP **401/402/403/429** → `mark_dead(key)` + xoay sang key kế.
  - Lỗi mạng / 5xx → thử key kế nhưng KHÔNG mark dead.
  - Cạn cả 6 → raise `QuotaAllExhausted` (không phải Exception thường).
- `renderer.render_voice(text, out, prefer_eleven=True)`:
  - Bắt `QuotaAllExhausted` → tự động fallback `edge-tts` → `gTTS`.
  - Không bao giờ raise nếu một engine free còn sống → pipeline không sập.
- `.env.example` + cả 2 workflow đã khai báo `ELEVENLABS_KEY1..6`.

### 4) Chống GitHub Actions timeout 30 phút
- `daily_production.yml` đổi tên *“Stage A — Script only”*: kết thúc ngay
  sau khi gửi tin nhắn duyệt + cinematic_video_prompt. Không chờ user.
- `assemble_video.yml` mới được trigger bởi webhook **sau khi đã có file
  scene_01.mp4** — chạy nhanh (~10–15 phút) và kết thúc.
- Hai workflow độc lập, dùng `concurrency` group khác nhau, không bao
  giờ đụng giới hạn 30 phút của runner.

## Phụ thuộc Mongo helper mới

`storage/mongo.py` cần thêm 4 hàm (chưa có sẵn trong zip cũ):

```python
def set_episode_state(episode_id: str, state: dict) -> None: ...
def find_episode_in_state(state_name: str) -> dict | None: ...
def save_scene1_blob(episode_id: str, version: int, data: bytes) -> None: ...
def load_scene1_blob(episode_id: str, version: int) -> bytes | None: ...
```

Có thể triển khai bằng 1 collection `episode_states` (NO2) +
`scene1_blobs` (GridFS hoặc Base64 trong document). Cấu trúc tự do.

## Test nhanh trên local

```bash
# 1. Sinh script + gửi duyệt
python -m src.main --stage produce_script

# 2. Sau khi user upload scene_01.mp4 qua bot (webhook đã lưu blob), ráp:
python -m src.main --stage assemble --episode-id ep_20250115_0100 --version 1
```

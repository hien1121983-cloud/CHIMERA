# CHIMERA V4.0 — Refactor Patch (Master Refactor Protocol)

Gói này CHỈ chứa các file đã sửa hoặc bổ sung mới, áp đè trực tiếp lên cây
mã nguồn `chimera/` hiện hữu (cùng cấu trúc thư mục).

## Danh sách file thay đổi

### Mã nguồn Python
- `src/main.py` — 2-stage orchestrator anti-deadlock (skeleton-only ở Stage A).
- `src/config.py` — thêm `edge_voice_narrator`, `max_character_dialogue_chars`.
- `src/processing/sandbox_loop.py` — Aggregator T1 (gom 7 khối) + sinh SKELETON.
- `src/processing/monte_carlo.py` — nhận `archetypes` + `forced_injection`.
- `src/engine/anh_t.py` — vet trên skeleton + ép đột biến (hidden_items + dice).
- `src/engine/llm_reader.py` — schema mới: `speaker_role`, `cinematic_video_prompt`;
  enforce ngân sách 1000 ký tự cho dialogue speaker_role=character.
- `src/engine/renderer.py` — TTS HYBRID theo `speaker_role`
  (narrator → edge-tts, character → ElevenLabs Rotator → fallback edge-tts).
- `src/engine/ffmpeg_builder.py` — SPLIT RENDERING: bỏ Scene 1 + bỏ glitch
  transition, xuất `system_video_full.mp4` HOẶC `system_video_part1/2.mp4`.
- `src/engine/alchemist.py` — thêm `build_skeleton_brief` + nhận 7-block input.
- `src/delivery/telegram_bot.py` — thêm `send_skeleton_for_approval`,
  `deliver_videos` xử lý list[Path] (part1/part2).

### Dữ liệu seed cho Aggregator T1
- `data/archetypes.json` — 27 archetype khung 15-scene.
- `data/characters/blueprints.json` — 9 hồ sơ nhân vật.
- `data/lore/mapping_dictionary.json` — copy từ `data/mapping_dictionary.json`
  (giữ file cũ làm fallback).
- `data/secrets/hidden_items.json` — kho cứng "vật phẩm/sự kiện ẩn".
- `data/destiny_dice.json` — xúc xắc định mệnh.

## Cách áp dụng
Giải nén ZIP và copy đè (`cp -r chimera/* /đường/dẫn/repo/chimera/`).
**Không xoá** file gốc nào ngoài danh sách trên — toàn bộ logic cốt lõi và
chuẩn UI 15-scene được giữ nguyên.

## Lưu ý vận hành
- 2 khối động (`news`, `memes`) cần helper `fetch_recent_news`,
  `fetch_recent_memes` trong `src/storage/mongo.py` (đọc collection
  `news` / `memes` của `MONGODB_URL_NO3`). Nếu chưa có, Aggregator T1 vẫn
  chạy được — chỉ log "không sẵn sàng" và truyền list rỗng cho LLM.
- Không cần file `assets/glitch_transition.mp4` nữa.

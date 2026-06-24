# Project Chimera

Pipeline tự động sinh truyện tranh có thoại (MP4 dọc 1080×1920), chạy 0đ trên GitHub Actions.

## Điểm mới (bản này)

- **7 Gemini API key xoay tour**: mỗi phân cảnh do 1 key đảm nhận (round-robin theo `scene index`).
  Trước mỗi run, từng key phải "say hi" thành công mới được vào pool. Key chết tự loại.
  Biến môi trường: `GEMINI_API_KEY1` … `GEMINI_API_KEY7`, model mặc định `gemini-2.5-flash`.
- **3 cụm MongoDB tách biệt**:
  - `MONGODB_URL_NO1` — **inputs**: entities + keywords + contexts + `current_state` (vĩnh viễn).
  - `MONGODB_URL_NO2` — **scripts**: kịch bản trung gian truyền cho renderer (`purgatory` TTL 3 ngày, `partial_output`, `scene_jobs`).
  - `MONGODB_URL_NO3` — **history**: 50 tập canon FIFO cho "anh T" đối chiếu chống trùng.
- **FFmpeg**: sau khi sinh ảnh + thoại, ghép thành **MP4 1080×1920** (subtitle hardsub từ SRT, BGM ducking 25%) và **gửi MP4 qua Telegram** thay cho ZIP. File > 50 MB tự cắt part.

## Kiến trúc rút gọn

```
ingestion (Mongo NO1)
   → sandbox + Monte Carlo + drama eval → Top 3
   → Alchemist prompt
   → LLM Reader:
        stage1 outline (1 key)
        stage2 từng scene (key #1..#7 xoay tour)
   → anh T (đối chiếu Mongo NO3, TF-IDF cosine)
   → Renderer (Pollinations → HF, Edge-TTS → gTTS → ElevenLabs)
   → Timeline Mapper (SRT + timeline_durations.json)
   → FFmpeg → final_video.mp4
   → Telegram sendVideo + Inline Keyboard
   → purgatory (Mongo NO2) chờ user chốt
   → webhook commit canon → Mongo NO3 (FIFO 50)
```

## Cài đặt nhanh

```bash
git init && git add . && git commit -m "init chimera"
# push lên GitHub, sau đó vào Settings → Secrets and variables → Actions, thêm:
#   GEMINI_API_KEY1..7
#   MONGODB_URL_NO1..3
#   TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_WEBHOOK_SECRET
#   (tuỳ chọn) GROQ_API_KEY, HF_TOKEN, ELEVENLABS_API_KEY
```

GitHub Action `daily_production.yml` chạy 08:00 GMT+7. Để chạy thử:
`Actions → Daily Episode Production → Run workflow` (đặt `DEBUG_MODE=true` để chỉ sinh 3 scene).

## Local

```bash
sudo apt-get install -y ffmpeg
python -m pip install -r requirements.txt
cp .env.example .env   # điền key
python -m src.main
```

## Cấu trúc

- `src/engine/gemini_pool.py` — say-hi + xoay tour 7 key.
- `src/engine/llm_reader.py` — outline + 1 scene / 1 key.
- `src/engine/ffmpeg_builder.py` — ghép MP4.
- `src/storage/mongo.py` — 3 cụm (`db_inputs`, `db_scripts`, `db_history`).
- `src/delivery/telegram_bot.py` — `deliver_videos()` thay cho ZIP.
- `src/delivery/webhook.py` — chốt canon → Mongo NO3 → trigger workflow phụ.

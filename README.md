# CHIMERA V5.0.1

Pipeline san xuat video tu dong gom 3 giai doan ("3 Ban").

## Kien truc tong the

```
[Ban 1] Python thuan
  T0-T0h thu thap -> T0i mo phong the gioi
        |
        v
  Master_Payload.json
        |
[Ban 2] Gemini + Auditor + Telegram
  A1 sinh 3 drafts -> T3 Auditor (Cosine Similarity)
  -> Showrunner duyet (Telegram) -> cap nhat World State
        |
        v
  Master_Script.json
        |
[Ban 3] Groq + ElevenLabs/Edge-TTS + Pollinations + FFmpeg
  A2 boc tach -> T5 sinh media -> merge audio
  -> T6 render FFmpeg -> T7 giao hang Telegram + don rac
        |
        v
  MP4 (<50MB) gui ve Telegram Showrunner
```

## Cau truc thu muc

- `config/` - Pydantic Settings + cac file JSON cau hinh.
- `core/` - Credential pool, health check, DB client (3 cum MongoDB + SQLite), backup GCS, helpers, logger.
- `fetchers/` - Cac tram thu thap T0 -> T0h.
- `simulator/` - T0i World State Simulator + cac engine + Pydantic models.
- `creative/` - A1 Alchemist (Gemini), prompt, schema, voice mapping.
- `audit/` - T3 Auditor (sentence-transformers) + vector cache.
- `telegram_bot/` - Showrunner bot (FastAPI webhook + asyncio.Event).
- `post_approval/` - Cap nhat World State sau khi duyet.
- `dispatcher/` - A2 Dispatcher (Groq) + visual lock + prompt translator.
- `media_factory/` - T5 Postman, TTS, image gen, audio merge/meter, resource lock.
- `render_engine/` - T6 FFmpeg, builder, subtitle, part splitter.
- `delivery/` - T7 Courier, garbage collector, report generator.

## Cai dat

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # dien API keys + MongoDB URI
```

Yeu cau he thong: `ffmpeg` va `ffprobe` co tren PATH.

## Chay

```bash
python main_pipeline.py            # Giai doan 1 -> cache/master_payload_latest.json
python main_creative_pipeline.py   # Giai doan 2 -> cache/master_script_latest.json (cho Showrunner duyet)
python main_media_pipeline.py      # Giai doan 3 -> MP4 gui Telegram
```

## Nguyen tac bat bien

- Secret-free: chi doc key qua `core/credential_manager`.
- Configuration-driven: moi nguong doc tu `config/settings.py` / `.env`.
- Fail-safe: moi tram T0x co try/except + fallback SQLite doc lap.
- Retry huu han: moi loi goi LLM gioi han bang `active_count + 1`.
- CPU protection: FFmpeg luon `-threads 2 -crf 28 -preset veryfast`.
- Garbage collection bat buoc sau khi giao hang.

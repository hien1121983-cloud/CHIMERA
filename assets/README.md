# `assets/` — Static media bundled vào source

## `glitch_transition.mp4` (BẮT BUỘC)

Một file video **tĩnh** dài 1.0 – 1.5 giây, 1080×1920 (9:16), 30fps,
H.264/AAC, dùng làm hiệu ứng **Chrono-Glitch Transition** khi kịch bản có
phân cảnh đánh dấu `is_glitch: true` (ví dụ Scene 8 trong tập 15 phân cảnh).

`src/engine/ffmpeg_builder.py` sẽ tự nhận diện flag này và `concat` cứng
file vào giữa luồng video — **không gọi API**, **không sinh prompt**.

Nếu file không tồn tại, transition sẽ bị bỏ qua (cảnh báo trong log) và
phần còn lại của episode vẫn ráp bình thường.

### Yêu cầu kỹ thuật
| Field | Value |
|---|---|
| Container | `.mp4` (MOV faststart) |
| Codec video | `libx264`, `pix_fmt=yuv420p` |
| Codec audio | `aac` (có thể là silent track) |
| Resolution | 1080 × 1920 |
| FPS | 30 |
| Duration | 1.0–1.5 s |

### Tạo nhanh từ stock
```
ffmpeg -i glitch_source.mov \
  -vf "scale=1080:1920:force_original_aspect_ratio=decrease,\
       pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30" \
  -t 1.2 -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p \
  -c:a aac -b:a 128k assets/glitch_transition.mp4
```

# Transition Clips

Đặt 3 clip ngắn vào thư mục này (1080×1920, MP4, không tiếng):

| File | Độ dài | Tình huống |
|---|---|---|
| `transition_standard.mp4` | 0.5s | Mặc định giữa các scene |
| `transition_glitch.mp4`   | 1.0s | Khi thế giới đang bị "GlitchCurse" (arc 3, Scene 7→9) |
| `transition_dramatic.mp4` | 0.8s | `sfx_tag ∈ {twist, dramatic, betrayal, revenge}` |

> Nếu thiếu clip, `timeline_mapper.select_transition` sẽ trả về `None` và
> FFmpeg builder bỏ qua transition (giữ hành vi cũ).

## Tạo nhanh bằng FFmpeg

```bash
ffmpeg -f lavfi -i color=black:s=1080x1920:d=0.5 -vf "fade=t=in:st=0:d=0.25" \
  -c:v libx264 -pix_fmt yuv420p transition_standard.mp4
```

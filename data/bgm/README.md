# BGM Pool

Đặt các file `.mp3` royalty-free vào thư mục này, sau đó liệt kê tên file
trong `bgm_index.json` theo nhóm cảm xúc tương ứng:

```json
{
  "tense":    ["thriller_loop.mp3"],
  "dramatic": ["string_swell.mp3"],
  "sad":      ["piano_rain.mp3"],
  "twist":    ["dark_reveal.mp3"],
  "calm":     ["ambient_soft.mp3"],
  "neutral":  ["default_bed.mp3"]
}
```

Nguồn gợi ý: Pixabay Music, Freesound.org, YouTube Audio Library.
LLM (Stage 1) trả `emotion_tag` quyết định Renderer chọn từ nhóm nào.

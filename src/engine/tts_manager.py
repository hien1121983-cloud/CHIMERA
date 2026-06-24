import os
import requests
import uuid

class TTSHybridManager:
    def __init__(self):
        # Nạp 6 Key ElevenLabs từ biến môi trường Github Secrets
        self.eleven_keys = [
            os.getenv(f"ELEVENLABS_KEY{i}") for i in range(1, 7)
            if os.getenv(f"ELEVENLABS_KEY{i}")
        ]
        self.current_key_idx = 0
        
        # ID giọng đọc ElevenLabs (Thay bằng ID giọng bạn muốn)
        self.voice_id = "21m00Tcm4TlvDq8ikWAM" 

    def generate_audio_for_scene(self, scene_id: int, narrator_text: str, character_text: str, output_path: str):
        """
        Tạo âm thanh kết hợp: Edge-TTS (Narrator) đọc bối cảnh trước, 
        ElevenLabs (Character) đọc thoại ngay sau đó trong cùng 1 scene.
        """
        # Tạo tên file tạm thời ngẫu nhiên để tránh xung đột luồng
        uid = uuid.uuid4().hex[:6]
        temp_narrator = f"temp_narrator_{scene_id}_{uid}.mp3"
        temp_character = f"temp_character_{scene_id}_{uid}.mp3"
        
        has_narrator = bool(narrator_text and str(narrator_text).strip())
        has_character = bool(character_text and str(character_text).strip())
        
        # 1. Gen Narrator bằng Edge-TTS (Miễn phí 0đ)
        if has_narrator:
            print(f"🤖 [Scene {scene_id}] Đang tạo Edge-TTS (Dẫn truyện)...")
            self._run_edge_tts(narrator_text, temp_narrator)
            
        # 2. Gen Character bằng ElevenLabs (Xoay vòng Key)
        if has_character:
            print(f"💎 [Scene {scene_id}] Đang tạo ElevenLabs (Thoại nhân vật)...")
            success = False
            if self.eleven_keys:
                success = self._run_elevenlabs_rotator(character_text, temp_character)
            
            # Fallback nếu cháy sạch 6 Key ElevenLabs
            if not success:
                print(f"⚠️ ElevenLabs cạn kiệt! Fallback thoại nhân vật Scene {scene_id} về Edge-TTS.")
                self._run_edge_tts(character_text, temp_character)
                
        # 3. Ghép nối file (Concat)
        if has_narrator and has_character:
            self._concat_audios(temp_narrator, temp_character, output_path)
        elif has_narrator:
            os.rename(temp_narrator, output_path)
        elif has_character:
            os.rename(temp_character, output_path)
        else:
            # Fallback nếu LLM trả về rỗng cả 2 (Tạo 1s âm thanh im lặng)
            os.system(f'ffmpeg -f lavfi -i anullsrc=r=44100:cl=mono -t 1 -q:a 9 -acodec libmp3lame "{output_path}" -loglevel error -y')

        # 4. Dọn rác file tạm
        if os.path.exists(temp_narrator): os.remove(temp_narrator)
        if os.path.exists(temp_character): os.remove(temp_character)
        
        return output_path

    def _run_elevenlabs_rotator(self, text: str, output_path: str) -> bool:
        """Xoay tua 6 Key ElevenLabs. Trượt sang Key mới nếu dính lỗi 401."""
        for _ in range(len(self.eleven_keys)):
            current_key = self.eleven_keys[self.current_key_idx]
            headers = {"xi-api-key": current_key, "Content-Type": "application/json"}
            data = {"text": text, "model_id": "eleven_multilingual_v2"}
            
            try:
                res = requests.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}", 
                    json=data, headers=headers
                )
                if res.status_code == 200:
                    with open(output_path, "wb") as f:
                        f.write(res.content)
                    return True
                elif res.status_code == 401:
                    print(f"🔄 Key ElevenLabs {self.current_key_idx + 1} cạn Credit. Chuyển Key...")
                    self.current_key_idx = (self.current_key_idx + 1) % len(self.eleven_keys)
                else:
                    print(f"❌ Lỗi API ElevenLabs: {res.status_code}")
                    break
            except Exception as e:
                print(f"❌ Lỗi mạng ElevenLabs: {e}")
                break
        return False

    def _run_edge_tts(self, text: str, output_path: str):
        """Chạy Edge-TTS hệ thống (Dùng subprocess hoặc os.system)"""
        # Sửa giọng vi-VN-HoaiMyNeural hoặc vi-VN-NamMinhNeural tuỳ ý
        safe_text = text.replace('"', '\\"') # Chống lỗi dấu nháy trong command line
        os.system(f'edge-tts --text "{safe_text}" --voice "vi-VN-HoaiMyNeural" --write-media "{output_path}"')

    def _concat_audios(self, file1: str, file2: str, output_path: str):
        """
        Dùng FFmpeg ép 2 file đồng bộ tần số lấy mẫu (44100Hz) và ghép nối liền mạch.
        Lệnh cực kỳ an toàn, chống lỗi mismatch sample rate giữa Edge và ElevenLabs.
        """
        cmd = (
            f'ffmpeg -y -i "{file1}" -i "{file2}" '
            f'-filter_complex "[0:a]aresample=44100,pan=mono|c0=c0[a0];'
            f'[1:a]aresample=44100,pan=mono|c0=c0[a1];[a0][a1]concat=n=2:v=0:a=1[out]" '
            f'-map "[out]" "{output_path}" -loglevel error'
        )
        os.system(cmd)


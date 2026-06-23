import os
import json
import random
import uuid

# --- CẤU HÌNH ĐƯỜNG DẪN ---
# Thư mục chứa 9 file JSON blueprint mà ta vừa tạo
BLUEPRINT_DIR = "data/world/blueprints"

# --- KHO TÊN MỒI (Có thể mở rộng sau này) ---
VIETNAMESE_NAMES = [
    "Nam 'Sẹo'", "Hải 'Dớ'", "Lan 'Bến Xe'", "Bà Lan", 
    "Chủ tịch Khang", "Linh 'Trà Xanh'", "Thành 'Phông Bạt'", 
    "Huy 'Crypto'", "Cô giáo Thủy", "Đại ca Long"
]

def roll_random_blueprint(directory=BLUEPRINT_DIR):
    """
    Hàm tung xúc xắc:
    1. Quét thư mục lấy danh sách 9 blueprint.
    2. Bốc ngẫu nhiên 1 bản.
    3. Sinh ID và Tên ngẫu nhiên để thay thế placeholder.
    4. Trả về một object Dictionary (JSON đã parse) cho hệ thống cha.
    """
    
    # Kiểm tra thư mục có tồn tại không
    if not os.path.exists(directory):
        # Trả về lỗi có cấu trúc để hệ thống cha dễ bắt lỗi
        return {"error": f"Lỗi: Không tìm thấy thư mục {directory}. Hãy chắc chắn bạn đã tạo 9 file json."}

    # Lấy danh sách các file .json
    json_files = [f for f in os.listdir(directory) if f.endswith('.json')]
    
    if not json_files:
        return {"error": "Lỗi: Thư mục blueprint trống rỗng!"}

    # 1. Tung xúc xắc chọn 1 file ngẫu nhiên
    chosen_file = random.choice(json_files)
    file_path = os.path.join(directory, chosen_file)

    # 2. Đọc file JSON
    with open(file_path, 'r', encoding='utf-8') as f:
        try:
            blueprint_data = json.load(f)
        except json.JSONDecodeError:
            return {"error": f"Lỗi: File {chosen_file} bị sai định dạng JSON."}

    # 3. "Thổi hồn" vào khuôn đúc (Thay thế các trường chờ)
    # Sinh một mã UUID ngắn (8 ký tự) để làm ID định danh
    new_id = f"entity_{str(uuid.uuid4())[:8]}"
    new_name = random.choice(VIETNAMESE_NAMES)

    blueprint_data["entity_id"] = new_id
    blueprint_data["full_name"] = new_name

    return blueprint_data

# ==========================================
# KHU VỰC TEST ĐỘC LẬP (Chỉ chạy khi bạn chạy trực tiếp file này)
# ==========================================
if __name__ == "__main__":
    print("🎲 Đang tung xúc xắc bốc khuôn đúc nhân vật...")
    
    # Giả lập hệ thống cha đang gọi hàm
    character = roll_random_blueprint()
    
    if "error" in character:
        print(character["error"])
    else:
        print(f"✅ Đã bốc trúng Hệ tư tưởng: {character.get('blueprint_origin')}")
        print(f"👤 Tên nhân vật: {character.get('full_name')}")
        print(f"🔑 Mã định danh: {character.get('entity_id')}")
        print("-" * 40)
        print("Trích xuất triết lý nhân vật:")
        print(character.get("core_data", {}).get("_blueprint_philosophy"))


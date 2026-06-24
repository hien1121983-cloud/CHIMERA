import json
import random

def gather_production_inputs(db_client):
    """Gom 7 nguồn dữ liệu (5 tĩnh, 2 động)"""
    with open("data/world/archetypes.json", "r", encoding="utf-8") as f:
        archetypes = json.load(f)
    with open("data/world/characters/blueprints.json", "r", encoding="utf-8") as f:
        characters = json.load(f)
    with open("data/world/lore/mapping_dictionary.json", "r", encoding="utf-8") as f:
        lore = json.load(f)
    with open("data/world/secrets/hidden_items.json", "r", encoding="utf-8") as f:
        secrets = json.load(f)
    with open("data/world/destiny_dice.json", "r", encoding="utf-8") as f:
        dice = json.load(f)
        
    # Lấy data động cào từ 6h sáng
    news = db_client.db.daily_news.find_one(sort=[("created_at", -1)])
    trends = db_client.db.daily_trends.find_one(sort=[("created_at", -1)])
    
    return {"archetypes": archetypes, "characters": characters, "lore": lore, 
            "secrets": secrets, "dice": dice, "news": news, "trends": trends}

def generate_and_filter_skeletons(llm_client, db_client, inputs):
    """Anh T: Lọc trùng lặp và Ép đột biến"""
    history_50 = get_last_50_episodes(db_client) # Lấy lịch sử 50 tập
    retry_count = 0
    max_retries = 3
    
    while retry_count <= max_retries:
        # Monte Carlo tự sinh và lọc lấy Top 3
        top_3_skeletons = llm_client.run_monte_carlo_skeletons(inputs, count=3)
        
        # Anh T kiểm tra TF-IDF (Giả mã hàm is_duplicate)
        is_dup = check_tfidf_duplicate(top_3_skeletons, history_50)
        
        if not is_dup:
            return top_3_skeletons # Pass, trả về 3 khung sạch
            
        retry_count += 1
        print(f"🔄 Anh T: Phát hiện trùng lặp lần {retry_count}. Yêu cầu sinh lại!")
        
        # Nếu fail đến lần 3, ép đột biến bằng Destiny Dice
        if retry_count == max_retries:
            print("⚡ Anh T: ÉP ĐỘT BIẾN! Nhồi Destiny Dice cực đoan vào Prompt.")
            inputs["forced_mutation"] = random.choice(inputs["dice"]["extreme_events"])

    return top_3_skeletons # Trả về kết quả cuối cùng sau khi ép

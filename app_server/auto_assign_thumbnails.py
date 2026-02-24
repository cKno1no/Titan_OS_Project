import os
import json
import pyodbc
import random
import time
import re
import google.generativeai as genai
from dotenv import load_dotenv

# --- CẤU HÌNH ---
load_dotenv()
API_KEY = "AIzaSyBLi_xp5bSdRXC8jpveV_mgumrushjZqBA" # Thay bằng Key thật của bạn

db_server = os.getenv('DB_SERVER')
db_name = os.getenv('DB_NAME')
db_uid = os.getenv('DB_UID')
db_pwd = os.getenv('DB_PWD')

CONN_STR = (
    r'DRIVER={ODBC Driver 17 for SQL Server};'
    f'SERVER={db_server};DATABASE={db_name};UID={db_uid};PWD={db_pwd}'
)

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# THƯ MỤC GỐC CHỨA 79 FILE 3D CỦA BẠN
IMG_BASE_DIR = "static/img/3d_assets"

def get_db_connection():
    return pyodbc.connect(CONN_STR)

def scan_local_images():
    """
    Quét thư mục chứa ảnh 3D và trả về danh sách có cấu trúc.
    Ví dụ: {'culture': ['books.png', 'sparkles.png'], 'factory': ['pump.png', 'bearing.png']}
    """
    inventory = {}
    if not os.path.exists(IMG_BASE_DIR):
        print(f"❌ Lỗi: Thư mục {IMG_BASE_DIR} không tồn tại.")
        return inventory
        
    for folder_name in os.listdir(IMG_BASE_DIR):
        folder_path = os.path.join(IMG_BASE_DIR, folder_name)
        if os.path.isdir(folder_path):
            files = [f for f in os.listdir(folder_path) if f.endswith(('.png', '.jpg', '.jpeg', '.webp'))]
            if files:
                inventory[folder_name] = files
                
    return inventory

def ai_assign_images(courses_batch, inventory):
    """
    Nhờ AI sắm vai Giám đốc Mỹ thuật để chọn ảnh từ kho 'inventory' cho các Khóa học.
    """
    prompt = f"""
    Bạn là một Giám đốc Đào tạo và Chuyên gia Thiết kế UI/UX.
    Tôi có một danh sách các khóa học nội bộ và một thư viện hình ảnh minh họa 3D (được chia theo chủ đề thư mục).
    
    NHIỆM VỤ CỦA BẠN:
    Hãy gán 1 hình ảnh 3D phù hợp nhất từ Thư viện Hình ảnh cho mỗi Khóa học. 
    Lựa chọn sao cho Tên thư mục hoặc Tên file ảnh có ý nghĩa tương đồng nhất với Tiêu đề (Title) và Phân loại (Category) của khóa học.

    [THƯ VIỆN HÌNH ẢNH (INVENTORY CÓ SẴN)]:
    {json.dumps(inventory, ensure_ascii=False)}

    [DANH SÁCH KHÓA HỌC CẦN GÁN ẢNH]:
    {json.dumps(courses_batch, ensure_ascii=False)}

    OUTPUT JSON YÊU CẦU:
    Trả về một mảng các đối tượng JSON. TUYỆT ĐỐI không sử dụng tên thư mục hay file ảnh không tồn tại trong INVENTORY ở trên.
    
    [
        {{
            "id": 1,
            "folder": "tên_thư_mục_được_chọn",
            "file": "tên_file_ảnh_được_chọn"
        }}
    ]
    """
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                max_output_tokens=8192
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"   ❌ Lỗi AI khi gán ảnh: {e}")
        return []

def get_random_fallback(inventory):
    """Dự phòng: Nếu AI lỗi, chọn bừa 1 ảnh hợp lệ trong kho"""
    if not inventory:
        return "/static/img/default_thumbnail.png"
    folder = random.choice(list(inventory.keys()))
    file = random.choice(inventory[folder])
    return f"/{IMG_BASE_DIR}/{folder}/{file}"

def main():
    print("🖼️ BƯỚC 1: Quét kho ảnh 3D local...")
    inventory = scan_local_images()
    total_images = sum(len(files) for files in inventory.values())
    print(f"-> Tìm thấy {total_images} ảnh trong {len(inventory)} thư mục chủ đề.")
    
    if total_images == 0:
        print("Vui lòng kiểm tra lại đường dẫn thư mục ảnh 3D.")
        return

    print("\n📚 BƯỚC 2: Đọc danh sách Khóa học từ Database...")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT CourseID, Title, Category, SubCategory FROM TRAINING_COURSES")
    rows = cursor.fetchall()
    
    if not rows:
        print("Không có khóa học nào để gán ảnh.")
        return
        
    courses_for_ai = []
    for r in rows:
        courses_for_ai.append({
            "id": r.CourseID,
            "title": r.Title,
            "category": r.Category,
            "sub_category": r.SubCategory
        })
        
    print(f"-> Lấy thành công {len(courses_for_ai)} khóa học.")

    # --- CHIA MẺ CHO AI (30 khóa học/mẻ) ---
    BATCH_SIZE = 30
    batches = [courses_for_ai[i:i + BATCH_SIZE] for i in range(0, len(courses_for_ai), BATCH_SIZE)]
    
    ai_map = {}
    print("\n🧠 BƯỚC 3: AI đang phân tích ngữ nghĩa và lựa chọn ảnh (Chờ chút nhé)...")
    
    for idx, batch in enumerate(batches):
        print(f"   ⏳ Đang phân tích mẻ {idx+1}/{len(batches)}...")
        results = ai_assign_images(batch, inventory)
        if results:
            for item in results:
                # Tạo đường dẫn tuyệt đối web (VD: /static/img/3d_assets/culture/books.png)
                ai_map[item['id']] = f"/{IMG_BASE_DIR}/{item['folder']}/{item['file']}"
        time.sleep(2) # Nghỉ 2s tránh Rate Limit

    print("\n⚙️ BƯỚC 4: Đối chiếu chéo và cập nhật Database...")
    count_success = 0
    count_fallback = 0
    
    for c in courses_for_ai:
        c_id = c['id']
        final_path = ""
        
        if c_id in ai_map:
            # BƯỚC KIỂM TRA QUAN TRỌNG: Check xem AI có bịa ra tên file không
            # Lấy đường dẫn vật lý để kiểm tra (bỏ dấu '/' ở đầu)
            real_check_path = ai_map[c_id].lstrip('/')
            if os.path.exists(real_check_path):
                final_path = ai_map[c_id]
                count_success += 1
            else:
                final_path = get_random_fallback(inventory)
                count_fallback += 1
        else:
            final_path = get_random_fallback(inventory)
            count_fallback += 1
            
        cursor.execute("UPDATE TRAINING_COURSES SET ThumbnailUrl = ? WHERE CourseID = ?", (final_path, c_id))
        
    conn.commit()
    conn.close()
    
    print(f"\n🎉 HOÀN TẤT! Đã gán ảnh thông minh cho {count_success} khóa học.")
    if count_fallback > 0:
        print(f"   (Dùng ảnh ngẫu nhiên {count_fallback} lần do AI sót hoặc file không tồn tại).")

if __name__ == "__main__":
    main()
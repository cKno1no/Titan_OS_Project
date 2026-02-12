import os
import time
import json
import pyodbc
import re
import difflib
import google.generativeai as genai
from dotenv import load_dotenv

# --- CẤU HÌNH ---
load_dotenv()
API_KEY = 

db_server = os.getenv('DB_SERVER')
db_name = os.getenv('DB_NAME')
db_uid = os.getenv('DB_UID')
db_pwd = os.getenv('DB_PWD')

CONN_STR = (
    r'DRIVER={ODBC Driver 17 for SQL Server};'
    f'SERVER={db_server};'
    f'DATABASE={db_name};'
    f'UID={db_uid};PWD={db_pwd}'
)

# Thư mục chứa PDF
LIBRARY_DIR = r'static/uploads/library' 

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

def get_db_connection():
    return pyodbc.connect(CONN_STR)

def clean_json_string(text):
    """Hàm làm sạch chuỗi JSON từ AI"""
    text = re.sub(r"```json|```", "", text).strip()
    # Tìm điểm bắt đầu [ và kết thúc ]
    start = text.find('[')
    end = text.rfind(']')
    if start != -1 and end != -1:
        text = text[start:end+1]
    return text

# 1. HÀM LỌC TRÙNG (GIỮ NGUYÊN)
def deduplicate_materials(materials):
    print(f"🧹 Đang lọc trùng lặp cho {len(materials)} tài liệu...")
    grouped = {}
    for m in materials:
        clean_name = re.sub(r'[\(\[\_\-\s]?(v\d+|ver\d+|final|copy|new|bản mới)[\)\]]?', '', m['title'], flags=re.IGNORECASE).strip().lower()
        found_key = None
        for key in grouped:
            if difflib.SequenceMatcher(None, clean_name, key).ratio() > 0.9:
                found_key = key
                break
        if not found_key:
            grouped[clean_name] = []
            found_key = clean_name
        grouped[found_key].append(m)

    final_list = []
    for key, group in grouped.items():
        best_candidate = sorted(group, key=lambda x: x['id'])[-1]
        final_list.append(best_candidate)
        
    print(f"✨ Sau khi lọc: Còn {len(final_list)} tài liệu.")
    return final_list

# ==============================================================================
# PHASE 2: AI ARCHITECT (V5 - CATEGORY BASED BLUEPRINT)
# ==============================================================================

def run_phase_2_v5(conn):
    print("\n🧠 --- BẮT ĐẦU PHASE 2 (V5): TRƯỞNG KHOA THIẾT KẾ ---")
    cursor = conn.cursor()
    
    # A. LẤY DỮ LIỆU
    cursor.execute("SELECT MaterialID, FileName, Summary FROM TRAINING_MATERIALS WHERE CourseID IS NULL")
    raw_materials = cursor.fetchall()
    if not raw_materials:
        print("Không có tài liệu nào cần xử lý.")
        return

    # Parse & Deduplicate
    materials_list = []
    for m in raw_materials:
        try:
            meta = json.loads(m.Summary)
            cat = meta.get('category', 'Khác')
            # Chuẩn hóa Category (AI Phase 1 có thể trả về nhiều kiểu)
            if 'kỹ thuật' in cat.lower(): cat = 'Kỹ thuật'
            elif 'kinh doanh' in cat.lower() or 'bán hàng' in cat.lower(): cat = 'Kinh doanh'
            elif 'kỹ năng' in cat.lower(): cat = 'Kỹ năng'
            
            materials_list.append({
                "id": m.MaterialID,
                "title": meta.get('title', m.FileName),
                "cat": cat
            })
        except:
            materials_list.append({"id": m.MaterialID, "title": m.FileName, "cat": "Khác"})

    clean_materials = deduplicate_materials(materials_list)

    # B. GOM THEO CATEGORY
    materials_by_cat = {}
    for m in clean_materials:
        if m['cat'] not in materials_by_cat: materials_by_cat[m['cat']] = []
        materials_by_cat[m['cat']].append(m)

    created_courses = [] # Danh sách khóa học đã tạo để dùng cho bước Gán

    # ---------------------------------------------------------
    # BƯỚC 1: TẠO KHÓA HỌC THEO TỪNG NHÓM (Chia nhỏ vấn đề)
    # ---------------------------------------------------------
    print("\n🏗️ BƯỚC 1: THIẾT KẾ KHUNG CHƯƠNG TRÌNH...")
    
    for cat_name, items in materials_by_cat.items():
        if not items: continue
        print(f"   -> Đang thiết kế cho nhóm: {cat_name} ({len(items)} bài)...")
        
        # Gửi danh sách tên bài học của nhóm này
        item_names = [m['title'] for m in items]
        
        prompt = f"""
        Bạn là Trưởng khoa Đào tạo chuyên về "{cat_name}".
        Dưới đây là danh sách {len(items)} tài liệu của khoa bạn:
        {json.dumps(item_names, ensure_ascii=False)}
        
        NHIỆM VỤ: 
        Thiết kế các KHÓA HỌC (Courses) để gom nhóm các tài liệu này một cách logic.
        - Mỗi khóa học nên chứa từ 3-10 bài.
        - Đặt tên khóa học chuyên nghiệp.
        
        OUTPUT JSON:
        [
            {{ "title": "Tên khóa", "desc": "Mô tả ngắn" }},
            ...
        ]
        """
        
        # Retry logic
        for attempt in range(3):
            try:
                response = model.generate_content(prompt)
                json_str = clean_json_string(response.text)
                courses = json.loads(json_str)
                
                # Insert vào DB
                for c in courses:
                    # Chọn ảnh
                    thumb = '/static/img/course_softskill.jpg'
                    if 'kỹ thuật' in cat_name.lower(): thumb = '/static/img/course_tech.jpg'
                    elif 'kinh doanh' in cat_name.lower(): thumb = '/static/img/course_sales.jpg'
                    
                    sql = "INSERT INTO TRAINING_COURSES (Title, Description, Category, ThumbnailUrl, IsMandatory, CreatedDate, XP_Reward) OUTPUT INSERTED.CourseID VALUES (?, ?, ?, ?, 0, GETDATE(), 300)"
                    cursor.execute(sql, (c['title'], c['desc'], cat_name, thumb))
                    new_id = cursor.fetchone()[0]
                    
                    created_courses.append({"id": new_id, "title": c['title']})
                    print(f"      + Đã tạo: {c['title']}")
                
                conn.commit()
                break # Thành công thì thoát retry
                
            except Exception as e:
                print(f"      ⚠️ Lỗi AI (Lần {attempt+1}): {e}")
                time.sleep(3)

    # ---------------------------------------------------------
    # BƯỚC 2: GÁN TÀI LIỆU VÀO KHÓA (Gán theo Batch 30)
    # ---------------------------------------------------------
    print(f"\n📦 BƯỚC 2: XẾP LỚP CHO {len(clean_materials)} TÀI LIỆU...")
    
    # Chỉ gửi danh sách tên khóa học lên để AI chọn
    all_course_names = [c['title'] for c in created_courses]
    
    # Chia batch 30 để gán
    batch_size = 30
    batches = [clean_materials[i:i + batch_size] for i in range(0, len(clean_materials), batch_size)]
    
    for idx, batch in enumerate(batches):
        print(f"   -> Đang xếp lớp Batch {idx+1}/{len(batches)}...")
        
        assign_prompt = f"""
        Danh sách các Khóa học hiện có:
        {json.dumps(all_course_names, ensure_ascii=False)}
        
        Danh sách tài liệu cần xếp lớp:
        {json.dumps([{'id': m['id'], 'title': m['title']} for m in batch], ensure_ascii=False)}
        
        NHIỆM VỤ: Gán từng tài liệu vào 1 Khóa học phù hợp nhất.
        OUTPUT JSON: [ {{ "material_id": 123, "course_title": "Tên khóa" }}, ... ]
        """
        
        try:
            res = model.generate_content(assign_prompt)
            clean_json = clean_json_string(res.text)
            
            # Cố gắng đóng ngoặc nếu thiếu
            if not clean_json.endswith(']'): clean_json += ']'
                
            assignments = json.loads(clean_json)
            
            updates = 0
            for item in assignments:
                target_course_id = next((c['id'] for c in created_courses if c['title'] == item.get('course_title')), None)
                if target_course_id:
                    cursor.execute("UPDATE TRAINING_MATERIALS SET CourseID = ? WHERE MaterialID = ?", (target_course_id, item['material_id']))
                    updates += 1
            
            conn.commit()
            print(f"      ✅ Đã xếp {updates} tài liệu vào lớp.")
            time.sleep(2)
            
        except Exception as e:
            print(f"      ⚠️ Lỗi Batch {idx+1}: {e}")
            time.sleep(3)

    print("\n✅ HOÀN TẤT TOÀN BỘ QUY TRÌNH!")

def main():
    conn = get_db_connection()
    run_phase_2_v5(conn)
    conn.close()

if __name__ == "__main__":
    main()
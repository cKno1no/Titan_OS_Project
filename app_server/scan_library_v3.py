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
API_KEY = "AIzaSyCC_qWqKqqupwwUT7mOR_Z75M9eKv8Vil4" # Hoặc lấy từ env

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

# ==============================================================================
# HÀM PHỤ TRỢ: LỌC TRÙNG LẶP (PYTHON LOGIC)
# ==============================================================================
def deduplicate_materials(materials):
    """
    Lọc bỏ các file là version cũ của nhau dựa trên tên file và metadata.
    Giữ lại file mới nhất.
    """
    print(f"🧹 Đang lọc trùng lặp cho {len(materials)} tài liệu...")
    
    # Nhóm các file có tên tương tự nhau
    grouped = {}
    
    for m in materials:
        # Chuẩn hóa tên để so sánh (bỏ v1, v2, final, copy...)
        clean_name = re.sub(r'[\(\[\_\-\s]?(v\d+|ver\d+|final|copy|new|bản mới)[\)\]]?', '', m['title'], flags=re.IGNORECASE).strip().lower()
        
        # Tìm key tương tự trong grouped (Fuzzy match > 90%)
        found_key = None
        for key in grouped:
            ratio = difflib.SequenceMatcher(None, clean_name, key).ratio()
            if ratio > 0.9: # Giống nhau 90%
                found_key = key
                break
        
        if not found_key:
            grouped[clean_name] = []
            found_key = clean_name
            
        grouped[found_key].append(m)

    # Chọn đại diện cho từng nhóm
    final_list = []
    removed_ids = []
    
    for key, group in grouped.items():
        if len(group) == 1:
            final_list.append(group[0])
        else:
            # Nếu có nhiều version, ưu tiên cái nào có 'ver' cao nhất hoặc mới nhất
            # Logic đơn giản: Ưu tiên file có ID lớn hơn (thường là mới import sau)
            # Hoặc ưu tiên file có chữ 'final', 'v2' trong tên gốc
            
            best_candidate = group[-1] # Mặc định lấy cái cuối cùng (ID lớn nhất)
            
            # Thử tìm candidate tốt hơn dựa trên tên
            for item in group:
                if 'final' in item['title'].lower() or 'v2' in item['title'].lower() or '202' in item['title']:
                    best_candidate = item
            
            final_list.append(best_candidate)
            
            # Ghi nhận các ID bị loại bỏ
            for item in group:
                if item['id'] != best_candidate['id']:
                    removed_ids.append(item['id'])
                    print(f"   🗑️ Loại bỏ bản cũ: {item['title']} (Giữ lại: {best_candidate['title']})")

    print(f"✨ Sau khi lọc: Còn {len(final_list)} tài liệu (Đã loại {len(removed_ids)} bản trùng).")
    return final_list, removed_ids

# ==============================================================================
# PHASE 2: AI ARCHITECT (V3 - ROBUST)
# ==============================================================================

def run_phase_2_clustering_v3(conn):
    print("\n🧠 --- BẮT ĐẦU PHASE 2 (V3): AI ARCHITECT ---")
    cursor = conn.cursor()
    
    # 1. Lấy dữ liệu từ DB
    cursor.execute("SELECT MaterialID, FileName, Summary FROM TRAINING_MATERIALS WHERE CourseID IS NULL")
    raw_materials = cursor.fetchall()
    
    if not raw_materials:
        print("Không có tài liệu nào cần xử lý.")
        return

    # Parse Metadata
    materials_list = []
    for m in raw_materials:
        try:
            meta = json.loads(m.Summary)
            materials_list.append({
                "id": m.MaterialID,
                "title": meta.get('title', m.FileName),
                "category": meta.get('category', 'Khác'),
                "sub": meta.get('sub_category', ''),
                "ver": meta.get('version_indicator', '')
            })
        except:
            materials_list.append({"id": m.MaterialID, "title": m.FileName, "category": "Unknown"})

    # 2. Lọc trùng lặp bằng Python trước
    clean_materials, duplicate_ids = deduplicate_materials(materials_list)
    
    # Đánh dấu các file trùng lặp là "Archived" hoặc ẩn đi (Optional)
    # (Ở đây ta cứ để đó, chỉ không gán vào Course thôi)

    print(f"📦 Đang gửi {len(clean_materials)} bài học lên Gemini để xếp lớp...")

    # 3. Chia Batch nếu quá nhiều (Max 50 items/lần để AI không bị "ngáo")
    # Nhưng để AI gom nhóm tốt nhất, ta nên gửi theo Category
    # Group by Category
    materials_by_cat = {}
    for m in clean_materials:
        cat = m.get('category', 'Khác')
        if cat not in materials_by_cat: materials_by_cat[cat] = []
        materials_by_cat[cat].append(m)

    for cat_name, items in materials_by_cat.items():
        if not items: continue
        print(f"\n--- Đang xử lý nhóm: {cat_name} ({len(items)} bài) ---")
        
        prompt = f"""
        Bạn là Giám đốc Đào tạo. Hãy sắp xếp {len(items)} tài liệu thuộc nhóm "{cat_name}" sau đây thành các KHÓA HỌC (Course) hợp lý.
        
        DANH SÁCH TÀI LIỆU:
        {json.dumps(items, ensure_ascii=False)}
        
        YÊU CẦU:
        1. Gom các bài có liên quan chặt chẽ thành 1 khóa (VD: 3 bài về Bạc đạn -> Khóa "Chuyên gia Bạc đạn").
        2. Nếu bài nào quá lẻ loi, hãy gom vào khóa "Tổng hợp {cat_name}".
        3. Trả về JSON chuẩn xác.
        
        OUTPUT JSON:
        [
            {{
                "course_title": "Tên khóa học",
                "description": "Mô tả ngắn",
                "category": "{cat_name}",
                "thumbnail_url": "",
                "material_ids": [id1, id2...]
            }}
        ]
        """
        
        # Retry mechanism
        success = False
        for attempt in range(3):
            try:
                response = model.generate_content(prompt)
                json_str = re.sub(r"```json|```", "", response.text).strip()
                
                # Fix lỗi JSON thiếu ngoặc (thường gặp khi output dài)
                if not json_str.endswith(']'):
                    json_str += ']'
                
                courses_plan = json.loads(json_str)
                
                # Thực thi vào DB ngay
                for course in courses_plan:
                    # Tạo Course
                    sql_course = """
                        INSERT INTO TRAINING_COURSES (Title, Description, Category, ThumbnailUrl, IsMandatory, CreatedDate, XP_Reward)
                        OUTPUT INSERTED.CourseID
                        VALUES (?, ?, ?, ?, 0, GETDATE(), 300)
                    """
                    # Fallback thumbnail
                    thumb = course.get('thumbnail_url')
                    if not thumb:
                        if 'Kỹ thuật' in cat_name: thumb = '/static/img/course_tech.jpg'
                        elif 'Kinh doanh' in cat_name: thumb = '/static/img/course_sales.jpg'
                        else: thumb = '/static/img/course_softskill.jpg'

                    cursor.execute(sql_course, (course['course_title'], course['description'], course['category'], thumb))
                    new_course_id = cursor.fetchone()[0]
                    
                    # Gán Material
                    ids = course['material_ids']
                    if ids:
                        # Chỉ update những ID hợp lệ (có trong danh sách gửi đi)
                        valid_ids = [i for i in ids if isinstance(i, int)]
                        if valid_ids:
                            placeholders = ','.join('?' * len(valid_ids))
                            sql_update = f"UPDATE TRAINING_MATERIALS SET CourseID = ? WHERE MaterialID IN ({placeholders})"
                            cursor.execute(sql_update, [new_course_id] + valid_ids)
                    
                    print(f"   Created: {course['course_title']} (ID: {new_course_id}) - {len(ids)} bài")
                
                conn.commit()
                success = True
                break # Thành công thì thoát retry loop

            except Exception as e:
                print(f"   ⚠️ Lỗi Batch {cat_name} (Lần {attempt+1}): {e}")
                time.sleep(3)
        
        if not success:
            print(f"❌ BỎ QUA nhóm {cat_name} do lỗi AI liên tục.")

    print("\n✅ HOÀN TẤT TOÀN BỘ!")

def main():
    conn = get_db_connection()
    # Chạy Phase 2 (Vì Phase 1 sếp đã chạy xong rồi, bảng Material đã có Summary)
    run_phase_2_clustering_v3(conn)
    conn.close()

if __name__ == "__main__":
    main()
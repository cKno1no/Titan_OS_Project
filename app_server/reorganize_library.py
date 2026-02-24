import os
import json
import pyodbc
import re
import time
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

def get_db_connection():
    return pyodbc.connect(CONN_STR)

def fetch_all_processed_materials(cursor):
    cursor.execute("SELECT MaterialID, FileName, Summary FROM TRAINING_MATERIALS WHERE AI_Processed = 1")
    rows = cursor.fetchall()
    materials_for_ai = []
    summary_map = {} 
    for row in rows:
        mat_id = row.MaterialID
        desc_text = ""
        if row.Summary:
            try:
                parsed = json.loads(row.Summary)
                desc_text = parsed.get('summary', row.Summary)
            except:
                desc_text = row.Summary
        materials_for_ai.append({
            "id": mat_id,
            "filename": row.FileName,
            "description": desc_text[:300] 
        })
        summary_map[mat_id] = row.Summary
    return materials_for_ai, summary_map

def ai_process_batch(batch_materials, existing_courses_info):
    """Xử lý từng mẻ nhỏ, ép AI gom nhóm quyết liệt vào existing_courses"""
    
    prompt = f"""
    Bạn là Giám đốc Đào tạo STD&D. Dưới đây là MỘT PHẦN tài liệu đào tạo (Batch) cần phân loại.
    
    MỤC TIÊU TỐI THƯỢNG: GOM NHÓM QUYẾT LIỆT ĐỂ GIẢM SỐ LƯỢNG KHÓA HỌC (TỔNG TOÀN HỆ THỐNG KHÔNG QUÁ 70 KHÓA).
    Thay vì chia nhỏ lắt nhắt, hãy tạo ra các Khóa học mang tính TỔNG HỢP CAO (Ví dụ: Gom 'Kỹ năng giao tiếp', 'Email', 'Thuyết trình' vào chung 1 khóa 'Kỹ năng làm việc chuyên nghiệp'). Mỗi khóa học nên chứa từ 7 đến 20 tài liệu.

    NHIỆM VỤ CỦA BẠN:
    1. CATALOGUE & TRÙNG LẶP: Đưa các tài liệu thuần thông số, bản vẽ, bảng giá vào 'catalogues'. Đưa bản copy thừa vào 'duplicates'.
    2. GẮN VÀO KHÓA HỌC: 
       - BẠN BẮT BUỘC PHẢI ƯU TIÊN TỐI ĐA việc đưa tài liệu vào các khóa học ĐÃ TẠO ở mẻ trước (Đọc kỹ Mô tả của chúng trong danh sách TRÍ NHỚ bên dưới).
       - CHỈ ĐƯỢC TẠO KHÓA HỌC MỚI khi tài liệu có chủ đề hoàn toàn khác biệt và không thể ghép chung với bất kỳ khóa nào cũ.
    
    8 CATEGORY CHUẨN ĐƯỢC PHÉP DÙNG:
    1. Kiến thức Sản phẩm
    2. Giới thiệu về STDD và năng lực cung cấp
    3. Kỹ năng mềm
    4. Quy trình & Vận hành
    5. Catalogue / Tra cứu
    6. Quy định & chính sách
    7. Công cụ & biểu mẫu
    8. Văn hóa & phát triển cá nhân

    [TRÍ NHỚ CỦA BẠN] DANH SÁCH CÁC KHÓA HỌC ĐÃ CÓ (HÃY TÌM MỌI CÁCH ĐỂ NHÉT TÀI LIỆU VÀO ĐÂY TRƯỚC):
    {json.dumps(existing_courses_info, ensure_ascii=False)}

    [DỮ LIỆU CẦN XỬ LÝ LẦN NÀY]:
    {json.dumps(batch_materials, ensure_ascii=False)}
    
    OUTPUT JSON BẮT BUỘC:
    {{
        "duplicates": [1, 2],
        "catalogues": [3, 4],
        "assignments": [
            {{
                "material_id": 5,
                "course_title": "Tên Khóa Học (Cố gắng copy y nguyên Tên Khóa học từ TRÍ NHỚ nếu tái sử dụng. Nếu bắt buộc tạo mới thì viết tên bao quát, tổng hợp)",
                "course_desc": "Chỉ viết mô tả nếu đây là Khóa học TẠO MỚI. Nếu xài khóa cũ thì để rỗng.",
                "category": "Tên 1 trong 8 Category",
                "sub_category": "Tên SubCategory"
            }}
        ]
    }}
    """
    
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json"
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"   ❌ Lỗi gọi AI: {e}")
        return None

def main():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print("📚 BƯỚC 1: Đọc dữ liệu tài liệu hiện có...")
    materials, summary_map = fetch_all_processed_materials(cursor)
    print(f"-> Lấy thành công {len(materials)} tài liệu.")
    if not materials: return

    BATCH_SIZE = 50
    batches = [materials[i:i + BATCH_SIZE] for i in range(0, len(materials), BATCH_SIZE)]
    print(f"-> Đã chia thành {len(batches)} mẻ để quét an toàn.")

    global_duplicates = set()
    global_catalogues = set()
    global_courses = {} 

    print("\n🧠 BƯỚC 2: TIẾN HÀNH QUÉT VÀ GOM NHÓM QUYẾT LIỆT...")
    
    for idx, batch in enumerate(batches):
        print(f"\n⏳ Đang xử lý mẻ {idx+1}/{len(batches)}...")
        
        # [CẢI TIẾN QUAN TRỌNG] Gửi toàn bộ Info (Tên + Mô tả) của khóa học cũ cho AI
        existing_courses_info = [
            {"title": title, "desc": info["desc"], "category": info["category"]} 
            for title, info in global_courses.items()
        ]
        
        result = ai_process_batch(batch, existing_courses_info)
        if not result:
            print(f"   ⚠️ Mẻ {idx+1} thất bại. Bỏ qua mẻ này.")
            continue
            
        global_duplicates.update(result.get('duplicates', []))
        global_catalogues.update(result.get('catalogues', []))
        
        assignments = result.get('assignments', [])
        for assign in assignments:
            mat_id = assign.get('material_id')
            title = assign.get('course_title', '').strip()
            if not mat_id or not title: continue
            
            # Gán vào khóa cũ hoặc đẻ khóa mới
            if title not in global_courses:
                global_courses[title] = {
                    "desc": assign.get('course_desc', f"Khóa học chuyên sâu về {title}"),
                    "category": assign.get('category', 'Khác'),
                    "sub_category": assign.get('sub_category', 'Chưa phân loại'),
                    "materials": []
                }
                
            global_courses[title]["materials"].append(mat_id)
            
            old_sum = summary_map.get(mat_id)
            if old_sum:
                try:
                    s_dict = json.loads(old_sum)
                    s_dict['category'] = assign.get('category')
                    s_dict['sub_category'] = assign.get('sub_category')
                    summary_map[mat_id] = json.dumps(s_dict, ensure_ascii=False)
                except: pass

        print(f"   -> Hệ thống hiện đang ghi nhận tổng cộng {len(global_courses)} Khóa học lớn.")
        time.sleep(3) 

    print(f"\n======================================")
    print(f"-> TỔNG KẾT: Đã cô đọng thành {len(global_courses)} Khóa học (Giảm thiểu phân mảnh).")
    
    print("\n⚙️ BƯỚC 3: CẬP NHẬT DATABASE CHÍNH THỨC...")
    try:
        cursor.execute("UPDATE TRAINING_MATERIALS SET CourseID = NULL")
        
        if global_catalogues:
            print("   - Đang đẩy tài liệu vào kho Catalogue...")
            for cat_id in global_catalogues:
                old_sum = summary_map.get(cat_id)
                if old_sum:
                    try:
                        s_dict = json.loads(old_sum)
                        s_dict['category'] = "Catalogue / Tra cứu"
                        s_dict['sub_category'] = "Tài liệu kỹ thuật"
                        cursor.execute("UPDATE TRAINING_MATERIALS SET Summary = ? WHERE MaterialID = ?", (json.dumps(s_dict, ensure_ascii=False), cat_id))
                    except: pass

        cursor.execute("DELETE FROM TRAINING_COURSES")
        
        print("   - Đang thiết lập cấu trúc Khóa học mới...")
        for title, c_data in global_courses.items():
            valid_ids = [i for i in c_data['materials'] if i not in global_duplicates and i not in global_catalogues]
            if not valid_ids: continue
            
            cursor.execute("""
                INSERT INTO TRAINING_COURSES (Title, Description, Category, SubCategory, ThumbnailUrl, IsMandatory, CreatedDate, XP_Reward)
                OUTPUT INSERTED.CourseID
                VALUES (?, ?, ?, ?, '/static/img/3d_assets/culture/books.png', 0, GETDATE(), 300)
            """, (title, c_data['desc'], c_data['category'], c_data['sub_category']))
            
            new_course_id = cursor.fetchone()[0]
            
            placeholders = ','.join('?' * len(valid_ids))
            sql_up = f"UPDATE TRAINING_MATERIALS SET CourseID = ? WHERE MaterialID IN ({placeholders})"
            cursor.execute(sql_up, [new_course_id] + valid_ids)

        for mat_id, sum_json in summary_map.items():
            cursor.execute("UPDATE TRAINING_MATERIALS SET Summary = ? WHERE MaterialID = ?", (sum_json, mat_id))

        conn.commit()
        print("\n🎉 THÀNH CÔNG! Thư viện đã được quy hoạch gọn gàng, súc tích.")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ LỖI DATABASE: Đã rollback. Chi tiết: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
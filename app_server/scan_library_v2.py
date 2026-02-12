import os
import time
import json
import pyodbc
import PyPDF2
import google.generativeai as genai
from dotenv import load_dotenv
import re

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

# ==============================================================================
# PHASE 1: PHÂN TÍCH TỪNG FILE (LOCAL SCAN)
# ==============================================================================

def extract_text_from_pdf(pdf_path, max_pages=10):
    """Đọc text từ PDF"""
    text = ""
    try:
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            num_pages = len(reader.pages)
            # Đọc tối đa 10 trang để AI có đủ dữ liệu phân loại
            for i in range(min(num_pages, max_pages)):
                page = reader.pages[i]
                txt = page.extract_text()
                if txt: text += txt + "\n"
        return text, num_pages
    except Exception as e:
        print(f"❌ Lỗi đọc file {pdf_path}: {e}")
        return None, 0

def analyze_single_doc(filename, text_content):
    """
    Gửi 1 file lên AI để lấy Metadata.
    Yêu cầu AI chuẩn hóa Category theo danh mục Sếp muốn.
    """
    prompt = f"""
    Bạn là Chuyên gia Đào tạo của công ty STDD (Kinh doanh thiết bị công nghiệp).
    Hãy phân tích tài liệu: "{filename}"
    Nội dung trích dẫn:
    ---
    {text_content[:5000]}
    ---
    
    NHIỆM VỤ: Trả về JSON với các trường:
    1. "title": Tên bài học chuẩn hóa (Tiếng Việt, ngắn gọn).
    2. "category": Chọn 1 trong 3 nhóm chính: [Kỹ thuật, Kinh doanh, Kỹ năng].
    3. "sub_category": Chi tiết hơn (VD: Bạc đạn, Dầu mỡ, Thủy lực, Biến tần, Chốt sales, Lãnh đạo...).
    4. "summary": Tóm tắt nội dung (2-3 câu).
    5. "version_indicator": Nếu thấy tên file hoặc nội dung có chữ 'ver 1', 'v2', 'final', 'nháp', 'cũ'... hãy ghi chú lại (VD: "v2"), nếu không thì để null.
    """
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            
            # 1. Làm sạch chuỗi JSON (Xóa markdown ```json ... ```)
            json_str = re.sub(r"```json|```", "", response.text).strip()
            
            # 2. Parse JSON
            data = json.loads(json_str)
            
            # [FIX QUAN TRỌNG] Nếu AI trả về List ([{...}]), lấy phần tử đầu tiên
            if isinstance(data, list):
                if len(data) > 0:
                    data = data[0]
                else:
                    return None # List rỗng
            
            # [FIX QUAN TRỌNG] Đảm bảo nó là Dict thì mới trả về
            if isinstance(data, dict):
                # Fallback nếu thiếu key quan trọng
                if 'title' not in data: data['title'] = filename
                if 'sub_category' not in data: data['sub_category'] = 'General'
                return data
            
        except Exception as e:
            print(f"   ⚠️ Lỗi AI (Lần {attempt+1}): {e}")
            time.sleep(2) # Nghỉ chút rồi thử lại
            
    return None

def run_phase_1_scanning(conn):
    print("\n🚀 --- BẮT ĐẦU PHASE 1: QUÉT & PHÂN TÍCH FILE LẺ ---")
    cursor = conn.cursor()
    
    files_processed = []
    
    for root, dirs, files in os.walk(LIBRARY_DIR):
        for file in files:
            if not file.lower().endswith('.pdf'): continue
            
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, start=os.getcwd()).replace("\\", "/")
            
            # Check tồn tại để không quét lại
            cursor.execute("SELECT MaterialID FROM TRAINING_MATERIALS WHERE FileName = ?", (file,))
            existing = cursor.fetchone()
            if existing:
                print(f"⏩ Đã có: {file}")
                # Vẫn thêm vào list để chạy Phase 2 (Gom nhóm)
                # Nhưng cần lấy lại thông tin từ DB để đỡ tốn token AI đọc lại PDF
                # (Ở đây demo tôi sẽ bỏ qua bước optimize này, cứ quét file mới thôi)
                continue

            print(f"📄 Đang đọc: {file}...")
            text, pages = extract_text_from_pdf(file_path)
            if not text: continue

            # Gọi AI
            ai_data = analyze_single_doc(file, text)
            if ai_data:
                # Insert vào DB (CourseID = NULL)
                sql = """
                    INSERT INTO TRAINING_MATERIALS 
                    (FileName, FilePath, TotalPages, Summary, CreatedDate, AI_Processed, CourseID)
                    VALUES (?, ?, ?, ?, GETDATE(), 1, NULL)
                """
                # Lưu Category vào Summary tạm thời để Phase 2 đọc
                meta_summary = json.dumps(ai_data, ensure_ascii=False) # Lưu JSON vào summary để dễ parse lại
                
                cursor.execute(sql, (ai_data['title'], f"/{rel_path}", pages, meta_summary))
                conn.commit()
                print(f"   ✅ Done: {ai_data['title']} ({ai_data['sub_category']})")
                files_processed.append(ai_data)
                time.sleep(1) # Tránh spam API

    return len(files_processed)

# ==============================================================================
# PHASE 2: KIẾN TRÚC SƯ (GOM NHÓM & TẠO KHÓA HỌC)
# ==============================================================================

def run_phase_2_clustering(conn):
    print("\n🧠 --- BẮT ĐẦU PHASE 2: AI ARCHITECT (GOM KHÓA HỌC) ---")
    cursor = conn.cursor()
    
    # 1. Lấy toàn bộ Material chưa có Course (hoặc tất cả để tái cấu trúc)
    # Lấy ID và Summary (nơi chứa JSON metadata từ Phase 1)
    cursor.execute("SELECT MaterialID, FileName, Summary FROM TRAINING_MATERIALS WHERE CourseID IS NULL")
    raw_materials = cursor.fetchall()
    
    if not raw_materials:
        print("Mọi tài liệu đã được xếp lớp. Không cần chạy Phase 2.")
        return

    # Chuẩn bị dữ liệu gửi cho Gemini (chỉ gửi Metadata, không gửi full text PDF)
    materials_list = []
    for m in raw_materials:
        try:
            # Cố gắng parse JSON từ cột Summary (do Phase 1 lưu)
            meta = json.loads(m.Summary)
            materials_list.append({
                "id": m.MaterialID,
                "title": meta.get('title', m.FileName),
                "category": meta.get('category', 'Khác'),
                "sub": meta.get('sub_category', ''),
                "ver": meta.get('version_indicator', '')
            })
        except:
            # Fallback nếu summary là text thường
            materials_list.append({"id": m.MaterialID, "title": m.FileName, "category": "Unknown"})

    print(f"📦 Đang gửi {len(materials_list)} bài học lên Gemini để sắp xếp...")

    # 2. PROMPT "KIẾN TRÚC SƯ"
    # Đây là prompt quan trọng nhất để Gemini tư duy như con người
    prompt = f"""
    Bạn là Giám đốc Đào tạo cấp cao. Dưới đây là danh sách {len(materials_list)} tài liệu rời rạc (ID, Tên, Danh mục):
    
    {json.dumps(materials_list, ensure_ascii=False)}
    
    NHIỆM VỤ CỦA BẠN:
    1. **Deduplication**: Tìm các bài có nội dung trùng lặp hoặc là version cũ/mới của nhau. Gom chúng lại, chỉ giữ 1 bản mới nhất làm chính.
    2. **Course Creation**: Gom các bài học liên quan thành các "Khóa học" (Course) logic.
       - Ví dụ: Gom các bài "Bạc đạn cầu", "Bạc đạn đũa", "Lắp đặt bạc đạn" -> Khóa "Chuyên gia Bạc đạn".
       - Gom "Kỹ năng telesale", "Chốt đơn" -> Khóa "Nghệ thuật Bán hàng".
    3. **Output Structure**: Trả về JSON danh sách các Khóa học.
    
    CẤU TRÚC JSON MONG MUỐN:
    [
        {{
            "course_title": "Tên khóa học hấp dẫn (VD: Làm chủ Thủy lực 4.0)",
            "description": "Mô tả ngắn về khóa học này",
            "category": "Kỹ thuật" hoặc "Kinh doanh" hoặc "Kỹ năng",
            "thumbnail_url": "link_anh_minh_hoa (tự bịa 1 cái theo chủ đề hoặc để null)",
            "material_ids": [1, 5, 8] // Danh sách ID các bài học thuộc khóa này
        }},
        ...
    ]
    Hãy đảm bảo MỌI ID trong danh sách đầu vào đều được phân vào một khóa học nào đó (hoặc khóa "Tài liệu chung").
    """

    try:
        response = model.generate_content(prompt)
        json_str = re.sub(r"```json|```", "", response.text).strip()
        courses_plan = json.loads(json_str)
        
        print(f"🤖 Gemini đề xuất {len(courses_plan)} khóa học. Đang thực thi vào DB...")
        
        # 3. THỰC THI VÀO DB
        for course in courses_plan:
            # A. Tạo Course
            thumb = course.get('thumbnail_url')
            if not thumb: # Fallback ảnh mẫu
                cat = course['category']
                if 'Kỹ thuật' in cat: thumb = '/static/img/course_tech.jpg'
                elif 'Kinh doanh' in cat: thumb = '/static/img/course_sales.jpg'
                else: thumb = '/static/img/course_softskill.jpg'

            sql_course = """
                INSERT INTO TRAINING_COURSES (Title, Description, Category, ThumbnailUrl, IsMandatory, CreatedDate, XP_Reward)
                OUTPUT INSERTED.CourseID
                VALUES (?, ?, ?, ?, 0, GETDATE(), 300)
            """
            cursor.execute(sql_course, (course['course_title'], course['description'], course['category'], thumb))
            new_course_id = cursor.fetchone()[0]
            
            # B. Gán Materials vào Course này
            ids = course['material_ids']
            if ids:
                placeholders = ','.join('?' * len(ids))
                sql_update = f"UPDATE TRAINING_MATERIALS SET CourseID = ? WHERE MaterialID IN ({placeholders})"
                cursor.execute(sql_update, [new_course_id] + ids)
                
            print(f"   Created Course [{new_course_id}]: {course['course_title']} ({len(ids)} bài)")

        conn.commit()
        print("✅ HOÀN TẤT SẮP XẾP KHÓA HỌC!")

    except Exception as e:
        print(f"❌ Lỗi Phase 2 (Clustering): {e}")
        # In ra response để debug nếu lỗi JSON
        print(response.text if 'response' in locals() else "No response")

def main():
    conn = get_db_connection()
    
    # Bước 1: Quét file lẻ và phân loại sơ bộ
    run_phase_1_scanning(conn)
    
    # Bước 2: Gom nhóm và tạo Course
    run_phase_2_clustering(conn)
    
    conn.close()

if __name__ == "__main__":
    main()
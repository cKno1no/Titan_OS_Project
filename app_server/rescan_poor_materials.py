import os
import json
import pyodbc
import PyPDF2
import re
import time
import google.generativeai as genai
from dotenv import load_dotenv

# --- CẤU HÌNH ---
load_dotenv()
API_KEY = "AIzaSyBLi_xp5bSdRXC8jpveV_mgumrushjZqBA" # Thay bằng Key thật

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

def clean_json_string(text):
    text = re.sub(r"```json|```", "", text).strip()
    s = text.find('{')
    e = text.rfind('}')
    if s != -1 and e != -1:
        return text[s:e+1]
    return "{}"

def extract_text_from_pdf(filepath, max_pages=15):
    """Đọc text từ file PDF vật lý"""
    if not os.path.exists(filepath):
        return None
    try:
        text = ""
        with open(filepath, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            num_pages = min(len(reader.pages), max_pages) # Đọc tối đa 15 trang đầu để tiết kiệm token
            for i in range(num_pages):
                page_text = reader.pages[i].extract_text()
                if page_text:
                    text += page_text + "\n"
        return text
    except Exception as e:
        print(f"Lỗi đọc PDF {filepath}: {e}")
        return None


def deep_scan_with_ai(filename, pdf_text):
    """Bắt AI đọc text và tóm tắt lại đàng hoàng, ép xuất chuẩn JSON"""
    prompt = f"""
    Bạn là Chuyên gia Đào tạo của công ty STD&D.
    Tài liệu này tên là: "{filename}".
    Dưới đây là nội dung trích xuất từ file PDF của tài liệu:
    
    --- START CONTENT ---
    {pdf_text[:15000]}
    --- END CONTENT ---
    
    YÊU CẦU:
    1. Đọc kỹ nội dung trên và tạo một bản tóm tắt chi tiết. 
    2. Phần tóm tắt (summary) PHẢI DÀI TỪ 100 ĐẾN 200 TỪ, diễn giải rõ ràng tài liệu này nói về cái gì, dùng cho ai, và mang lại kiến thức/giá trị gì. Tuyệt đối không được trả lời hời hợt kiểu "Tài liệu nội bộ" hay "Cần kiểm tra lại".
    3. QUAN TRỌNG NHẤT: TUYỆT ĐỐI KHÔNG DÙNG DẤU NGOẶC KÉP (") VÀ KHÔNG XUỐNG DÒNG BÊN TRONG CÁC ĐOẠN TEXT. Nếu cần trích dẫn, hãy dùng dấu nháy đơn (').
    
    OUTPUT JSON THEO ĐÚNG ĐỊNH DẠNG:
    {{
        "title": "Tên tài liệu đã được chuẩn hóa cho đẹp",
        "category": "Chọn 1 trong: Kiến thức Sản phẩm / Giải pháp Ngành / Kỹ năng & Văn hóa / Quy trình & Vận hành / Catalogue / Tra cứu",
        "sub_category": "Tên nhóm phụ (ngắn gọn)",
        "summary": "Nội dung tóm tắt chi tiết..."
    }}
    """
    
    try:
        # ÉP BUỘC GEMINI TRẢ VỀ JSON CHUẨN (Không bao giờ bị lỗi format)
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json"
            )
        )
        
        # Vì đã ép mime_type, kết quả trả về chắc chắn là chuỗi JSON sạch
        return json.loads(response.text)
    except Exception as e:
        print(f"   ❌ Lỗi gọi AI: {e}")
        # In ra nội dung AI trả về để xem nếu vẫn bị lỗi
        if 'response' in locals():
            print(f"      [Dữ liệu thô AI trả về]: {response.text}")
        return None

def main():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print("🔍 BƯỚC 1: Quét Database tìm các tài liệu có Summary kém chất lượng...")
    cursor.execute("SELECT MaterialID, FileName, FilePath, Summary FROM TRAINING_MATERIALS WHERE AI_Processed = 1")
    rows = cursor.fetchall()
    
    poor_materials = []
    
    for row in rows:
        mat_id = row.MaterialID
        summary_raw = row.Summary
        
        desc_text = ""
        if summary_raw:
            try:
                parsed = json.loads(summary_raw)
                desc_text = parsed.get('summary', "")
            except:
                desc_text = summary_raw
        
        # LOGIC LỌC: Đếm số từ, nếu dưới 30 từ hoặc dính chữ rác thì đem đi quét lại
        word_count = len(desc_text.split())
        is_poor = False
        
        if word_count < 30: 
            is_poor = True
        elif "cần kiểm tra lại" in desc_text.lower() or "tài liệu nội bộ" in desc_text.lower():
            is_poor = True
            
        if is_poor:
            poor_materials.append({
                'id': mat_id,
                'filename': row.FileName,
                'filepath': row.FilePath,
                'current_summary': desc_text
            })
            
    print(f"-> Đã phát hiện {len(poor_materials)} tài liệu có tóm tắt quá ngắn (dưới 30 từ).")
    
    if not poor_materials:
        print("Mọi thứ đều ổn, không cần quét lại PDF.")
        return
        
    print("\n⚙️ BƯỚC 2: Bắt đầu Deep Scan (Mở file PDF và đọc lại nội dung)...")
    
    success_count = 0
    for idx, mat in enumerate(poor_materials):
        print(f"\n[{idx+1}/{len(poor_materials)}] Đang xử lý: {mat['filename']}")
        print(f"   - Tóm tắt cũ đang bị lỗi: '{mat['current_summary']}'")
        
        # Đường dẫn file vật lý (có thể cần chỉnh sửa tùy theo cách cấu trúc thư mục của bạn)
        # Nếu FilePath trong DB lưu dạng /static/uploads/... thì bỏ dấu / đầu tiên đi để nối chuỗi
        relative_path = mat['filepath'].lstrip('/') if mat['filepath'] else ""
        physical_path = os.path.join(os.getcwd(), relative_path)
        
        pdf_text = extract_text_from_pdf(physical_path)
        
        if not pdf_text or len(pdf_text.strip()) < 50:
            print("   ⚠️ Không thể đọc chữ từ file PDF này (có thể là ảnh scan hoặc file lỗi). Đánh dấu bỏ qua.")
            continue
            
        print("   - Đã bóc xuất text thành công. Đang gửi AI phân tích...")
        ai_result = deep_scan_with_ai(mat['filename'], pdf_text)
        
        if ai_result:
            try:
                # Đảm bảo giữ lại field 'ver' nếu có
                ai_result['ver'] = "v_rescanned" 
                new_json_str = json.dumps(ai_result, ensure_ascii=False)
                
                # Cập nhật Database
                cursor.execute("UPDATE TRAINING_MATERIALS SET Summary = ? WHERE MaterialID = ?", (new_json_str, mat['id']))
                conn.commit()
                success_count += 1
                print(f"   ✅ Đã tạo tóm tắt mới: {ai_result.get('summary')[:100]}...")
            except Exception as e:
                print(f"   ❌ Lỗi cập nhật DB: {e}")
        
        time.sleep(2) # Nghỉ 2s tránh bị Google chặn Rate Limit

    conn.close()
    print(f"\n🎉 HOÀN TẤT DEEP SCAN! Đã làm lại tóm tắt chất lượng cho {success_count} tài liệu.")

if __name__ == "__main__":
    main()
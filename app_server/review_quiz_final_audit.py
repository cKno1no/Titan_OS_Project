import os
import time
import json
import pyodbc
import re
import google.generativeai as genai
from dotenv import load_dotenv
from PIL import Image

# --- CẤU HÌNH ---
load_dotenv()
API_KEY = "AIzaSyBLi_xp5bSdRXC8jpveV_mgumrushjZqBA" # Hoặc lấy từ env

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


genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

IMAGE_BASE_DIR = os.path.join("static", "images", "N3H")



def get_db_connection():
    return pyodbc.connect(CONN_STR)

def clean_json_string(text):
    text = re.sub(r"```json|```", "", text).strip()
    s = text.find('{')
    e = text.rfind('}')
    if s != -1 and e != -1:
        return text[s:e+1]
    return "{}"




def audit_expert_content(row):
    q_code = row.QuestionCode
    
    # 1. Tìm ảnh (Hỗ trợ nhiều định dạng ảnh)
    img_obj = None
    has_image = False
    valid_extensions = ['.jpg', '.jpeg', '.png', '.JPG', '.PNG']
    
    for ext in valid_extensions:
        temp_path = os.path.join(IMAGE_BASE_DIR, f"{q_code}{ext}")
        if os.path.exists(temp_path):
            try:
                img_obj = Image.open(temp_path)
                has_image = True
                print(f"   🖼️ Đã tìm thấy và đính kèm ảnh: {q_code}{ext}")
                break
            except Exception as e:
                print(f"   ⚠️ Lỗi đọc ảnh {temp_path}: {e}")

    # --- GHÉP NỘI DUNG CÂU HỎI VÀ TẤT CẢ CÁC OPTION (A đến F) ---
    full_question = row.Content or ""
    if hasattr(row, 'OptionA') and row.OptionA: full_question += f"\n- {row.OptionA}"
    if hasattr(row, 'OptionB') and row.OptionB: full_question += f"\n- {row.OptionB}"
    if hasattr(row, 'OptionC') and row.OptionC: full_question += f"\n- {row.OptionC}"
    if hasattr(row, 'OptionD') and row.OptionD: full_question += f"\n- {row.OptionD}"
    if hasattr(row, 'OptionE') and row.OptionE: full_question += f"\n- {row.OptionE}"
    if hasattr(row, 'OptionF') and row.OptionF: full_question += f"\n- {row.OptionF}"

    # --- TÍNH TOÁN SỐ TỪ CỦA ĐÁP ÁN HIỆN TẠI (Để báo cho AI biết) ---
    current_answer = str(row.CorrectAnswer) if row.CorrectAnswer else ""
    word_count = len(current_answer.split())

    # 2. Prompt (Thêm Rule Giữ nguyên & Kiểm tra độ dài 300 từ)
    prompt = f"""
    Bạn là Kỹ sư Trưởng đang rà soát lại đáp án thi nghiệp vụ của công ty.
    
    CÂU HỎI ĐẦY ĐỦ: 
    {full_question}
    
    ĐÁP ÁN HIỆN TẠI ĐANG LƯU TRONG HỆ THỐNG (Độ dài: {word_count} từ): 
    "{current_answer}"
    
    {'[HÃY NHÌN ẢNH ĐÍNH KÈM ĐỂ ĐỐI CHIẾU MÃ SỐ TRONG HÌNH VỚI TEXT CỦA CÂU HỎI]' if has_image else ''}
    
    NHIỆM VỤ CỦA BẠN:
    1. Đánh giá ĐÁP ÁN HIỆN TẠI. 
       - YÊU CẦU QUAN TRỌNG: Nếu đáp án hiện tại ĐÚNG về mặt kỹ thuật/logic (dù diễn đạt chưa hoàn hảo) VÀ có độ dài DƯỚI 300 từ: HÃY GIỮ NGUYÊN (đặt is_wrong = false).
       
       - Bạn PHẢI đánh dấu là CẦN SỬA LẠI (is_wrong = true) NẾU rơi vào 1 trong 3 trường hợp sau:
         + Trường hợp 1: Kiến thức kỹ thuật bị sai hoặc KHÔNG KHỚP với thông tin trong hình ảnh.
         + Trường hợp 2: CÂU HỎI YÊU CẦU SỐ LIỆU CỤ THỂ, SO SÁNH THÔNG SỐ NHƯNG đáp án hiện tại lại trả lời lý thuyết suông, không có con số.
         + Trường hợp 3: ĐÁP ÁN QUÁ DÀI (Trên 300 từ). Đáp án này ({word_count} từ) đang quá dài, lê thê, không phù hợp để làm đáp án chấm điểm thi. Cần tóm tắt lại.
    
    2. NẾU BẠN CHỌN is_wrong = true, hãy tạo "new_answer" tuân thủ NGHIÊM NGẶT các quy tắc sau:
       - BIẾN THÀNH ĐÁP ÁN MẪU: súc tích (Dưới 150-200 từ). Hãy nhớ người thi chỉ có tối đa 10 phút để tự gõ đáp án này.
       - ĐI THẲNG VÀO TRỌNG TÂM. TUYỆT ĐỐI KHÔNG viết các câu mở bài luyên thuyên như "Dựa trên phân tích hình ảnh...", "Theo tiêu chuẩn...", "Đáp án chính xác là...".
       - NẾU LÀ CÂU HỎI GHÉP HÌNH / TÌM MÃ: CHỈ liệt kê kết quả dạng gạch đầu dòng ngắn gọn nhất (Ví dụ: Hình 1: Mã A, Hình 2: Mã B). KHÔNG giải thích dài dòng kẻ bảng nếu đề không yêu cầu.
       - NẾU LÀ CÂU HỎI KỸ THUẬT (Như P4 vs P6): Trả lời trực tiếp số liệu (Ví dụ: "P4 có độ đảo tâm 2.5µm, P6 là 6µm. P4 chính xác hơn").
       
    3. Viết GIẢI THÍCH (Explanation):
       - Phần giải thích chi tiết, lập luận tại sao lại chọn đáp án đó hãy để dành viết vào mục "explanation" này (dưới 100 từ).
       
    OUTPUT JSON:
    {{
        "is_wrong": true/false,
        "new_answer": "...",
        "explanation": "..."
    }}
    """
    
    try:
        inputs = [prompt]
        if has_image and img_obj: inputs.append(img_obj)
        
        response = model.generate_content(inputs)
        return json.loads(clean_json_string(response.text))
    except Exception as e:
        print(f"   ❌ Lỗi AI: {e}")
        return None


def main():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print("🕵️ BẮT ĐẦU AUDIT ĐÒI HỎI CAO KỸ THUẬT (BỎ QUA ASSESSMENT)...")
    
    # --- LỆNH SQL ĐÃ ĐƯỢC CẬP NHẬT ---
    # 1. Lấy đủ các cột OptionA, B, C, D
    # 2. Bỏ qua các câu hỏi có Category là 'Assessment'
    sql = """
        SELECT ID, QuestionCode, Content, OptionA, OptionB, OptionC, OptionD, OptionE, OptionF, CorrectAnswer, Explanation 
        FROM TRAINING_QUESTION_BANK 
        WHERE CorrectAnswer IS NOT NULL 
        AND (Category IS NULL OR Category <> 'Assessment')
        ORDER BY ID DESC
    """
    questions = cursor.execute(sql).fetchall()
    
    print(f"📋 Tìm thấy {len(questions)} câu hỏi cần duyệt.")
    
    count_fixed = 0
    count_explained = 0
    
    for idx, row in enumerate(questions):
        print(f"\n[{idx+1}/{len(questions)}] Duyệt câu {row.QuestionCode}...")
        
        res = audit_expert_content(row)
        
        if res:
            needs_update = False
            
            # 1. Xử lý CorrectAnswer
            if res.get('is_wrong') == True:
                raw_new_ans = res.get('new_answer')
                
                # Xử lý an toàn nếu AI trả về dict/list thay vì string
                if isinstance(raw_new_ans, (dict, list)):
                    if isinstance(raw_new_ans, dict) and 'text' in raw_new_ans:
                        new_ans = str(raw_new_ans['text'])
                    else:
                        new_ans = json.dumps(raw_new_ans, ensure_ascii=False)
                else:
                    new_ans = str(raw_new_ans) if raw_new_ans else ""

                if new_ans and new_ans.strip() != "" and new_ans != row.CorrectAnswer:
                    print(f"   ⚠️ PHÁT HIỆN SAI KỸ THUẬT/THIẾU SỐ LIỆU -> Sửa lại.")
                    cursor.execute("UPDATE TRAINING_QUESTION_BANK SET CorrectAnswer = ? WHERE ID = ?", (new_ans, row.ID))
                    count_fixed += 1
                    needs_update = True
            else:
                print("   ✅ Đáp án hợp lý -> Giữ nguyên.")

            # 2. Xử lý Explanation
            raw_expl = res.get('explanation')
            if isinstance(raw_expl, (dict, list)):
                new_expl = json.dumps(raw_expl, ensure_ascii=False)
            else:
                new_expl = str(raw_expl) if raw_expl else ""

            if new_expl:
                if (not row.Explanation) or (new_expl != row.Explanation):
                    print("   ℹ️ Cập nhật giải thích.")
                    cursor.execute("UPDATE TRAINING_QUESTION_BANK SET Explanation = ? WHERE ID = ?", (new_expl, row.ID))
                    count_explained += 1
                    needs_update = True
            
            if needs_update:
                conn.commit()
        
        time.sleep(1)

    print(f"\n🏁 HOÀN TẤT! Sửa {count_fixed} câu, Giải thích {count_explained} câu.")
    conn.close()

if __name__ == "__main__":
    main()
# services/tools_schema.py
from google.generativeai.types import FunctionDeclaration

def get_tools_definitions():
    return [
        FunctionDeclaration(
            name="check_product_info",
            description="Tra cứu thông định sản phẩm (Giá, Tồn kho, Lịch sử mua). Phân biệt rõ Tên Hàng và Tên Khách.",
            parameters={
                "type": "object",
                "properties": {
                    "product_keywords": {"type": "string", "description": "Mã hoặc tên sản phẩm (VD: '22210 NSK')"},
                    "customer_name": {"type": "string", "description": "Tên khách hàng (VD: 'Kraft', 'Hoa Sen')"},
                    "selection_index": {"type": "integer", "description": "Số thứ tự nếu user chọn từ danh sách trước đó"}
                },
                "required": ["product_keywords"]
            }
        ),
        FunctionDeclaration(
            name="check_delivery_status",
            description="Kiểm tra tình trạng giao hàng THỰC TẾ (Xe chạy chưa, đã giao xong chưa). Dùng bảng Delivery Weekly. Sử dụng khi hỏi: 'Giao chưa?', 'Xe đi chưa?', 'Đang ở đâu?'.",
            parameters={
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Tên khách hàng"},
                    "product_keywords": {"type": "string", "description": "Mã hàng cụ thể cần kiểm tra (Nếu có)."},
                    "selection_index": {"type": "integer", "description": "Số thứ tự user chọn"}
                },
                "required": ["customer_name"]
            }
        ),
        FunctionDeclaration(
            name="check_replenishment",
            description="Kiểm tra nhu cầu đặt hàng dự phòng (Safety Stock/ROP/BackOrder).",
            parameters={
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Tên khách hàng"},
                    "i02id_filter": {"type": "string", "description": "Mã lọc phụ (VD: 'AB' hoặc mã I02ID cụ thể)"},
                    "selection_index": {"type": "integer", "description": "Số thứ tự user chọn"}
                },
                "required": ["customer_name"]
            }
        ),
        FunctionDeclaration(
            name="check_customer_overview",
            description="Xem tổng quan về khách hàng (Doanh số, Công nợ cơ bản).",
            parameters={
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Tên khách hàng"},
                    "selection_index": {"type": "integer", "description": "Số thứ tự user chọn"}
                }
            }
        ),
        FunctionDeclaration(
            name="check_daily_briefing",
            description="Tổng hợp công việc hôm nay (Task, Approval, Report).",
            parameters={
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "enum": ["today", "week"]}
                }
            }
        ),
        FunctionDeclaration(
            name="summarize_customer_report",
            description="Đọc và tóm tắt báo cáo (Notes/Activities) của khách hàng.",
            parameters={
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Tên khách hàng"},
                    "months": {"type": "integer", "description": "Số tháng (mặc định 6)"},
                    "selection_index": {"type": "integer", "description": "Số thứ tự user chọn"}
                },
                "required": ["customer_name"]
            }
        ),
        FunctionDeclaration(
            name="analyze_customer_deep_dive",
            description="Phân tích chuyên sâu 360 độ (KPIs, Top SP, Cơ hội bỏ lỡ, Lãi biên...). Dùng cho câu hỏi 'Phân tích', 'Báo cáo chi tiết'.",
            parameters={
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Tên khách hàng"},
                    "selection_index": {"type": "integer", "description": "Số thứ tự user chọn nếu có danh sách"}
                },
                "required": ["customer_name"]
            }
        ),
        FunctionDeclaration(
            name="lookup_sales_flow",
            description="Tra cứu dữ liệu Dòng chảy Kinh doanh (PXK, Hóa đơn, Lịch sử). Dùng View Tổng hợp. Sử dụng khi hỏi: 'Xuất kho ngày nào?', 'Số hóa đơn?', 'Giá bán bao nhiêu?', 'Lịch sử mua hàng'.",
            parameters={
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string", 
                        "enum": ["check_export_invoice", "check_price_history", "customer_list"],
                        "description": "Mục đích: check_export_invoice (Ngày xuất kho/HĐ), check_price_history (Lịch sử giá/SL), customer_list (Ai mua mã này)"
                    },
                    "product_keywords": {"type": "string", "description": "Mã hoặc tên sản phẩm"},
                    "customer_name": {"type": "string", "description": "Tên khách hàng"},
                    "order_ref": {"type": "string", "description": "Số đơn hàng (SO), Số PXK hoặc Số Hóa đơn"},
                    "months": {"type": "integer", "description": "Số tháng tra cứu (Mặc định 6)."}
                },
                "required": ["intent"]
            }
        ),
        FunctionDeclaration(
            name="get_titan_stories",
            description="Kể chuyện Hall of Fame. Đối tượng hợp lệ bao gồm: 1. Các nhân sự (Titan). 2. CÔNG TY STDD (Ngôi nhà chung). Nếu hỏi về STDD, BẮT BUỘC dùng tool này.",
            parameters={
                "type": "object",
                "properties": {
                    "titan_name": {"type": "string", "description": "Tên nhân sự hoặc tên công ty (VD: 'STDD', 'Ngôi nhà chung')."},
                    "tag_filter": {"type": "string", "description": "Chủ đề (Tag) muốn lọc."}
                },
                "required": ["titan_name"]
            }
        ),
        FunctionDeclaration(
            name="search_company_documents",
            description="Tìm kiếm và trích xuất tài liệu nội bộ (Quy chế, Nội quy, Hướng dẫn kỹ thuật...). TRÍCH DẪN RÕ TÊN FILE VÀ SỐ TRANG khi trả lời.",
            parameters={
                "type": "object",
                "properties": {
                    "search_query": {
                        "type": "string",
                        "description": "Từ khóa tìm kiếm quy định, chính sách công ty (VD: 'quy định nghỉ phép', 'tính lương')."
                    }
                },
                "required": ["search_query"]
            }
        )
    ]
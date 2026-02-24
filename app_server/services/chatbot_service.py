# services/chatbot_service.py
from flask import current_app, session
import google.generativeai as genai
from datetime import datetime
import traceback
import config
from db_manager import safe_float
import logging

# Import các module vừa tách
from services.tools_schema import get_tools_definitions
from services.rag_memory_service import RagMemoryService
from services.chatbot_ui_helper import ChatbotUIHelper
from services.training_service import TrainingService
from services.gamification_service import GamificationService

logger = logging.getLogger(__name__)

class ChatbotService:
    def __init__(self, sales_lookup_service, customer_service, delivery_service, task_service, app_config, db_manager):
        self.lookup_service = sales_lookup_service
        self.customer_service = customer_service
        self.delivery_service = delivery_service
        self.task_service = task_service
        self.db = db_manager
        self.app_config = app_config
        
        self.gamification = GamificationService(db_manager)
        self.training_service = TrainingService(db_manager, self.gamification)
        self.rag_service = RagMemoryService(db_manager)
        
        from services.customer_analysis_service import CustomerAnalysisService
        self.analysis_service = CustomerAnalysisService(db_manager) 

        api_key = "x"
        if api_key: genai.configure(api_key=api_key)

        self.skill_mapping = {
            'check_delivery_status': 'skill_delivery',
            'check_replenishment': 'skill_replenishment',
            'check_customer_overview': 'skill_overview',
            'check_daily_briefing': 'skill_briefing',
            'summarize_customer_report': 'skill_report',
            'lookup_sales_flow' : 'skill_Salesflow',
            'analyze_customer_deep_dive': 'skill_deepdive',
            'get_titan_stories': 'skill_stories'
        }

        self.tools_definitions = get_tools_definitions()
            
        self.model = genai.GenerativeModel(model_name='gemini-2.5-flash', tools=[self.tools_definitions])
        if not self.model: 
            self.model = genai.GenerativeModel('gemini-1.5-flash', tools=[self.tools_definitions])

        self.functions_map = {
            'check_product_info': self._wrapper_product_info,
            'check_delivery_status': self._wrapper_delivery_status,
            'check_replenishment': self._wrapper_replenishment,
            'check_customer_overview': self._wrapper_customer_overview,
            'check_daily_briefing': self._wrapper_daily_briefing,
            'summarize_customer_report': self._wrapper_summarize_report,
            'analyze_customer_deep_dive': self._wrapper_analyze_deep_dive,
            'lookup_sales_flow' : self._wrapper_lookup_sales_flow,
            'get_titan_stories': self._wrapper_titan_stories,
            'search_company_documents': self._wrapper_search_documents
        }

    # =========================================================================
    # HÀM XỬ LÝ QUYỀN VÀ RATE LIMIT
    # =========================================================================
    def _check_user_has_skill(self, user_code, func_name):
        if func_name not in self.skill_mapping: return True, None
        required_item_code = self.skill_mapping[func_name]
        check = self.db.get_data("SELECT TOP 1 ID FROM TitanOS_UserInventory WHERE UserCode = ? AND ItemCode = ? AND IsActive = 1", (user_code, required_item_code))
        if check: return True, None
        skill_info = self.db.get_data("SELECT ItemName FROM TitanOS_SystemItems WHERE ItemCode = ?", (required_item_code,))
        return False, skill_info[0]['ItemName'] if skill_info else required_item_code
        
    def _get_equipped_pet_info(self, user_code):
        data = self.db.get_data("SELECT T2.ItemName, T2.ItemCode FROM TitanOS_UserProfile T1 JOIN TitanOS_SystemItems T2 ON T1.EquippedPet = T2.ItemCode WHERE T1.UserCode = ?", (user_code,))
        if data:
            nicknames = {'fox': 'Bé Cáo AI', 'bear': 'Bé Gấu Mặp', 'dragon': 'Bé Rồng Bự', 'monkey': 'Bé Khỉ Thiền', 'cat': 'Bé Mèo Béo', 'deer': 'Bé Nai Ngơ'}
            return nicknames.get(data[0]['ItemCode'], data[0]['ItemName'])
        return "Bé Titan" 

    def _check_ai_rate_limit(self, user_code, user_role):
        base_limit, bonus_per_level = 20, 2
        if user_role == 'ADMIN': max_limit = base_limit * 100 
        else:
            try: max_limit = base_limit + (int(self.db.get_data("SELECT Level FROM TitanOS_UserStats WHERE UserCode = ?", (user_code,))[0]['Level']) * bonus_per_level)
            except: max_limit = base_limit + bonus_per_level

        redis_client = current_app.redis_client
        if not redis_client: return True, max_limit, 0 
            
        key = f"ai_limit:chatbot:{datetime.now().strftime('%Y%m%d')}:{user_code}"
        try:
            current_usage = int(redis_client.get(key) or 0)
            if current_usage >= max_limit: return False, max_limit, current_usage
            pipe = redis_client.pipeline()
            pipe.incr(key)
            if current_usage == 0: pipe.expire(key, 86400)
            pipe.execute()
            return True, max_limit, current_usage + 1
        except Exception: return True, max_limit, 0 

    # =========================================================================
    # MAIN ORCHESTRATOR 
    # =========================================================================
    def process_message(self, message_text, user_code, user_role, theme='light'):
        try:
            clean_msg_for_check = message_text.strip().upper()
            if not (len(clean_msg_for_check) == 1 and clean_msg_for_check in ['A', 'B', 'C', 'D']):
                is_allowed, max_limit, current_usage = self._check_ai_rate_limit(user_code, user_role)
                if not is_allowed:
                    return f"⚡ **Cảnh báo Năng lượng:** Sếp đã dùng hết giới hạn AI hôm nay ({max_limit}/{max_limit} lượt)."
        
            user_profile = self.db.get_data("SELECT Nickname, SHORTNAME FROM TitanOS_UserProfile P JOIN [GD - NGUOI DUNG] U ON P.UserCode = U.USERCODE WHERE P.UserCode = ?", (user_code,))
            user_name = user_profile[0].get('Nickname') or user_profile[0].get('SHORTNAME') if user_profile else "Sếp"
            pet_name = self._get_equipped_pet_info(user_code) if theme == 'adorable' else "AI"
            
            base_personas = {
                'light': "Bạn là Trợ lý Kinh doanh Titan (Business Style). Trả lời rành mạch, tập trung vào số liệu.",
                'dark': "Bạn là Hệ thống Titan OS (Formal). Xưng hô: Tôi - Bạn. Phong cách trang trọng, chính xác, khách quan.",
                'fantasy': "Bạn là AI từ tương lai (Sci-Fi). Xưng hô: Commander - System. Giọng điệu máy móc, hào hứng.",
                'adorable': f"Bạn là {pet_name} (Gen Z). Người dùng tên là {user_name}. Xưng hô: Em ({pet_name}) - Hãy gọi người dùng là {user_name} hoặc Sếp {user_name}. Dùng emoji 🦊🐻💖✨. Giọng cute, năng động, hỗ trợ nhiệt tình."
            }
            
            hall_of_fame_rule = """
            QUY TẮC HALL OF FAME:
            - 'Titan' bao gồm cả CON NGƯỜI và TẬP THỂ CÔNG TY (STDD).
            - Nếu user hỏi 'kể về STDD', 'ngôi nhà chung', 'công ty', HÃY DÙNG TOOL `get_titan_stories` để kể chuyện.
            """

            system_instruction = f"{base_personas.get(theme, base_personas['light'])}\n{hall_of_fame_rule}"
            
            history = session.get('chat_history', [])
            gemini_history = []
            for h in history:
                gemini_history.append({"role": "user", "parts": [h['user']]})
                gemini_history.append({"role": "model", "parts": [h['bot']]})

            chat = self.model.start_chat(history=gemini_history, enable_automatic_function_calling=False)
            self.current_user_code = user_code
            self.current_user_role = user_role

            if len(clean_msg_for_check) == 1 and clean_msg_for_check in ['A', 'B', 'C', 'D']:
                res = self.training_service.check_daily_answer(user_code, clean_msg_for_check)
                if res: return res

            full_prompt = f"[System Instruction: {system_instruction}]\nUser Query: {message_text}"
            response = chat.send_message(full_prompt)
            
            final_text = ""
            function_call_part = None
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.function_call:
                        function_call_part = part.function_call
                        break
            
            if function_call_part:
                func_name = function_call_part.name
                func_args = dict(function_call_part.args)
                
                if current_app: current_app.logger.info(f"🤖 AI Calling Tool: {func_name} | Args: {func_args}")

                has_permission, skill_name = self._check_user_has_skill(user_code, func_name)

                if not has_permission:
                    api_result = f"SYSTEM_ALERT: Người dùng CHƯA sở hữu kỹ năng '{skill_name}'. Hãy từ chối thực hiện và yêu cầu họ vào 'Cửa hàng'."
                else:
                    if func_name in self.functions_map:
                        try:
                            api_result = self.functions_map[func_name](**func_args)
                        except Exception as e:
                            api_result = f"Lỗi thực thi hàm {func_name}: {str(e)}"
                    else:
                        api_result = "Hàm không tồn tại trong hệ thống."
                
                # ==============================================================================
                # CƠ CHẾ FAST-RESPONSE: PHÂN LUỒNG RENDER (TRÁNH BỊ AI TÓM TẮT MẤT ĐỊNH DẠNG MÀU MÈ)
                # ==============================================================================
                if func_name == 'search_company_documents':
                    # CHỈ DUY NHẤT HÀM RAG LÀ CẦN AI TÓM TẮT THÀNH ĐOẠN VĂN
                    final_res = chat.send_message({
                        "function_response": {
                            "name": func_name,
                            "response": {"result": api_result}
                        }
                    })
                    final_text = final_res.text
                else:
                    # CÒN LẠI TẤT CẢ CÁC HÀM SALES/BÁO CÁO PHẢI XẢ THẲNG RA MÀN HÌNH ĐỂ GIỮ MARKDOWN GỐC
                    final_text = api_result

            else:
                final_text = response.text

            history.append({'user': message_text, 'bot': final_text})
            session['chat_history'] = history[-10:]
            return final_text

        except Exception as e:
            traceback.print_exc()
            return f"Hệ thống đang bận hoặc gặp lỗi kết nối AI. Vui lòng thử lại sau. (Error: {str(e)})"

    # =========================================================================
    # CÁC HÀM WRAPPER & HELPER (HOÀN TRẢ NGUYÊN BẢN 100% NHƯ FILE ORIGINAL CỦA SẾP)
    # =========================================================================

    def _wrapper_search_documents(self, search_query):
        if current_app: current_app.logger.info(f"📚 AI đang quét RAG: {search_query}")
        return self.rag_service.search_vector_database(search_query) or "Không tìm thấy nội quy, hãy trả lời bằng kiến thức chung."

    def _resolve_customer(self, customer_name, selection_index):
        context_list = session.get('customer_search_results')
        if selection_index is not None and context_list:
            try:
                idx = int(selection_index) - 1
                if 0 <= idx < len(context_list):
                    selected = context_list[idx]
                    session.pop('customer_search_results', None)
                    return [selected] 
            except: pass

        if not customer_name: return None
        customers = self.customer_service.get_customer_by_name(customer_name)
        if not customers: return "NOT_FOUND"
        if len(customers) > 1:
            session['customer_search_results'] = customers 
            return "MULTIPLE"
        return customers
    
    def _safe_format_date(self, date_obj, fmt='%d/%m/%y'):
        if date_obj is None: return None
        if str(date_obj) == 'NaT': return None
        try: return date_obj.strftime(fmt)
        except: return None
        
    def _wrapper_product_info(self, product_keywords, customer_name=None, selection_index=None):
        if not customer_name and not selection_index:
            return self._handle_quick_lookup(product_keywords)

        cust_result = self._resolve_customer(customer_name, selection_index)
        if cust_result == "NOT_FOUND":
            return f"Không tìm thấy khách hàng '{customer_name}'.\nĐang tra nhanh mã '{product_keywords}'...\n" + self._handle_quick_lookup(product_keywords)
                   
        if cust_result == "MULTIPLE":
            return self._format_customer_options(session['customer_search_results'], customer_name)
        
        customer_obj = cust_result[0]
        price_info_str = self._handle_price_check_final(product_keywords, customer_obj)
        history_info_str = self._handle_check_history_final(product_keywords, customer_obj)
        
        return f"""
### 📦 Kết quả tra cứu: {customer_obj['FullName']}
---
{price_info_str}

{history_info_str}
"""

    def _wrapper_delivery_status(self, customer_name, product_keywords=None, selection_index=None):
        cust_result = self._resolve_customer(customer_name, selection_index)
        if cust_result == "NOT_FOUND": return f"❌ Không tìm thấy khách hàng '{customer_name}'."
        if cust_result == "MULTIPLE": return self._format_customer_options(session['customer_search_results'], customer_name)
        
        customer_id = cust_result[0]['ID']
        customer_full_name = cust_result[0]['FullName']
        
        sql = f"""
            SELECT TOP 5 
                M.VoucherNo, M.ActualDeliveryDate, M.DeliveryStatus, 
                M.Planned_Day, O.RefNo02, D.Notes, D.InventoryID,
                ISNULL(D.ActualQuantity, 0) as Quantity,
                ISNULL(I.InventoryName, D.InventoryID) as InventoryName
            FROM [CRM_STDD].[dbo].[Delivery_Weekly] M
            LEFT JOIN {config.ERP_DELIVERY_MASTER} O ON M.VoucherID = O.VoucherID
            LEFT JOIN {config.ERP_DELIVERY_DETAIL} D ON M.VoucherID = D.VoucherID
            LEFT JOIN {config.ERP_IT1302} I ON D.InventoryID = I.InventoryID
            WHERE M.ObjectID = ?
        """
        params = [customer_id]

        if product_keywords:
            sql += " AND (D.InventoryID LIKE ? OR I.InventoryName LIKE ?)"
            kw = f"%{product_keywords}%"
            params.extend([kw, kw])
        
        sql += " AND M.VoucherDate >= DATEADD(month, -3, GETDATE()) ORDER BY M.VoucherDate DESC"
        
        try:
            data = self.db.get_data(sql, tuple(params))
            if not data:
                return f"ℹ️ Không tìm thấy Lệnh Xuất Hàng (Delivery) nào cho **{customer_full_name}** trong 3 tháng qua (khớp yêu cầu)."

            res = f"🚚 **Tình trạng Vận chuyển Thực tế (Delivery Weekly):**\n"
            count = 0
            for item in data:
                status = str(item.get('DeliveryStatus', '')).strip().upper()
                icon = "🟢" if status in ['DONE', 'DA GIAO'] else "🟠"
                actual_date_str = self._safe_format_date(item.get('ActualDeliveryDate'), '%d/%m')
                
                if actual_date_str: date_info = f"Đã giao: **{actual_date_str}**"
                else: date_info = f"KH: {item.get('Planned_Day', 'POOL')}"

                item_info = ""
                if item.get('InventoryID'):
                    qty = safe_float(item.get('Quantity', 0))
                    inv_id = item['InventoryID']
                    inv_name = item.get('InventoryName', '')
                    if inv_name and inv_name != inv_id:
                        if len(inv_name) > 30: inv_name = inv_name[:27] + "..."
                        display_str = f"{inv_id} - {inv_name}"
                    else:
                        display_str = inv_id
                    item_info = f"📦 **{display_str}**: {qty:,.0f}"

                ref_info = item.get('RefNo02')
                note_info = item.get('Notes')
                extra_details = []
                if ref_info: extra_details.append(f"Ref: {ref_info}")
                if note_info: extra_details.append(f"Note: {note_info}")
                detail_str = f" _({', '.join(extra_details)})_" if extra_details else ""
                
                res += f"- {icon} **{item['VoucherNo']}**: {status} | {date_info} | {item_info}{detail_str}\n"
                count += 1
                if count >= 5: 
                    res += "... (còn thêm kết quả)"
                    break 
            return res
        except Exception as e:
            return f"Lỗi tra cứu Delivery Weekly: {str(e)}"

    def _wrapper_replenishment(self, customer_name, i02id_filter=None, selection_index=None):
        cust_result = self._resolve_customer(customer_name, selection_index)
        if cust_result == "NOT_FOUND": return f"Không tìm thấy khách hàng '{customer_name}'."
        if cust_result == "MULTIPLE": return self._format_customer_options(session['customer_search_results'], customer_name)
        
        customer_obj = cust_result[0]
        if i02id_filter: customer_obj['i02id_filter'] = i02id_filter
        return self._handle_replenishment_check_final(customer_obj)

    def _wrapper_customer_overview(self, customer_name, selection_index=None):
        cust_result = self._resolve_customer(customer_name, selection_index)
        if cust_result == "NOT_FOUND": return f"❌ Không tìm thấy khách hàng '{customer_name}'."
        if cust_result == "MULTIPLE": return self._format_customer_options(session['customer_search_results'], customer_name)
        
        data = self.db.get_data("SELECT TOP 1 ObjectName, O05ID, Address, (SELECT SUM(ConLai) FROM AR_AgingDetail WHERE ObjectID = T1.ObjectID) as Debt FROM IT1202 T1 WHERE ObjectID = ?", (cust_result[0]['ID'],))
        if data:
            c = data[0]
            return (f"🏢 **{c['ObjectName']}** ({cust_result[0]['ID']})\n"
                    f"- Phân loại: {c['O05ID']}\n"
                    f"- Công nợ: {c['Debt'] or 0:,.0f} VND\n"
                    f"- Địa chỉ: {c['Address']}")
        return "Lỗi lấy dữ liệu chi tiết."

    def _wrapper_daily_briefing(self, scope='today'):
        user_code = getattr(self, 'current_user_code', '')
        res = f"📅 **Tổng quan công việc ({scope}):**\n"
        
        sql_task = "SELECT Subject, Priority FROM Task_Master WHERE AssignedTo = ? AND Status != 'Done' AND DueDate <= GETDATE()"
        tasks = self.db.get_data(sql_task, (user_code,))
        if tasks: res += "\n📌 **Việc cần làm ngay:**\n" + "\n".join([f"- {t['Subject']} ({t['Priority']})" for t in tasks])
        else: res += "\n📌 **Việc cần làm:** Tuyệt vời! Bạn không có task quá hạn."

        sql_approval = "SELECT COUNT(*) as Cnt FROM OT2101 WHERE OrderStatus = 0" 
        approval = self.db.get_data(sql_approval)
        if approval and approval[0]['Cnt'] > 0: res += f"\n\n💰 **Phê duyệt:** Hệ thống có {approval[0]['Cnt']} Báo giá đang chờ duyệt."
        return res

    def _wrapper_summarize_report(self, customer_name, months=6, selection_index=None):
        try: months = int(float(months)) if months else 6
        except: months = 6

        cust_result = self._resolve_customer(customer_name, selection_index)
        if cust_result == "NOT_FOUND": return f"❌ Không tìm thấy khách hàng '{customer_name}'."
        if cust_result == "MULTIPLE": return self._format_customer_options(session['customer_search_results'], customer_name)

        customer_obj = cust_result[0]
        customer_id = customer_obj['ID']
        customer_full_name = customer_obj['FullName']
        search_keyword = customer_name if len(customer_name) > 3 else customer_full_name 

        sql = f"""
            SELECT TOP 60 
                [Ngay] as CreatedDate, [Nguoi] as CreateUser,
                CAST([Noi dung 1] AS NVARCHAR(MAX)) as Content1, 
                CAST([Noi dung 2] AS NVARCHAR(MAX)) as Content2_Added,
                CAST([Danh gia 2] AS NVARCHAR(MAX)) as Content3,
                [Khach hang] as TaggedCustomerID
            FROM {config.TEN_BANG_BAO_CAO}
            WHERE 
                ([Ngay] >= DATEADD(month, -?, GETDATE()))
                AND (
                    [Khach hang] = ?  
                    OR (CAST([Noi dung 1] AS NVARCHAR(MAX)) LIKE N'%{search_keyword}%')
                    OR (CAST([Noi dung 2] AS NVARCHAR(MAX)) LIKE N'%{search_keyword}%')
                )
            ORDER BY [Ngay] DESC
        """ 

        try:
            reports = self.db.get_data(sql, (months, customer_id))
        except Exception as e:
            return f"Lỗi hệ thống khi truy xuất báo cáo: {str(e)}"
            
        if not reports:
            return f"ℹ️ Không tìm thấy báo cáo nào liên quan đến **{customer_full_name}** trong {months} tháng qua."

        context_text_raw = ""
        related_count = 0
        direct_count = 0
        
        for r in reports:
            date_val = r.get('CreatedDate')
            date_str = date_val.strftime('%d/%m/%Y') if date_val else 'N/A'
            c1, c2, c3 = str(r.get('Content1', '')).strip(), str(r.get('Content2_Added', '')).strip(), str(r.get('Content3', '')).strip()
            content = ". ".join([p for p in [c1, c2, c3] if p])
            if not content or content == '.': continue 
            
            tagged_id = str(r.get('TaggedCustomerID', '')).strip()
            if tagged_id == str(customer_id):
                source_type, direct_count = "TRỰC TIẾP", direct_count + 1
            else:
                source_type, related_count = "LIÊN QUAN", related_count + 1
            context_text_raw += f"- [{date_str}] [{source_type}] {r['CreateUser']}: {content}\n"
        
        system_prompt = (
            f"Bạn là trợ lý Kinh doanh. Nhiệm vụ: Tóm tắt tình hình khách hàng {customer_full_name} trong 20-25 dòng.\n"
            f"- Lọc thông tin liên quan đến '{search_keyword}' hoặc '{customer_full_name}'.\n"
            "- Tổng hợp thành 3 phần: \n"
            "   + 1. Tổng quan\n"
            "   + 2. Điểm Tốt & Thành Tựu\n"
            "   + 3. Rủi ro & Cần Cải Thiện.\n"
            "- Trình bày Markdown rõ ràng."
        )
        
        full_input = f"### 📊 DỮ LIỆU: {direct_count} Trực tiếp | {related_count} Liên quan\n---" + context_text_raw
        try:
            summary_model = genai.GenerativeModel(model_name=self.model.model_name, system_instruction=system_prompt, generation_config={"temperature": 0.2, "top_p": 0.8, "top_k": 40})
            return summary_model.generate_content(contents=[full_input]).text
        except Exception as e:
            return f"Lỗi AI xử lý tóm tắt: {str(e)}"

    def _wrapper_analyze_deep_dive(self, customer_name, selection_index=None):
        cust_result = self._resolve_customer(customer_name, selection_index)
        if cust_result == "NOT_FOUND": return f"❌ Không tìm thấy khách hàng '{customer_name}'."
        if cust_result == "MULTIPLE": return self._format_customer_options(session['customer_search_results'], customer_name)
        
        customer_obj = cust_result[0]
        cust_id, cust_name = customer_obj['ID'], customer_obj['FullName']
        
        try:
            metrics = self.analysis_service.get_header_metrics(cust_id)
            top_products = self.analysis_service.get_top_products(cust_id)[:10]
            missed_opps = self.analysis_service.get_missed_opportunities_quotes(cust_id)[:10]
            category_data = self.analysis_service.get_category_analysis(cust_id)
        except Exception as e:
            return f"Gặp lỗi khi trích xuất dữ liệu phân tích: {str(e)}"

        res = f"### 📊 BÁO CÁO PHÂN TÍCH SÂU: {cust_name} ({cust_id})\n"
        
        res += "**1. Sức khỏe Tài chính & Vận hành (YTD):**\n"
        res += f"- **Doanh số:** {metrics.get('SalesYTD', 0):,.0f} (Target: {metrics.get('TargetYear', 0):,.0f})\n"
        res += f"- **Đơn hàng:** {metrics.get('OrderCount', 0)} | **Báo giá:** {metrics.get('QuoteCount', 0)}\n"
        res += f"- **Công nợ:** Hiện tại {metrics.get('DebtCurrent', 0):,.0f} | Quá hạn **{metrics.get('DebtOverdue', 0):,.0f}**\n"
        res += f"- **Hiệu suất Giao hàng (OTIF):** {metrics.get('OTIF', 0)}%\n"
        res += f"- **Tương tác (Báo cáo):** {metrics.get('ReportCount', 0)} lần\n\n"
        
        res += "**2. Top 10 Sản phẩm Bán chạy (2 năm qua):**\n"
        if top_products:
            for i, p in enumerate(top_products):
                name = p.get('InventoryName', p['InventoryID'])
                rev = safe_float(p.get('TotalRevenue', 0))
                qty_ytd = safe_float(p.get('Qty_YTD', 0))
                res += f"{i+1}. **{name}**: {rev:,.0f} đ (SL năm nay: {qty_ytd:,.0f})\n"
        else: res += "_Chưa có dữ liệu bán hàng._\n"
        res += "\n"

        res += "**3. Top 10 Cơ hội Bỏ lỡ (Báo giá trượt 5 năm):**\n"
        if missed_opps:
            for i, m in enumerate(missed_opps):
                name = m.get('InventoryName', m['InventoryID'])
                val = safe_float(m.get('MissedValue', 0))
                count = m.get('QuoteCount', 0)
                res += f"{i+1}. **{name}**: Trượt {val:,.0f} đ ({count} lần báo)\n"
        else: res += "_Không có cơ hội bỏ lỡ đáng kể._\n"
        res += "\n"
        
        res += "**4. Cơ cấu Nhóm hàng & Hiệu quả (Top 5):**\n"
        if category_data and 'details' in category_data:
            details = category_data['details']
            for i, item in enumerate(details[:5]):
                name, rev, profit, margin = item['name'], item['revenue'], item.get('profit', 0), item.get('margin_pct', 0)
                icon = "🟢" if margin >= 15 else ("🟠" if margin >= 5 else "🔴")
                res += f"- **{name}**: {rev:,.0f} đ | Lãi: {profit:,.0f} ({icon} **{margin}%**)\n"
        elif category_data and 'labels' in category_data:
            for i, label in enumerate(category_data['labels'][:5]):
                res += f"- **{label}**: {category_data['series'][i]:,.0f} đ\n"
        else: res += "_Chưa có dữ liệu phân tích nhóm hàng._\n"

        res += "\n💡 **Gợi ý từ Titan AI:**\n"
        if safe_float(metrics.get('DebtOverdue', 0)) > 10000000:
            res += "- ⚠️ Cảnh báo: Nợ quá hạn cao, cần nhắc nhở khách.\n"
        if safe_float(metrics.get('OrderCount', 0)) == 0 and safe_float(metrics.get('QuoteCount', 0)) > 5:
            res += "- ⚠️ Tỷ lệ chốt đơn thấp. Cần xem lại giá hoặc đối thủ cạnh tranh.\n"
        if missed_opps:
            res += f"- 🎯 Cơ hội: Nên chào lại mã **{missed_opps[0].get('InventoryName', 'N/A')}** vì khách đã hỏi nhiều lần.\n"

        return res
    
    def _wrapper_lookup_sales_flow(self, intent, product_keywords=None, customer_name=None, order_ref=None, months=None):
        customer_id = None
        customer_display = "Tất cả KH"
        if customer_name:
            cust_result = self._resolve_customer(customer_name, None)
            if cust_result == "NOT_FOUND": return f"❌ Không tìm thấy khách hàng '{customer_name}'."
            if cust_result == "MULTIPLE": return self._format_customer_options(session['customer_search_results'], customer_name)
            customer_id = cust_result[0]['ID']
            customer_display = cust_result[0]['FullName']

        try: months = int(months) if months else 24 
        except: months = 24
            
        product_filter = f"%{product_keywords}%" if product_keywords else "%"
        order_filter = f"%{order_ref}%" if order_ref else "%"

        base_sql = f"SELECT TOP 50 * FROM {config.VIEW_CHATBOT_SALES_FLOW} WHERE 1=1"
        params = []

        if customer_id:
            base_sql += " AND CustomerCode = ?"
            params.append(customer_id)
        if product_keywords:
            base_sql += " AND (InventoryID LIKE ? OR InventoryName LIKE ?)"
            params.extend([product_filter, product_filter])
        if order_ref:
            base_sql += " AND (OrderNo LIKE ? OR InvoiceNo LIKE ? OR DeliveryVoucherNos LIKE ?)"
            params.extend([order_filter, order_filter, order_filter])
        if not order_ref:
            base_sql += " AND OrderDate >= DATEADD(month, -?, GETDATE())"
            params.append(months)

        base_sql += " ORDER BY OrderDate DESC"

        try:
            data = self.db.get_data(base_sql, tuple(params))
        except Exception as e:
            return f"Lỗi truy xuất View Sales Flow: {str(e)}"

        if not data:
            return f"ℹ️ Không tìm thấy dữ liệu phù hợp cho **{customer_display}** trong {months} tháng qua."

        res_lines = []
        if intent == 'customer_list':
            detail_summary = {}
            for d in data:
                c_name, inv_id, inv_name = d.get('CustomerName', 'Khách lẻ'), d.get('InventoryID', ''), d.get('InventoryName', '')
                key = (c_name, inv_id, inv_name)
                detail_summary[key] = detail_summary.get(key, 0) + d['Qty_Ordered']
            
            sorted_items = sorted(detail_summary.items(), key=lambda x: x[1], reverse=True)
            res_lines.append(f"👥 **Khách mua '{product_keywords}' ({months} tháng):**")
            
            for (c_name, inv_id, inv_name), qty in sorted_items[:7]:
                res_lines.append(f"- **{c_name}**: {inv_id} - {inv_name}, mua **{qty:,.0f}** cái")
            
            remaining = len(sorted_items) - 7
            if remaining > 0: res_lines.append(f"... và {remaining} mã/khách khác.")

        else: 
            first_item = data[0]
            c_name = first_item.get('CustomerName', customer_display)
            c_code = first_item.get('CustomerCode', '')
            inv_id = first_item.get('InventoryID', '')
            inv_name = first_item.get('InventoryName', '')
            years_txt = f"{months//12} năm" if months >= 12 else f"{months} tháng"
            
            res_lines.append(f"Khách hàng **{c_name}** ({c_code}) đã mua **{len(data)}** lần **{inv_id}** - {inv_name} trong {years_txt} qua:\n")

            count = 0
            for i, item in enumerate(data):
                if count >= 5: break 
                so_no, price, qty = item.get('OrderNo', 'N/A'), item.get('UnitPrice', 0), item.get('Qty_Ordered', 0)
                inv_no = item.get('InvoiceNo')
                inv_str = f", hóa đơn {inv_no}" if inv_no else ""
                
                export_date = self._safe_format_date(item.get('LastExportDate'), '%d/%m/%Y')
                if export_date: date_str = f"giao ngày {export_date}"
                else: date_str = f"đặt ngày {self._safe_format_date(item.get('OrderDate'), '%d/%m/%Y')} (Chưa giao)"

                res_lines.append(f"{i+1}/ Đơn hàng ({so_no}): giá **{price:,.0f}**, mua {qty:,.0f} cái{inv_str}, {date_str}.")
                count += 1
            
            remaining = len(data) - count
            if remaining > 0: res_lines.append(f"... và {remaining} lần mua khác.")

        return "\n".join(res_lines)

    def _wrapper_titan_stories(self, titan_name, tag_filter=None):
        try:
            target_code = None
            target_name = None
            job_title = "Nhân sự Titan"
            department = "STDD"
            personal_tags = ""
            is_stdd_entity = False
            
            raw_input = titan_name.strip()
            clean_name_upper = raw_input.upper()
            stdd_keywords = ['STDD', 'CÔNG TY', 'CONG TY', 'NGÔI NHÀ', 'NGOI NHA', 'TẬP THỂ']
            
            if any(k in clean_name_upper for k in stdd_keywords) and len(clean_name_upper) < 20: 
                target_code, target_name, is_stdd_entity = 'STDD', 'NGÔI NHÀ CHUNG STDD', True
            else:
                honorifics = ['SẾP', 'SEP', 'BOSS', 'ANH', 'CHỊ', 'CHI', 'EM', 'CÔ', 'CHÚ', 'BÁC', 'MR', 'MS', 'MRS']
                search_term = raw_input
                for prefix in honorifics:
                    if clean_name_upper.startswith(prefix + " "): 
                        search_term = raw_input[len(prefix):].strip()
                        break
                
                sql_find_user = f"SELECT TOP 1 U.UserCode, U.shortname, U.userName, ISNULL(P.JobTitle, 'Titan Member') as JobTitle, ISNULL(P.Department, 'STDD') as Department, P.PersonalTags FROM [GD - NGUOI DUNG] U LEFT JOIN TitanOS_UserProfile P ON U.UserCode = P.UserCode WHERE (U.shortname LIKE N'%{search_term}%') OR (U.userName LIKE N'%{search_term}%') OR (U.UserCode = '{search_term}')"
                user_data_list = self.db.get_data(sql_find_user)
                if not user_data_list:
                    if 'STDD' in clean_name_upper: target_code, target_name, is_stdd_entity = 'STDD', 'NGÔI NHÀ CHUNG STDD', True
                    else: return f"⚠️ Không tìm thấy đồng nghiệp tên '{search_term}' trong hệ thống."
                else:
                    u = user_data_list[0]
                    target_code = u['UserCode']
                    target_name = ChatbotUIHelper.get_formal_target_name(u)
                    job_title = u['JobTitle']
                    department = u['Department']
                    personal_tags = u.get('PersonalTags', '')

            sql_stories = "SELECT StoryID, StoryTitle, StoryContent, AuthorUserCode, Tags, ImagePaths FROM HR_HALL_OF_FAME WHERE TargetUserCode = ? AND IsPublic = 1"
            params = [target_code]
            display_tag_text = tag_filter
            
            if tag_filter:
                normalized_tag = ChatbotUIHelper.ai_translate_tag(tag_filter, self.model)
                sql_stories += " AND Tags LIKE ?"
                params.append(f"%{normalized_tag}%")
                vn = ChatbotUIHelper.TAG_TRANSLATIONS.get(normalized_tag)
                display_tag_text = f"{vn} ({normalized_tag})" if vn else normalized_tag

            stories = self.db.get_data(sql_stories, tuple(params))

            if not stories:
                if is_stdd_entity: return "Chưa có dữ liệu về STDD."
                tags_display = ChatbotUIHelper.format_tags_bilingual(personal_tags) if personal_tags else "Chiến binh thầm lặng"
                prompt = f"Bạn là một cây bút phóng sự chân dung. Hãy phác họa về **{target_name}** ({job_title}). Dữ liệu: Các từ khóa đặc trưng: {tags_display}. NHIỆM VỤ: Viết 150-200 từ. KHÔNG dùng từ phủ định. Hãy bắt đầu bằng: 'Trong dòng chảy công việc tại STDD...'"
                return ChatbotUIHelper.build_titan_html_card(f"HỒ SƠ: {target_name.upper()}", job_title, None, self.model.generate_content(prompt).text)

            context_data, all_tags, img_gallery = "", [], []
            for idx, s in enumerate(stories[:10]):
                if s['Tags']: all_tags.extend([t.strip().replace('#','') for t in s['Tags'].replace(',', ' ').split() if t.strip()])
                if s['ImagePaths']: img_gallery.extend([i.strip() for i in s['ImagePaths'].split(',') if i.strip()])
                context_data += f"\n[DỮ LIỆU GỐC #{idx+1}]: {s['StoryContent']}"

            cover_image = img_gallery[0] if img_gallery else None

            if not tag_filter:
                from collections import Counter
                top_tags = [t[0] for t in Counter(all_tags).most_common(10)]
                tags_menu = ChatbotUIHelper.format_tags_bilingual(", ".join(top_tags))
                prompt = f"[MODE: BLOGGER PORTRAIT] Đối tượng: **{target_name}**. NHIỆM VỤ: Viết đoạn tóm tắt chân dung 200-300 từ. Cuối bài mời chọn: '👉 Các chủ đề nổi bật: {tags_menu}'. CẤM: Không đếm số lượng. DỮ LIỆU: {context_data}"
            else:
                prompt = f"🔴 [STRICT BLOGGER STORYTELLING MODE] Kể về **{target_name}** qua chủ đề **{display_tag_text}**. YÊU CẦU: Ít nhất 3 đoạn văn sâu sắc (300-500 từ). Tiêu đề phụ trong thẻ <strong>. Chọn 1 chi tiết đắt giá vào thẻ <blockquote>. Hào hùng, trân trọng. DỮ LIỆU: {context_data}"

            return ChatbotUIHelper.build_titan_html_card(f"HỒI KÝ TITAN: {target_name.upper()}" if not is_stdd_entity else "BIÊN NIÊN SỬ STDD", job_title, cover_image, self.model.generate_content(prompt).text)
        except Exception as e:
            return f"Lỗi hệ thống: {str(e)}"

    def _format_customer_options(self, customers, term, limit=5):
        response = f"🔍 Tìm thấy **{len(customers)}** khách hàng tên '{term}'. Sếp chọn số mấy?\n"
        for i, c in enumerate(customers[:limit]):
            response += f"**{i+1}**. {c['FullName']} (Mã: {c['ID']})\n"
        return response

    def _get_customer_detail(self, cust_id):
        sql = "SELECT TOP 1 ObjectName, O05ID, Address, (SELECT SUM(ConLai) FROM AR_AgingDetail WHERE ObjectID = T1.ObjectID) as Debt FROM IT1202 T1 WHERE ObjectID = ?"
        data = self.db.get_data(sql, (cust_id,))
        if data:
            c = data[0]
            return (f"🏢 **{c['ObjectName']}** ({cust_id})\n- Phân loại: {c['O05ID']}\n- Công nợ: {c['Debt'] or 0:,.0f} VND\n- Địa chỉ: {c['Address']}")
        return "Lỗi lấy dữ liệu chi tiết."

    def _handle_quick_lookup(self, item_codes, limit=5):
        try:
            data = self.lookup_service.get_quick_lookup_data(item_codes)
            if not data: return f"Không tìm thấy thông tin cho mã: '{item_codes}'."
            
            response_lines = [f"**Kết quả tra nhanh Tồn kho ('{item_codes}'):**"]
            for item in data[:limit]:
                inv_id, inv_name = item['InventoryID'], item.get('InventoryName', 'N/A') 
                ton, bo, gbqd = item.get('Ton', 0), item.get('BackOrder', 0), item.get('GiaBanQuyDinh', 0)
                
                line = f"- **{inv_name}** ({inv_id}):\n  Tồn: **{ton:,.0f}** | BO: **{bo:,.0f}** | Giá QĐ: **{gbqd:,.0f}**"
                if bo > 0: line += f"\n  -> *Gợi ý: Mã này đang BackOrder.*"
                response_lines.append(line)
            return "\n".join(response_lines)
        except Exception as e: return f"Lỗi tra cứu nhanh: {e}"

    def _handle_price_check_final(self, item_term, customer_object, limit=5):
        try: block1 = self.lookup_service._get_block1_data(item_term, customer_object['ID'])
        except Exception as e: return f"Lỗi lấy giá: {e}"
        
        if not block1: return f"Không tìm thấy mặt hàng '{item_term}' cho KH {customer_object['FullName']}."
            
        response_lines = [f"**Kết quả giá cho '{item_term}' (KH: {customer_object['FullName']}):**"]
        for item in block1[:limit]:
            gbqd, gia_hd, ngay_hd = safe_float(item.get('GiaBanQuyDinh', 0)), safe_float(item.get('GiaBanGanNhat_HD', 0)), item.get('NgayGanNhat_HD', '—') 
            line = f"- **{item.get('InventoryName', 'N/A')}** ({item.get('InventoryID')}):\n  Giá Bán QĐ: **{gbqd:,.0f}**"
            
            if gia_hd > 0 and ngay_hd != '—':
                percent_diff = ((gia_hd / gbqd) - 1) * 100 if gbqd > 0 else 0
                line += f"\n  Giá HĐ gần nhất: **{gia_hd:,.0f}** (Ngày: {ngay_hd}) ({'+' if percent_diff >= 0 else ''}{percent_diff:.1f}%)"
            else:
                line += "\n  *(Chưa có lịch sử HĐ)*"
            response_lines.append(line)
        return "\n".join(response_lines)

    def _handle_check_history_final(self, item_term, customer_object, limit=5):
        items_found = self.lookup_service.get_quick_lookup_data(item_term)
        if not items_found: return ""

        response_lines, found_history = [f"**Lịch sử mua hàng:**"], False
        for item in items_found[:limit]:
            item_id = item['InventoryID']
            last_invoice_date = self.lookup_service.check_purchase_history(customer_object['ID'], item_id)
            
            line = f"- **{item_id}**: "
            if last_invoice_date:
                found_history = True
                line += f"**Đã mua** (Gần nhất: {last_invoice_date})"
            else: line += "**Chưa mua**"
            response_lines.append(line)

        if not found_history: return f"**Chưa.** KH chưa mua mặt hàng nào khớp với '{item_term}'."
        return "\n".join(response_lines)

    def _handle_replenishment_check_final(self, customer_object, limit=10):
        data = self.lookup_service.get_replenishment_needs(customer_object['ID'])
        if not data: return f"KH **{customer_object['FullName']}** không có nhu cầu dự phòng."

        deficit_items = [i for i in data if safe_float(i.get('LuongThieuDu')) > 1]
        filter_note, filtered_items = "", deficit_items
        
        if customer_object.get('i02id_filter'):
            target = customer_object['i02id_filter'].upper()
            if target != 'AB':
                filtered_items = [i for i in deficit_items if (i.get('I02ID') == target) or (i.get('NhomHang', '').upper().startswith(f'{target}_'))]
                filter_note = f" theo mã **{target}**"

        if not filtered_items: return f"KH **{customer_object['FullName']}** đủ hàng dự phòng{filter_note}."

        response_lines = [f"KH **{customer_object['FullName']}** cần đặt **{len(filtered_items)}** nhóm hàng{filter_note}:"]
        for i, item in enumerate(filtered_items[:limit]):
            thieu, rop, ton_bo = safe_float(item.get('LuongThieuDu', 0)), safe_float(item.get('DiemTaiDatROP', 0)), safe_float(item.get('TonBO', 0))
            response_lines.append(f"**{i+1}. {item.get('NhomHang')}**\n  - Thiếu: **{thieu:,.0f}** | ROP: {rop:,.0f} | Tồn-BO: {ton_bo:,.0f}")
        return "\n".join(response_lines)
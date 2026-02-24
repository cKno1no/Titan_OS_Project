# services/kpi_service.py

from db_manager import DBManager, safe_float
from flask import current_app
import math

class KPIService:
    def __init__(self, db_manager: DBManager):
        self.db = db_manager

    
    def _get_targets(self, user_code, year):
        """
        Lấy đồng thời chỉ tiêu của Sales và chỉ tiêu của Thư Ký từ bảng DTCL.
        [UPDATED] Theo yêu cầu mới: DS hỗ trợ đăng ký cũng lấy từ cột [PHU TRACH DS]
        """
        query = """
            SELECT 
                (SELECT SUM(ISNULL(DK, 0)) FROM [CRM_STDD].[dbo].[DTCL] WHERE RTRIM([PHU TRACH DS]) = ? AND Nam = ?) AS SalesTarget,
                (SELECT SUM(ISNULL(DK, 0)) FROM [CRM_STDD].[dbo].[DTCL] WHERE RTRIM([PHU TRACH DS]) = ? AND Nam = ?) AS AdminTarget
        """
        data = self.db.get_data(query, (user_code, year, user_code, year))
        
        sales_target_yr = safe_float(data[0]['SalesTarget']) if data and data[0]['SalesTarget'] else 0
        admin_target_yr = safe_float(data[0]['AdminTarget']) if data and data[0]['AdminTarget'] else 0
        
        return {
            'sales_month': (sales_target_yr / 12) if sales_target_yr > 0 else 1000000000.0,
            'admin_month': (admin_target_yr / 12) if admin_target_yr > 0 else 1000000000.0
        }

    
    def fetch_all_actuals(self, year, month, user_code):
        """
        Gọi Master SPs để lấy toàn bộ chỉ số thực tế của User.
        Tự động tính toán các chỉ số phái sinh (như % hoàn thành).
        """
        actuals = {}
        
        # =====================================================================
        # 1. LẤY DATA KINH DOANH & THƯ KÝ
        # =====================================================================
        sales_data = self.db.execute_sp_multi('sp_KPI_Sales_GetMetrics', (year, month, user_code))
        if sales_data and sales_data[0]:
            sd = sales_data[0][0]
            
            # Lấy Target tháng linh hoạt (Sales vs Admin)
            targets = self._get_targets(user_code, year)
            
            # --- CHỈ SỐ NHÓM KINH DOANH (SALES) ---
            actual_sales_total = safe_float(sd.get('Actual_Sales_Total', 0))
            actuals['Revenue_Salesman_Pct'] = (actual_sales_total / targets['sales_month']) * 100
            
            actuals['Revenue_NewCust_Mil'] = safe_float(sd.get('Actual_Sales_NewCust', 0)) / 1000000.0
            actuals['AR_Overdue_Rate_Sales'] = safe_float(sd.get('AR_Overdue_Rate', 0))
            
            # --- CHỈ SỐ NHÓM THƯ KÝ (ADMIN) ---
            # % Hoàn thành Doanh số Support (Áp với Target của cột THU KY)
            actual_support = safe_float(sd.get('Actual_Support_Sales', 0))
            actuals['Revenue_Employee_Pct'] = (actual_support / targets['admin_month']) * 100
            
            # Doanh số Kênh Văn phòng (Quy ra Triệu VNĐ)
            actuals['Revenue_Office_Mil'] = safe_float(sd.get('Actual_Office_Sales', 0)) / 1000000.0
            
            # Đếm số hóa đơn giao trễ > 7 ngày so với Date01
            actuals['Late_Delivery_Admin'] = safe_float(sd.get('Late_Delivery_Admin', 0))
            
            # (Chỉ số Win-rate sẽ lấy từ SP hệ thống nếu có form duyệt báo giá)
            actuals['Quote_WinRate'] = safe_float(sd.get('Quote_WinRate', 0))

        # =====================================================================
        # 2. LẤY DATA KẾ TOÁN (SP 2 - ĐÃ CẬP NHẬT FULL)
        # =====================================================================
        acc_data = self.db.execute_sp_multi('sp_KPI_Acc_GetMetrics', (year, month, user_code))
        if acc_data and acc_data[0]:
            ad = acc_data[0][0]
            actuals['Invoice_DelayCount'] = safe_float(ad.get('Invoice_DelayCount', 0))
            actuals['Invoice_CancelCount'] = safe_float(ad.get('Invoice_CancelCount', 0))
            actuals['Missing_Invoice_Receipts'] = safe_float(ad.get('Missing_Invoice_Receipts', 0))
            actuals['AR_Overdue_Rate_Acc'] = safe_float(ad.get('AR_Overdue_Rate', 0))
            actuals['Budget_Variance_Pct'] = safe_float(ad.get('Budget_Variance_Pct', 0))
            
            # Các trường mới từ SP Acc đã nâng cấp
            actuals['Avg_Order_Process_Hours'] = safe_float(ad.get('Avg_Order_Process_Hours', 0))
            actuals['Negative_Stock_Errors'] = safe_float(ad.get('Negative_Stock_Errors', 0))
            actuals['Overdue_Reduction_Rate'] = safe_float(ad.get('Overdue_Reduction_Rate', 0))
            actuals['Cash_Flow_Velocity_Days'] = safe_float(ad.get('Cash_Flow_Velocity_Days', 0))

        # =====================================================================
        # 3. LẤY DATA KHO (SP 3 - ĐÃ CẬP NHẬT FULL)
        # =====================================================================
        whs_data = self.db.execute_sp_multi('sp_KPI_Whs_GetMetrics', (year, month, user_code))
        if whs_data and whs_data[0]:
            wd = whs_data[0][0]
            actuals['OTIF_Rate'] = safe_float(wd.get('OTIF_Rate', 0))
            actuals['Avg_Picking_Hours'] = safe_float(wd.get('Avg_Picking_Hours', 0))
            actuals['Total_Lines_Picked'] = safe_float(wd.get('Total_Lines_Picked', 0))
            actuals['Total_Lines_Putaway'] = safe_float(wd.get('Total_Lines_Putaway', 0))
            actuals['Delay_Docs_Count'] = safe_float(wd.get('Delay_Docs_Count', 0))
            
            # Các trường mới từ SP Whs đã nâng cấp
            actuals['Loss_Value'] = safe_float(wd.get('Loss_Value', 0)) / 1000000.0 # Quy đổi ra Triệu VNĐ
            actuals['Warehouse_Budget_Over_Pct'] = safe_float(wd.get('Warehouse_Budget_Over_Pct', 0))

        # =====================================================================
        # 4. LẤY DATA HỆ THỐNG TITAN (SP 4)
        # =====================================================================
        sys_data = self.db.execute_sp_multi('sp_KPI_Sys_GetMetrics', (year, month, user_code))
        if sys_data and sys_data[0]:
            syd = sys_data[0][0]
            actuals['CRM_Report_Count'] = safe_float(syd.get('CRM_Report_Count', 0))
            actuals['Task_Completion_Rate'] = safe_float(syd.get('Task_Completion_Rate', 0))
            actuals['Approval_SLA_Hours'] = safe_float(syd.get('Approval_SLA_Hours', 0))
            actuals['Gamification_XP'] = safe_float(syd.get('Gamification_XP', 0))

        return actuals

    def get_actual_value_for_criteria(self, criteria_id, actuals):
        """Map (Khớp) ID Tiêu chí với trường dữ liệu thực tế."""
        mapping = {
            # --- SALES & ADMIN ---
            'KPI_KD_01': actuals.get('Revenue_Salesman_Pct', 0),
            'KPI_KD_02': actuals.get('Revenue_NewCust_Mil', 0),
            'KPI_KD_03': actuals.get('AR_Overdue_Rate_Sales', 0),
            'KPI_TK_01': actuals.get('Revenue_Employee_Pct', 0),
            'KPI_TK_02': actuals.get('Revenue_Office_Mil', 0),
            'KPI_TK_03': actuals.get('Late_Delivery_Admin', 0),
            'KPI_TK_04': actuals.get('Quote_WinRate', 0),
            
            # --- KẾ TOÁN (ĐÃ CẬP NHẬT FULL) ---
            'KPI_KT_01': actuals.get('Approval_SLA_Hours', 0),
            'KPI_KT_02': actuals.get('Budget_Variance_Pct', 0),
            'KPI_KT_03': actuals.get('Invoice_CancelCount', 0),      # Lỗi nghiệp vụ
            'KPI_KT_04': actuals.get('AR_Overdue_Rate_Acc', 0),
            'KPI_KT_05': actuals.get('Overdue_Reduction_Rate', 0),   # [NEW] Giảm nợ
            'KPI_KT_06': actuals.get('Cash_Flow_Velocity_Days', 0),  # [NEW] Dòng tiền
            'KPI_KT_07': actuals.get('Negative_Stock_Errors', 0),    # [NEW] Âm kho
            'KPI_KT_08': actuals.get('Missing_Invoice_Receipts', 0),
            'KPI_KT_09': actuals.get('Avg_Order_Process_Hours', 0),  # [NEW] Tốc độ lệnh
            'KPI_KT_10': actuals.get('Invoice_DelayCount', 0),
            'KPI_KT_11': actuals.get('Invoice_CancelCount', 0),
            'KPI_KT_12': actuals.get('Cash_Flow_Velocity_Days', 0),  # Dùng chung logic dòng tiền
            
            # --- KHO (ĐÃ CẬP NHẬT FULL) ---
            'KPI_KH_01': actuals.get('OTIF_Rate', 0),
            'KPI_KH_02': actuals.get('Loss_Value', 0),               # [NEW] Hàng mất (Triệu)
            'KPI_KH_03': actuals.get('Warehouse_Budget_Over_Pct', 0),# [NEW] Ngân sách kho
            'KPI_KH_04': actuals.get('Total_Lines_Picked', 0),
            'KPI_KH_05': actuals.get('Avg_Picking_Hours', 0),
            'KPI_KH_06': 100, # Hardcode tạm thời
            'KPI_KH_07': actuals.get('Total_Lines_Putaway', 0),
            'KPI_KH_08': actuals.get('Avg_Picking_Hours', 0),        # Mượn tạm logic
            'KPI_KH_09': actuals.get('OTIF_Rate', 0),

            # --- HỆ THỐNG ---
            'KPI_SYS_01': actuals.get('CRM_Report_Count', 0),
            'KPI_SYS_02': actuals.get('Task_Completion_Rate', 0),
            'KPI_SYS_03': actuals.get('Gamification_XP', 0)
        }
        return mapping.get(criteria_id, 0) # Nếu không tìm thấy, trả về 0 (Manual)

    def calculate_bucket_score(self, actual, is_higher_better, t100, t85, t70, t50, t30, t0):
        """Dò con số thực tế vào các khung điểm để chấm điểm KPI."""
        if is_higher_better:
            if actual >= t100: return 100
            elif actual >= t85: return 85
            elif actual >= t70: return 70
            elif actual >= t50: return 50
            elif actual >= t30: return 30
            else: return 0
        else: # Càng thấp càng tốt (ví dụ: Lỗi, Đi trễ, Giao trễ)
            if actual <= t100: return 100
            elif actual <= t85: return 85
            elif actual <= t70: return 70
            elif actual <= t50: return 50
            elif actual <= t30: return 30
            else: return 0

    
    def evaluate_monthly_kpi(self, user_code, year, month):
        """Hàm CHÍNH: Lấy Cấu hình -> Quét Thực tế -> Chấm điểm -> Lưu DB"""
        
        # 1. Lấy Profile KPI
        query_profile = """
            SELECT P.*, C.CriteriaName, C.CalculationType, C.IsHigherBetter
            FROM dbo.KPI_USER_PROFILE P
            INNER JOIN dbo.KPI_CRITERIA_MASTER C ON P.CriteriaID = C.CriteriaID
            WHERE P.UserCode = ? AND P.IsActive = 1
        """
        profiles = self.db.get_data(query_profile, (user_code,))
        if not profiles:
            return {"success": False, "message": f"Không tìm thấy cấu hình KPI cho {user_code}"}

        # 2. Xóa các chỉ số TỰ ĐỘNG cũ, GIỮ LẠI chỉ số THỦ CÔNG (MANUAL)
        delete_query = """
            DELETE FROM dbo.KPI_MONTHLY_RESULT 
            WHERE UserCode = ? AND EvalYear = ? AND EvalMonth = ?
            AND CriteriaID IN (SELECT CriteriaID FROM dbo.KPI_CRITERIA_MASTER WHERE CalculationType != 'MANUAL')
        """
        self.db.execute_non_query(delete_query, (user_code, year, month))

        # 3. Lấy dữ liệu thực tế từ ERP
        actuals_dict = self.fetch_all_actuals(year, month, user_code)

        insert_query = """
            INSERT INTO dbo.KPI_MONTHLY_RESULT 
            (UserCode, EvalYear, EvalMonth, CriteriaID, ActualValue, RawScore, WeightedScore)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        
        total_score = 0
        conn = self.db.get_transaction_connection()
        cursor = conn.cursor()
        
        try:
            for p in profiles:
                crit_id = p['CriteriaID']
                weight = safe_float(p['Weight'])
                is_higher_better = bool(p['IsHigherBetter'])
                calc_type = p['CalculationType']
                
                # --- [FIX LOGIC MANUAL] QUAN TRỌNG ---
                if calc_type == 'MANUAL':
                    # Kiểm tra xem tiêu chí này đã có điểm trong DB chưa
                    existing_score_query = "SELECT WeightedScore FROM dbo.KPI_MONTHLY_RESULT WHERE UserCode=? AND CriteriaID=? AND EvalYear=? AND EvalMonth=?"
                    cursor.execute(existing_score_query, (user_code, crit_id, year, month))
                    row = cursor.fetchone()
                    
                    if row:
                        # Nếu ĐÃ CÓ (đã chấm trước đó), cộng điểm vào tổng
                        total_score += safe_float(row[0])
                    else:
                        # Nếu CHƯA CÓ, tạo dòng dữ liệu giữ chỗ (Placeholder) với điểm = 0
                        # Để Dashboard có thể hiển thị tiêu chí này ra màn hình
                        cursor.execute(insert_query, (user_code, year, month, crit_id, 0, 0, 0))
                    
                    continue # Bỏ qua phần tính toán tự động bên dưới

                # --- TÍNH TOÁN TIÊU CHÍ TỰ ĐỘNG (AUTO) ---
                actual_val = self.get_actual_value_for_criteria(crit_id, actuals_dict)
                raw_score = self.calculate_bucket_score(
                    actual_val, is_higher_better,
                    safe_float(p['Threshold_100']), safe_float(p['Threshold_85']),
                    safe_float(p['Threshold_70']), safe_float(p['Threshold_50']),
                    safe_float(p['Threshold_30']), safe_float(p['Threshold_0'])
                )
                
                weighted_score = raw_score * weight
                total_score += weighted_score

                cursor.execute(insert_query, (
                    user_code, year, month, crit_id, 
                    actual_val, raw_score, weighted_score
                ))

            # =========================================================================
            # TÍNH TOÁN KPI_SYS_04: ĐIỂM TRUNG BÌNH CỦA NHÂN VIÊN CẤP DƯỚI
            # =========================================================================
            try:
                # 1. Tìm các nhân viên mà User này là cấp trên
                cursor.execute("SELECT USERCODE FROM [dbo].[GD - NGUOI DUNG] WHERE [CAP TREN] = ?", (user_code,))
                subordinates = cursor.fetchall()
                
                if subordinates:
                    sub_codes = [s[0] for s in subordinates] # Lấy cột đầu tiên
                    if sub_codes:
                        placeholders = ','.join(['?'] * len(sub_codes))
                        # Lấy tổng điểm KPI của nhân viên
                        query_scores = f"""
                            SELECT SUM(WeightedScore) 
                            FROM dbo.KPI_MONTHLY_RESULT 
                            WHERE EvalYear=? AND EvalMonth=? AND UserCode IN ({placeholders})
                            GROUP BY UserCode
                        """
                        params = [year, month] + sub_codes
                        cursor.execute(query_scores, tuple(params))
                        scores_data = cursor.fetchall()
                        
                        if scores_data:
                            # Tính trung bình cộng điểm của các nhân viên có dữ liệu
                            list_scores = [float(x[0]) for x in scores_data if x[0] is not None]
                            if list_scores:
                                avg_score = sum(list_scores) / len(list_scores)
                                
                                # Lấy trọng số của KPI_SYS_04 cho Sếp
                                cursor.execute("SELECT Weight FROM dbo.KPI_USER_PROFILE WHERE UserCode=? AND CriteriaID='KPI_SYS_04' AND IsActive=1", (user_code,))
                                sys04_profile = cursor.fetchone()
                                
                                if sys04_profile:
                                    weight_04 = float(sys04_profile[0])
                                    weighted_score_04 = avg_score * weight_04
                                    
                                    # Upsert vào bảng kết quả (Update nếu có, Insert nếu chưa)
                                    cursor.execute("SELECT ResultID FROM dbo.KPI_MONTHLY_RESULT WHERE UserCode=? AND CriteriaID='KPI_SYS_04' AND EvalYear=? AND EvalMonth=?", (user_code, year, month))
                                    check_exist = cursor.fetchone()
                                    
                                    if check_exist:
                                        cursor.execute("UPDATE dbo.KPI_MONTHLY_RESULT SET ActualValue=?, RawScore=?, WeightedScore=? WHERE ResultID=?", (avg_score, avg_score, weighted_score_04, check_exist[0]))
                                    else:
                                        cursor.execute("INSERT INTO dbo.KPI_MONTHLY_RESULT (UserCode, EvalYear, EvalMonth, CriteriaID, ActualValue, RawScore, WeightedScore) VALUES (?, ?, ?, 'KPI_SYS_04', ?, ?, ?)", (user_code, year, month, avg_score, avg_score, weighted_score_04))
                                    
                                    total_score += weighted_score_04

            except Exception as e_sub:
                print(f"⚠️ Lỗi tính điểm cấp dưới (KPI_SYS_04): {e_sub}")

            conn.commit()
            return {"success": True, "total_score": round(total_score, 2), "message": "Đã quét ERP & chốt KPI thành công."}

        except Exception as e:
            conn.rollback()
            return {"success": False, "message": str(e)}
        finally:
            conn.close()

    def get_kpi_results_for_view(self, user_code, year, month):
        """Lấy dữ liệu hiển thị lên Dashboard KPI của nhân viên"""
        """Lấy dữ liệu hiển thị lên Dashboard KPI của nhân viên"""
        query = """
            SELECT 
                R.ResultID, R.CriteriaID, C.CriteriaName, C.CalculationType,
                C.Unit, -- ĐÃ BỔ SUNG CỘT UNIT TỪ MASTER
                P.Weight, R.ActualValue, R.RawScore, R.WeightedScore,
                P.Threshold_100, P.Threshold_85, P.Threshold_70,
                P.Threshold_50, P.Threshold_30, P.Threshold_0,
                C.IsHigherBetter
            FROM dbo.KPI_MONTHLY_RESULT R
            INNER JOIN dbo.KPI_CRITERIA_MASTER C ON R.CriteriaID = C.CriteriaID
            INNER JOIN dbo.KPI_USER_PROFILE P ON R.CriteriaID = P.CriteriaID AND R.UserCode = P.UserCode
            WHERE R.UserCode = ? AND R.EvalYear = ? AND R.EvalMonth = ?
            ORDER BY P.Weight DESC
        """
        return self.db.get_data(query, (user_code, year, month))

    # =========================================================================
    # CÁC HÀM HỖ TRỢ CHẤM ĐIỂM THỦ CÔNG & ĐÁNH GIÁ CHÉO
    # =========================================================================

    def get_manual_criteria_for_evaluation(self, target_user, year, month):
        """Lấy danh sách các Tiêu chí Cần chấm tay của 1 User (kèm điểm đã chấm nếu có)"""
        query = """
            SELECT 
                P.CriteriaID, C.CriteriaName, P.Weight, P.Threshold_100, P.Threshold_0, C.IsHigherBetter,
                ISNULL(R.ActualValue, '') AS CurrentActualValue,
                R.EvaluatorCode, R.Note
            FROM dbo.KPI_USER_PROFILE P
            INNER JOIN dbo.KPI_CRITERIA_MASTER C ON P.CriteriaID = C.CriteriaID
            LEFT JOIN dbo.KPI_MONTHLY_RESULT R ON P.CriteriaID = R.CriteriaID AND R.UserCode = P.UserCode AND R.EvalYear = ? AND R.EvalMonth = ?
            WHERE P.UserCode = ? AND C.CalculationType = 'MANUAL' AND P.IsActive = 1
        """
        return self.db.get_data(query, (year, month, target_user))

    def save_manual_evaluations(self, target_user, year, month, scores_data, evaluator_code):
        """Lưu điểm chấm tay từ Form vào Database"""
        # Lấy thông tin cấu hình để nội suy điểm
        check_exist = "SELECT ResultID FROM dbo.KPI_MONTHLY_RESULT WHERE UserCode=? AND EvalYear=? AND EvalMonth=? AND CriteriaID=?"
        insert_sql = """INSERT INTO dbo.KPI_MONTHLY_RESULT (UserCode, EvalYear, EvalMonth, CriteriaID, ActualValue, RawScore, WeightedScore, EvaluatorCode, Note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        update_sql = """UPDATE dbo.KPI_MONTHLY_RESULT SET ActualValue=?, RawScore=?, WeightedScore=?, EvaluatorCode=?, Note=?, CreatedAt=GETDATE() WHERE UserCode=? AND EvalYear=? AND EvalMonth=? AND CriteriaID=?"""

        for item in scores_data:
            crit_id = item['criteria_id']
            actual_val = safe_float(item['actual_value'])
            note = item.get('note', '')

            # Lấy Profile để tính điểm
            profile = self.db.get_data("SELECT * FROM dbo.KPI_USER_PROFILE WHERE UserCode = ? AND CriteriaID = ?", (target_user, crit_id))
            if not profile: continue
            p = profile[0]
            
            master = self.db.get_data("SELECT IsHigherBetter FROM dbo.KPI_CRITERIA_MASTER WHERE CriteriaID=?", (crit_id,))
            is_higher = bool(master[0]['IsHigherBetter']) if master else True

            # Quy đổi điểm (dò vào Threshold)
            raw_score = self.calculate_bucket_score(
                actual_val, is_higher,
                safe_float(p['Threshold_100']), safe_float(p['Threshold_85']),
                safe_float(p['Threshold_70']), safe_float(p['Threshold_50']),
                safe_float(p['Threshold_30']), safe_float(p['Threshold_0'])
            )
            weighted_score = raw_score * safe_float(p['Weight'])

            # Lưu DB
            existing = self.db.get_data(check_exist, (target_user, year, month, crit_id))
            if existing:
                self.db.execute_non_query(update_sql, (actual_val, raw_score, weighted_score, evaluator_code, note, target_user, year, month, crit_id))
            else:
                self.db.execute_non_query(insert_sql, (target_user, year, month, crit_id, actual_val, raw_score, weighted_score, evaluator_code, note))

        return {"success": True, "message": "Đã lưu kết quả đánh giá thủ công."}

    def save_peer_review(self, target_user, evaluator_user, year, month, score, note):
        """Lưu một phiếu đánh giá chéo của 1 người"""
        # [FIX] Cắt khoảng trắng thừa
        target = str(target_user).strip()
        evaluator = str(evaluator_user).strip()

        check_query = """
            SELECT ReviewID FROM dbo.KPI_PEER_REVIEW 
            WHERE TargetUser=? AND EvaluatorUser=? AND EvalYear=? AND EvalMonth=?
        """
        existing = self.db.get_data(check_query, (target, evaluator, year, month))
        
        if existing:
            update_sql = "UPDATE dbo.KPI_PEER_REVIEW SET Score=?, Note=?, CreatedAt=GETDATE() WHERE ReviewID=?"
            self.db.execute_non_query(update_sql, (score, note, existing[0]['ReviewID']))
        else:
            insert_sql = "INSERT INTO dbo.KPI_PEER_REVIEW (TargetUser, EvaluatorUser, EvalYear, EvalMonth, Score, Note) VALUES (?, ?, ?, ?, ?, ?)"
            self.db.execute_non_query(insert_sql, (target, evaluator, year, month, score, note))

        # Sau khi lưu phiếu, tự động tính lại ĐIỂM TỔNG môn Đánh giá chéo (KPI_MAN_01)
        self._calculate_and_update_final_peer_score(target, year, month)
        return {"success": True, "message": "Đã ghi nhận đánh giá thành công!"}

    
    def _calculate_and_update_final_peer_score(self, target_user, year, month):
        """Thuật toán: Sếp trực tiếp 40%, Đồng nghiệp 60% (Trung bình). Nếu <3 đồng nghiệp -> Max phần ĐN = 4đ"""
        target = str(target_user).strip()
        
        reviews = self.db.get_data("SELECT EvaluatorUser, Score FROM dbo.KPI_PEER_REVIEW WHERE TargetUser=? AND EvalYear=? AND EvalMonth=?", (target, year, month))
        if not reviews: return

        # Xác định Cấp trên trực tiếp của người bị chấm
        query_manager = "SELECT [CAP TREN] FROM [dbo].[GD - NGUOI DUNG] WHERE LTRIM(RTRIM(USERCODE)) = ?"
        manager_data = self.db.get_data(query_manager, (target,))
        direct_manager = str(manager_data[0]['CAP TREN']).strip().upper() if manager_data and manager_data[0]['CAP TREN'] else ''

        manager_score = 0
        peer_scores = []

        for r in reviews:
            eval_user = str(r['EvaluatorUser']).strip().upper()
            score = safe_float(r['Score'])
            
            # So khớp ai là Sếp trực tiếp
            if eval_user == direct_manager: 
                manager_score = score
            else: 
                peer_scores.append(score)

        # Tính toán
        s_manager = manager_score * 0.4 if manager_score > 0 else 0
        
        s_peers = 0
        if len(peer_scores) > 0:
            avg_peer = sum(peer_scores) / len(peer_scores)
            s_peers = avg_peer * 0.6
            # Ràng buộc: < 3 người chấm thì điểm phần đồng nghiệp max = 4
            if len(peer_scores) < 3 and s_peers > 4:
                s_peers = 4

        final_score = s_manager + s_peers

        # Lưu điểm tổng
        profile = self.db.get_data("SELECT Weight FROM dbo.KPI_USER_PROFILE WHERE LTRIM(RTRIM(UserCode))=? AND CriteriaID='KPI_MAN_01' AND IsActive=1", (target,))
        if profile:
            weight = safe_float(profile[0]['Weight'])
            # Mức điểm hiện tại là thang 10. Chuyển sang hệ 100 để đồng bộ với các tiêu chí khác
            raw_score_100 = final_score * 10 
            weighted_score = raw_score_100 * weight 
            
            check_res = self.db.get_data("SELECT ResultID FROM dbo.KPI_MONTHLY_RESULT WHERE LTRIM(RTRIM(UserCode))=? AND EvalYear=? AND EvalMonth=? AND CriteriaID='KPI_MAN_01'", (target, year, month))
            
            if check_res:
                self.db.execute_non_query("UPDATE dbo.KPI_MONTHLY_RESULT SET ActualValue=?, RawScore=?, WeightedScore=? WHERE ResultID=?", (final_score, raw_score_100, weighted_score, check_res[0]['ResultID']))
            else:
                self.db.execute_non_query("INSERT INTO dbo.KPI_MONTHLY_RESULT (UserCode, EvalYear, EvalMonth, CriteriaID, ActualValue, RawScore, WeightedScore) VALUES (?, ?, ?, 'KPI_MAN_01', ?, ?, ?)", (target, year, month, final_score, raw_score_100, weighted_score))

    # Hàm hỗ trợ gộp dòng (Để ngoài hoặc làm method riêng)
    def _aggregate_rows(self, data, sum_fields, label_field):
        if not data or len(data) <= 50:
            return data
        
        top_data = data[:49]
        other_data = data[49:]
        
        other_row = {k: "---" for k in data[0].keys()}
        other_row[label_field] = f"Khác (Gộp {len(other_data)} dòng)"
        
        for field in sum_fields:
            other_row[field] = sum([safe_float(r.get(field, 0)) for r in other_data])
        
        top_data.append(other_row)
        return top_data

    def get_criteria_detail(self, criteria_id, user_code, year, month):
        """
        [STRATEGY PATTERN ROUTER]
        Định tuyến yêu cầu Drill-down tới các Master SP trong SQL.
        Tự động gán Cấu trúc Cột và Tính toán Summary.
        """
        result = {"columns": [], "rows": [], "summary": ""}

        # =================================================================
        # 1. BẢN ĐỒ ĐỊNH TUYẾN (ROUTING MAP)
        # Bất cứ khi nào có KPI mới, chỉ cần thêm 1 Block vào Dictionary này
        # =================================================================
        route_map = {
            'KPI_KD_01': {
                'sp': 'sp_KPI_GetDetail_Sales',
                'columns': [
                    {"field": "KhachHang", "label": "Tên Khách Hàng"},
                    {"field": "SoLuongHD", "label": "Số Lượng HĐ", "type": "number"},
                    {"field": "DoanhSo", "label": "Tổng Doanh Số (VNĐ)", "type": "currency"}
                ],
                'sum_fields': ['DoanhSo', 'SoLuongHD'],
                'label_field': 'KhachHang'
            },
            'KPI_KD_02': {
                'sp': 'sp_KPI_GetDetail_Sales',
                'columns': [
                    {"field": "KhachHang", "label": "Khách Hàng Mới / Win-back"},
                    {"field": "SoLuongHD", "label": "Số Lượng HĐ", "type": "number"},
                    {"field": "DoanhSo", "label": "Doanh Số (VNĐ)", "type": "currency"}
                ],
                'sum_fields': ['DoanhSo', 'SoLuongHD'],
                'label_field': 'KhachHang'
            },
            # [FIX CẤU TRÚC] Map với SP mới cập nhật, xóa cột đếm Hóa Đơn
            'KPI_KD_03': {
                'sp': 'sp_KPI_GetDetail_Sales',
                'columns': [
                    {"field": "KhachHang", "label": "Khách Hàng Đang Nợ"},
                    {"field": "TongNo", "label": "Tổng Dư Nợ (VNĐ)", "type": "currency"},
                    {"field": "NoQuaHan", "label": "Nợ Quá Hạn (VNĐ)", "type": "currency"}
                ],
                'sum_fields': ['TongNo', 'NoQuaHan'],
                'label_field': 'KhachHang'
            },
            'KPI_TK_01': {
                'sp': 'sp_KPI_GetDetail_Admin',
                'columns': [
                    {"field": "SalesChinh", "label": "Sales Phụ Trách"},
                    {"field": "KhachHang", "label": "Khách Hàng Hỗ Trợ"},
                    {"field": "SoLuongHD", "label": "Số Lượng HĐ", "type": "number"},
                    {"field": "DoanhSo", "label": "Doanh Số Hỗ Trợ (VNĐ)", "type": "currency"}
                ],
                'sum_fields': ['DoanhSo', 'SoLuongHD'],
                'label_field': 'KhachHang'
            },

            'KPI_TK_03': {
                'sp': 'sp_KPI_GetDetail_Admin',
                'columns': [
                    {"field": "SoDonHang", "label": "Số Đơn Hàng"},
                    {"field": "KhachHang", "label": "Khách Hàng"},
                    {"field": "NgayYeuCau", "label": "Ngày Yêu Cầu"},
                    {"field": "NgayThucXuat", "label": "Thực Xuất Kho"},
                    {"field": "SoNgayTre", "label": "Trễ (Ngày)", "type": "number"}
                ],
                'sum_fields': ['SoNgayTre'],
                'label_field': 'KhachHang'
            },
            'KPI_TK_04': {
                'sp': 'sp_KPI_GetDetail_Admin',
                'columns': [
                    {"field": "SoBaoGia", "label": "Số Báo Giá"},
                    {"field": "KhachHang", "label": "Khách Hàng"},
                    {"field": "GiaTri", "label": "Giá Trị (VNĐ)", "type": "currency"},
                    {"field": "TrangThai", "label": "Trạng Thái Báo Giá"}
                ],
                'sum_fields': ['GiaTri'],
                'label_field': 'KhachHang'
            },
            'KPI_SYS_01': {
                'sp': 'sp_KPI_GetDetail_System',
                'columns': [
                    {"field": "NgayNop", "label": "Ngày Nộp"},
                    {"field": "KhachHang", "label": "Khách Hàng Tương Tác"},
                    {"field": "NoiDung", "label": "Nội Dung Báo Cáo"}
                ],
                'sum_fields': [],
                'label_field': 'NoiDung'
            },
            'KPI_SYS_02': {
                'sp': 'sp_KPI_GetDetail_System',
                'columns': [
                    {"field": "NgayTask", "label": "Ngày Phân Công"},
                    {"field": "LoaiTask", "label": "Phân Loại Nhiệm Vụ"},
                    {"field": "TenTask", "label": "Nội Dung Công Việc"},
                    {"field": "TrangThai", "label": "Trạng Thái"}
                ],
                'sum_fields': [],
                'label_field': 'TenTask'
            },
            # --- CHI TIẾT KẾ TOÁN ---
            'KPI_KT_01': {
                'sp': 'sp_KPI_GetDetail_Acc',
                'columns': [
                    {"field": "SoChungTu", "label": "Số CT"},
                    {"field": "LoaiPhieu", "label": "Loại"},
                    {"field": "NgayHT", "label": "Ngày Hạch Toán"},
                    {"field": "DoiTuong", "label": "Đối Tượng"},
                    {"field": "SoTien", "label": "Số Tiền (VNĐ)", "type": "currency"}
                ],
                'sum_fields': ['SoTien'],
                'label_field': 'DoiTuong'
            },
            'KPI_KT_02': {
                'sp': 'sp_KPI_GetDetail_Acc',
                'columns': [
                    {"field": "MaKH", "label": "Mã KH"},
                    {"field": "KhachHang", "label": "Tên Khách Hàng"},
                    {"field": "NVKD", "label": "Sales Phụ Trách"},
                    {"field": "TongNo", "label": "Tổng Dư Nợ", "type": "currency"},
                    {"field": "NoQuaHan", "label": "Nợ Quá Hạn", "type": "currency"}
                ],
                'sum_fields': ['NoQuaHan', 'TongNo'],
                'label_field': 'KhachHang'
            },
            
            # --- CHI TIẾT KHO VẬN ---
            'KPI_KHO_01': {
                'sp': 'sp_KPI_GetDetail_Whs',
                'columns': [
                    {"field": "SoPhieu", "label": "Số Phiếu Nhập"},
                    {"field": "NgayLap", "label": "Ngày Nhập"},
                    {"field": "DoiTuong", "label": "Đối Tượng / NCC"},
                    {"field": "DienGiai", "label": "Diễn Giải"}
                ],
                'sum_fields': [],
                'label_field': 'DoiTuong'
            },
            'KPI_KHO_02': {
                'sp': 'sp_KPI_GetDetail_Whs',
                'columns': [
                    {"field": "SoPhieu", "label": "Số Phiếu Xuất"},
                    {"field": "LoaiPhieu", "label": "Loại"},
                    {"field": "NgayLap", "label": "Ngày Xuất"},
                    {"field": "DoiTuong", "label": "Khách Hàng / Đối Tượng"}
                ],
                'sum_fields': [],
                'label_field': 'DoiTuong'
            },
            'KPI_KHO_03': {
                'sp': 'sp_KPI_GetDetail_Whs',
                'columns': [
                    {"field": "SoPhieuXuat", "label": "Số PX/XK"},
                    {"field": "SoDonHang", "label": "Mã Đơn Hàng (SO)"},
                    {"field": "KhachHang", "label": "Khách Hàng"},
                    {"field": "NgayYeuCau", "label": "Ngày Yêu Cầu"},
                    {"field": "NgayThucXuat", "label": "Ngày Thực Xuất"},
                    {"field": "SoNgayTre", "label": "Trễ (Ngày)", "type": "number"}
                ],
                'sum_fields': ['SoNgayTre'],
                'label_field': 'KhachHang'
            }   
        }

        # Kiểm tra xem tiêu chí có được hỗ trợ Drill-down chưa
        route = route_map.get(criteria_id)
        if not route:
            result['summary'] = "<i>Hệ thống đang cập nhật cấu trúc Drill-down Level 1 cho tiêu chí này.</i>"
            return result

        # =================================================================
        # 2. THỰC THI GỌI SQL THEO ĐỊNH TUYẾN
        # =================================================================
        query = f"EXEC {route['sp']} ?, ?, ?, ?"
        data = self.db.get_data(query, (criteria_id, user_code, year, month))
        
        if not data:
            result['summary'] = "Chưa có dữ liệu phát sinh trong tháng."
            return result

        # =================================================================
        # 3. GỘP DÒNG VÀ ĐÓNG GÓI JSON
        # =================================================================
        result['columns'] = route['columns']
        result['rows'] = self._aggregate_rows(data, route['sum_fields'], route['label_field'])

        # =================================================================
        # 4. TẠO CHUỖI SUMMARY ĐỘNG
        # =================================================================
        # =================================================================
        # 4. TẠO CHUỖI SUMMARY ĐỘNG (ĐÃ FIX LỖI INDEX)
        # =================================================================
        total_actual = 0
        # Kiểm tra xem tiêu chí có cột nào cần tính tổng không (Task/CRM thì không có)
        if route.get('sum_fields') and len(route['sum_fields']) > 0:
            main_sum_field = route['sum_fields'][0]
            total_actual = sum([safe_float(r.get(main_sum_field, 0)) for r in data])

        if criteria_id == 'KPI_KD_01':
            target = self._get_targets(user_code, year).get('sales_month', 0)
            result['summary'] = f"<b>Thực tế:</b> {total_actual:,.0f} đ / <b>Chỉ tiêu:</b> {target:,.0f} đ"
            
        elif criteria_id == 'KPI_TK_01':
            target = self._get_targets(user_code, year).get('admin_month', 0)
            result['summary'] = f"<b>Thực hỗ trợ:</b> {total_actual:,.0f} đ / <b>Chỉ tiêu:</b> {target:,.0f} đ"
            
        elif criteria_id == 'KPI_KD_02':
            result['summary'] = f"<b>Tổng doanh số mang về từ KH Mới:</b> <span class='text-success'>{total_actual:,.0f} đ</span>"
            
        elif criteria_id == 'KPI_KD_03':
            total_overdue = sum([safe_float(r.get('NoQuaHan', 0)) for r in data])
            pct = (total_overdue / total_actual * 100) if total_actual > 0 else 0
            color = "text-danger" if pct > 15 else "text-warning"
            result['summary'] = f"<b>Tổng Nợ:</b> {total_actual:,.0f} đ | <b>Quá hạn:</b> <span class='{color}'>{total_overdue:,.0f} đ ({pct:.1f}%)</span>"
            
        elif criteria_id == 'KPI_TK_02':
            result['summary'] = f"<b>Tổng doanh số chốt đơn Văn Phòng:</b> <span class='text-primary'>{total_actual:,.0f} đ</span>"
            
        elif criteria_id == 'KPI_TK_03':
            so_don_tre = len(data) if data else 0
            result['summary'] = f"<b>Số lượng đơn hàng giao trễ so với cam kết:</b> <span class='text-danger'>{so_don_tre} đơn</span>"
            
        elif criteria_id == 'KPI_TK_04':
            win_count = sum(1 for r in data if r.get('TrangThai') == 'WIN')
            total_closed = len(data) if data else 0
            rate = (win_count / total_closed * 100) if total_closed > 0 else 0
            result['summary'] = f"<b>Tỷ lệ chốt deal (Win-rate):</b> <span class='text-primary'>{rate:.1f}%</span> ({win_count} Win / {total_closed} Báo giá)"
            
        elif criteria_id == 'KPI_SYS_01':
            result['summary'] = f"<b>Tổng số Báo cáo CRM trong tháng:</b> <span class='text-success'>{len(data)} báo cáo</span>"
            
        elif criteria_id == 'KPI_SYS_02':
            assigned = sum(1 for r in data if '70%' in r.get('LoaiTask', ''))
            self_task = sum(1 for r in data if '30%' in r.get('LoaiTask', ''))
            result['summary'] = f"<b>Thống kê Task:</b> {assigned} Task Giao | {self_task} Task Tự lên KH"
        elif criteria_id == 'KPI_KT_01':
            result['summary'] = f"<b>Năng suất:</b> Kế toán đã xử lý <span class='text-primary'>{len(data)} chứng từ</span> Thu/Chi."
        elif criteria_id == 'KPI_KT_02':
            result['summary'] = f"<b>Cảnh báo:</b> Danh sách TOP 100 khách hàng tồn đọng Nợ Quá Hạn lớn nhất toàn Công ty."
        elif criteria_id == 'KPI_KHO_01':
            result['summary'] = f"<b>Năng suất:</b> Đã lập <span class='text-primary'>{len(data)} phiếu Nhập Kho</span> trong tháng."
        elif criteria_id == 'KPI_KHO_02':
            result['summary'] = f"<b>Năng suất:</b> Đã lập <span class='text-success'>{len(data)} phiếu Xuất Kho</span> trong tháng."
        elif criteria_id == 'KPI_KHO_03':
            result['summary'] = f"<b>Vi phạm Leadtime:</b> Có <span class='text-danger'>{len(data)} phiếu xuất kho</span> trễ hẹn > 3 ngày."
        return result            


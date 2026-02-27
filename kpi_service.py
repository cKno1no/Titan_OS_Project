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
        Đã đồng bộ hóa tên field với SP Kế toán mới nhất.
        """
        actuals = {}
        
        # --- 1. LẤY DATA KINH DOANH & THƯ KÝ ---
        sales_data = self.db.execute_sp_multi('sp_KPI_Sales_GetMetrics', (year, month, user_code))
        if sales_data and sales_data[0]:
            sd = sales_data[0][0]
            targets = self._get_targets(user_code, year)
            actuals['Revenue_Salesman_Pct'] = (safe_float(sd.get('Actual_Sales_Total', 0)) / targets['sales_month']) * 100 if targets['sales_month'] > 0 else 0
            actuals['Revenue_NewCust_Mil'] = safe_float(sd.get('Actual_Sales_NewCust', 0)) / 1000000.0
            actuals['AR_Overdue_Rate_Sales'] = safe_float(sd.get('AR_Overdue_Rate', 0))
            actuals['Revenue_Employee_Pct'] = (safe_float(sd.get('Actual_Support_Sales', 0)) / targets['admin_month']) * 100 if targets['admin_month'] > 0 else 0
            actuals['Revenue_Office_Mil'] = safe_float(sd.get('Actual_Office_Sales', 0)) / 1000000.0
            actuals['Late_Delivery_Admin'] = safe_float(sd.get('Late_Delivery_Admin', 0))
            actuals['Quote_WinRate'] = safe_float(sd.get('Quote_WinRate', 0))

        # --- 2. LẤY DATA KẾ TOÁN (Đồng bộ theo SP sp_KPI_Acc_GetMetrics) ---
        acc_data = self.db.execute_sp_multi('sp_KPI_Acc_GetMetrics', (year, month, user_code))
        if acc_data and acc_data[0]:
            ad = acc_data[0][0]
            # Lấy role để biết đường mapping ở hàm sau
            actuals['detected_role'] = ad.get('KPIRole')

            # Hứng toàn bộ các cột có thể có từ SP Kế toán vào dict actuals
            actuals['Invoice_Latency_Hours'] = safe_float(ad.get('Invoice_Latency_Hours', 0))
            actuals['Pending_Invoice_Rate'] = safe_float(ad.get('Pending_Invoice_Rate', 0))
            actuals['Order_Process_Latency'] = safe_float(ad.get('Order_Process_Latency', 0))
            actuals['Negative_Stock_Errors'] = safe_float(ad.get('Negative_Stock_Errors', 0))
            actuals['Payment_SLA_Hours'] = safe_float(ad.get('Payment_SLA_Hours', 0))
            actuals['Overdue_Debt_Rate'] = safe_float(ad.get('Overdue_Debt_Rate', 0))
            actuals['Late_Expense_Count'] = safe_float(ad.get('Late_Expense_Count', 0))
            actuals['Admin_Approval_SLA'] = safe_float(ad.get('Admin_Approval_SLA', 0))

        # --- 3. LẤY DATA KHO ---
        whs_data = self.db.execute_sp_multi('sp_KPI_Whs_GetMetrics', (year, month, user_code))
        if whs_data and whs_data[0]:
            wd = whs_data[0][0]
            actuals['OTIF_Rate'] = safe_float(wd.get('OTIF_Rate', 0))
            actuals['Avg_Picking_Hours'] = safe_float(wd.get('Avg_Picking_Hours', 0))
            actuals['Total_Lines_Picked'] = safe_float(wd.get('Total_Lines_Picked', 0))
            actuals['Total_Lines_Putaway'] = safe_float(wd.get('Total_Lines_Putaway', 0))
            actuals['Delay_Docs_Count'] = safe_float(wd.get('Delay_Docs_Count', 0))
            actuals['Loss_Value'] = safe_float(wd.get('Loss_Value', 0)) / 1000000.0
            actuals['Warehouse_Budget_Over_Pct'] = safe_float(wd.get('Warehouse_Budget_Over_Pct', 0))

        # --- 4. LẤY DATA HỆ THỐNG TITAN ---
        sys_data = self.db.execute_sp_multi('sp_KPI_Sys_GetMetrics', (year, month, user_code))
        if sys_data and sys_data[0]:
            syd = sys_data[0][0]
            actuals['CRM_Report_Count'] = safe_float(syd.get('CRM_Report_Count', 0))
            actuals['Task_Completion_Rate'] = safe_float(syd.get('Task_Completion_Rate', 0))
            actuals['Approval_SLA_Hours'] = safe_float(syd.get('Approval_SLA_Hours', 0))
            actuals['Gamification_XP'] = safe_float(syd.get('Gamification_XP', 0))

        # Tích hợp đánh giá chéo
        actuals['Peer_Review_Score'] = safe_float(self._calculate_and_update_final_peer_score(user_code, year, month))

        return actuals
    
    def get_actual_value_for_criteria(self, criteria_id, actuals):
        """
        Map ID Tiêu chí với trường dữ liệu thực tế.
        Sử dụng tên nghiệp vụ trực tiếp thay vì acc_m1, acc_m2.
        """
        role = actuals.get('detected_role')
        
        # 1. LOGIC MAPPING RIÊNG CHO KHỐI KẾ TOÁN (Dựa trên Role và ID chuẩn KPI_2026)
        if criteria_id.startswith('KPI_KT_'):
            if role == 'ACC_SALES': # Thanh Diệu (KD006)
                if criteria_id == 'KPI_KT_DIEU_01': return actuals.get('Invoice_Latency_Hours', 0)
                if criteria_id == 'KPI_KT_DIEU_03': return actuals.get('Pending_Invoice_Rate', 0)
                if criteria_id == 'KPI_KT_DIEU_04': return actuals.get('Invoice_Error_Rate', 0) # Cần bổ sung SP nếu muốn chạy
            
            elif role == 'ACC_WAREHOUSE': # Tú Anh (KD007)
                if criteria_id == 'KPI_KT_KHO_01': return actuals.get('Inventory_Accuracy', 0)
                if criteria_id == 'KPI_KT_KHO_02': return actuals.get('Order_Process_Latency', 0)
                if criteria_id == 'KPI_KT_KHO_03': return actuals.get('Negative_Stock_Errors', 0)
            
            elif role == 'ACC_PAYMENT': # Thanh Bình (KT004)
                if criteria_id == 'KPI_KT_BINH_01': return actuals.get('Payment_SLA_Hours', 0)
                if criteria_id == 'KPI_KT_BINH_02': return actuals.get('Overdue_Debt_Rate', 0)
                if criteria_id == 'KPI_KT_BINH_03': return actuals.get('Reconciliation_Latency', 0)
            
            elif role == 'ACC_TAX': # Anh Thư (KD066)
                if criteria_id == 'KPI_KT_THU_01': return actuals.get('Tax_Report_Deadline_Status', 0)
                if criteria_id == 'KPI_KT_THU_02': return actuals.get('Invoice_Audit_Rate', 0)
                if criteria_id == 'KPI_KT_THU_04': return actuals.get('Late_Expense_Count', 0)
            
            elif role == 'ACC_CHIEF': # Quốc Nguyễn (KT007)
                if criteria_id == 'KPI_KT_KTT_01': return actuals.get('Chief_Report_Deadline_Status', 0)
                if criteria_id == 'KPI_KT_KTT_02': return actuals.get('Admin_Approval_SLA', 0)
                if criteria_id == 'KPI_KT_KTT_03': return actuals.get('Budget_Control_Rate', 0)

        # 2. MAPPING ĐÁNH GIÁ CHÉO
        if criteria_id == 'KPI_MAN_01':
            return actuals.get('Peer_Review_Score', 0)

        # 3. BẢNG MAPPING TỔNG HỢP CHO SALES & CÁC KHỐI KHÁC
        mapping = {
            'KPI_KD_01': actuals.get('Revenue_Salesman_Pct', 0),
            'KPI_KD_02': actuals.get('Revenue_NewCust_Mil', 0),
            'KPI_KD_03': actuals.get('AR_Overdue_Rate_Sales', 0),
            'KPI_TK_01': actuals.get('Revenue_Employee_Pct', 0),
            'KPI_TK_02': actuals.get('Revenue_Office_Mil', 0),
            'KPI_TK_03': actuals.get('Late_Delivery_Admin', 0),
            'KPI_TK_04': actuals.get('Quote_WinRate', 0),
            'KPI_KH_01': actuals.get('OTIF_Rate', 0),
            'KPI_KH_02': actuals.get('Loss_Value', 0),
            'KPI_KH_03': actuals.get('Warehouse_Budget_Over_Pct', 0),
            'KPI_KH_04': actuals.get('Total_Lines_Picked', 0),
            'KPI_KH_05': actuals.get('Avg_Picking_Hours', 0),
            'KPI_KH_07': actuals.get('Total_Lines_Putaway', 0),
            'KPI_SYS_01': actuals.get('CRM_Report_Count', 0),
            'KPI_SYS_02': actuals.get('Task_Completion_Rate', 0),
            'KPI_SYS_03': actuals.get('Gamification_XP', 0)
        }
        return mapping.get(criteria_id, 0)

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
        # 1. Lấy Profile
        query_profile = """
            SELECT P.*, C.CriteriaName, C.CalculationType, C.IsHigherBetter
            FROM dbo.KPI_USER_PROFILE P
            INNER JOIN dbo.KPI_CRITERIA_MASTER C ON P.CriteriaID = C.CriteriaID
            WHERE P.UserCode = ? AND P.IsActive = 1
        """
        profiles = self.db.get_data(query_profile, (user_code,))
        if not profiles:
            return {"success": False, "message": f"Không tìm thấy cấu hình cho {user_code}"}

        # 2. Xóa dữ liệu cũ (Xóa cả AUTO và Đánh giá chéo để nạp lại sạch)
        delete_query = """
            DELETE FROM dbo.KPI_MONTHLY_RESULT 
            WHERE UserCode = ? AND EvalYear = ? AND EvalMonth = ?
            AND (
                CriteriaID IN (SELECT CriteriaID FROM dbo.KPI_CRITERIA_MASTER WHERE CalculationType != 'MANUAL')
                OR CriteriaID = 'KPI_MAN_01'
            )
        """
        self.db.execute_non_query(delete_query, (user_code, year, month))

        # 3. Lấy thực tế
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
                
                # BỎ QUA Đánh giá chéo trong vòng lặp này để tránh lặp dòng
                if crit_id == 'KPI_MAN_01':
                    continue

                if calc_type == 'MANUAL':
                    existing_score_query = "SELECT WeightedScore FROM dbo.KPI_MONTHLY_RESULT WHERE UserCode=? AND CriteriaID=? AND EvalYear=? AND EvalMonth=?"
                    cursor.execute(existing_score_query, (user_code, crit_id, year, month))
                    row = cursor.fetchone()
                    if row:
                        total_score += safe_float(row[0])
                    else:
                        cursor.execute(insert_query, (user_code, year, month, crit_id, 0, 0, 0))
                    continue

                # TÍNH TOÁN AUTO
                actual_val = self.get_actual_value_for_criteria(crit_id, actuals_dict)
                raw_score = self.calculate_bucket_score(
                    actual_val, is_higher_better,
                    safe_float(p['Threshold_100']), safe_float(p['Threshold_85']),
                    safe_float(p['Threshold_70']), safe_float(p['Threshold_50']),
                    safe_float(p['Threshold_30']), safe_float(p['Threshold_0'])
                )
                
                weighted_score = raw_score * weight
                total_score += weighted_score
                cursor.execute(insert_query, (user_code, year, month, crit_id, actual_val, raw_score, weighted_score))

            conn.commit() # Commit đợt 1 cho các chỉ số AUTO

            # 4. TÍNH ĐÁNH GIÁ CHÉO (Chỉ gọi 1 lần duy nhất ở đây)
            # Hàm này bên dưới sẽ tự INSERT/UPDATE vào DB
            self._calculate_and_update_final_peer_score(user_code, year, month)

            # 5. TÍNH ĐIỂM CẤP DƯỚI (SYS_04) - Cần thực hiện sau khi các NV đã được chốt
            # (Giữ nguyên logic SYS_04 của sếp tại đây...)

            return {"success": True, "message": "Đã chốt KPI thành công."}

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
        """
        Thuật toán: Sếp trực tiếp 40%, Đồng nghiệp 60% (Trung bình). 
        Nếu < 3 đồng nghiệp -> Max phần ĐN = 4đ (trên tổng 6đ tối đa của phần này).
        """
        target = str(target_user).strip().upper()
        
        # 1. Lấy tất cả phiếu đánh giá cho nhân sự này
        reviews = self.db.get_data(
            "SELECT EvaluatorUser, Score FROM dbo.KPI_PEER_REVIEW WHERE TargetUser=? AND EvalYear=? AND EvalMonth=?", 
            (target, year, month)
        )
        if not reviews: return

        # 2. Xác định Cấp trên trực tiếp từ danh mục người dùng
        # Sử dụng LTRIM/RTRIM để loại bỏ khoảng trắng thừa trong DB
        query_manager = "SELECT RTRIM(LTRIM([CAP TREN])) AS Manager FROM [dbo].[GD - NGUOI DUNG] WHERE RTRIM(LTRIM(USERCODE)) = ?"
        manager_data = self.db.get_data(query_manager, (target,))
        direct_manager = str(manager_data[0]['Manager']).strip().upper() if manager_data and manager_data[0]['Manager'] else ''

        manager_score = 0
        peer_scores = []

        for r in reviews:
            eval_user = str(r['EvaluatorUser']).strip().upper()
            score = safe_float(r['Score'])
            
            # Phân loại Sếp chấm hay Đồng nghiệp chấm
            if eval_user == direct_manager: 
                manager_score = score
            else: 
                peer_scores.append(score)

        # 3. Tính toán trọng số 40/60
        s_manager = manager_score * 0.4
        
        s_peers = 0
        if len(peer_scores) > 0:
            avg_peer = sum(peer_scores) / len(peer_scores)
            s_peers = avg_peer * 0.6
            # Ràng buộc sếp đưa ra: < 3 người chấm thì phần đồng nghiệp không quá 4đ
            if len(peer_scores) < 3 and s_peers > 4:
                s_peers = 4

        final_score = round(s_manager + s_peers, 2)
        raw_score_100 = final_score * 10 

        # 4. Lưu kết quả vào bảng Result
        # Phải lấy đúng Weight từ Profile của User đó cho tiêu chí KPI_MAN_01
        profile = self.db.get_data(
            "SELECT Weight FROM dbo.KPI_USER_PROFILE WHERE RTRIM(UserCode)=? AND CriteriaID='KPI_MAN_01' AND IsActive=1", 
            (target,)
        )
        
        if profile:
            weight = safe_float(profile[0]['Weight'])
            weighted_score = raw_score_100 * weight 
            
            # Kiểm tra xem đã có dòng kết quả chưa để chọn lệnh UPDATE hay INSERT
            check_res = self.db.get_data(
                "SELECT ResultID FROM dbo.KPI_MONTHLY_RESULT WHERE RTRIM(UserCode)=? AND EvalYear=? AND EvalMonth=? AND CriteriaID='KPI_MAN_01'", 
                (target, year, month)
            )
            
            if check_res:
                update_sql = "UPDATE dbo.KPI_MONTHLY_RESULT SET ActualValue=?, RawScore=?, WeightedScore=?, CreatedAt=GETDATE() WHERE ResultID=?"
                self.db.execute_non_query(update_sql, (final_score, raw_score_100, weighted_score, check_res[0]['ResultID']))
            else:
                insert_sql = "INSERT INTO dbo.KPI_MONTHLY_RESULT (UserCode, EvalYear, EvalMonth, CriteriaID, ActualValue, RawScore, WeightedScore) VALUES (?, ?, ?, 'KPI_MAN_01', ?, ?, ?)"
                self.db.execute_non_query(insert_sql, (target, year, month, final_score, raw_score_100, weighted_score))
                
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
            },
            'KPI_KT_DIEU_01': {
                'sp': 'sp_KPI_GetDetail_Acc', # Cần bổ sung case này trong SP detail
                'columns': [
                    {"field": "VoucherNo", "label": "Số Phiếu VC"},
                    {"field": "VoucherDate", "label": "Ngày Xuất Kho"},
                    {"field": "InvoiceNo", "label": "Số Hóa Đơn"},
                    {"field": "HoursDiff", "label": "Độ trễ (Giờ)", "type": "number"}
                ],
                'sum_fields': ['HoursDiff'],
                'label_field': 'VoucherNo'
            },
            'KPI_KT_KHO_03': {
                'sp': 'sp_KPI_GetDetail_Whs',
                'columns': [
                    {"field": "InventoryID", "label": "Mã Hàng"},
                    {"field": "InventoryName", "label": "Tên Hàng"},
                    {"field": "EndQuantity", "label": "Số dư âm", "type": "number"}
                ],
                'sum_fields': ['EndQuantity'],
                'label_field': 'InventoryID'
            },
            # 1. Đánh giá phối hợp (Sử dụng bảng Peer Review)
            'KPI_MAN_01': {
                'sp': 'sp_KPI_GetDetail_PeerReview',
                'columns': [
                    {"field": "ReviewScore", "label": "Mức điểm chấm", "type": "number"},
                    {"field": "CountReviewer", "label": "Số người chấm", "type": "number"}
                ],
                'sum_fields': ['CountReviewer'],
                'label_field': 'ReviewScore'
            },

            # 2. Độ trễ xuất hóa đơn (Anh Thư - ACC_TAX)
            'KPI_KT_THU_04': {
                'sp': 'sp_KPI_GetDetail_Acc',
                'columns': [
                    {"field": "InvoiceNo", "label": "Số Hóa Đơn"},
                    {"field": "KhachHang", "label": "Khách Hàng"},
                    {"field": "NgayChungTu", "label": "Ngày Chứng Từ"},
                    {"field": "NgayHoaDon", "label": "Ngày Xuất HĐ"},
                    {"field": "SoNgayTre", "label": "Trễ (Ngày)", "type": "number"}
                ],
                'sum_fields': ['SoNgayTre'],
                'label_field': 'InvoiceNo'
            },

            # 3. Hóa đơn treo (Rà soát nợ - Anh Thư)
            'KPI_KT_THU_02': {
                'sp': 'sp_KPI_GetDetail_Acc',
                'columns': [
                    {"field": "VoucherNo", "label": "Số Chứng Từ"},
                    {"field": "NgayCT", "label": "Ngày Phát Sinh"},
                    {"field": "KhachHang", "label": "Khách Hàng"},
                    {"field": "SoTien", "label": "Số Tiền Treo", "type": "currency"}
                ],
                'sum_fields': ['SoTien'],
                'label_field': 'VoucherNo'
            },
            'KPI_KT_KTT_02': {
                'sp': 'sp_KPI_GetDetail_Acc',
                'columns': [
                    {"field": "SoPhieu", "label": "Mã Đề Nghị"},
                    {"field": "NgayGui", "label": "Ngày Gửi"},
                    {"field": "NgayDuyet", "label": "Ngày Duyệt"},
                    {"field": "SoGioDuyet", "label": "SLA (Giờ)", "type": "number"},
                    {"field": "LyDoChi", "label": "Lý Do Chi"},
                    {"field": "SoTien", "label": "Số Tiền", "type": "currency"}
                ],
                'sum_fields': ['SoTien'],
                'label_field': 'SoPhieu'
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
        elif criteria_id == 'KPI_MAN_01':
            if data:
                # data đã được sort DESC ở SP, nên dòng 0 là cao nhất, dòng cuối là thấp nhất
                max_row = data[0]
                min_row = data[-1]
                result['summary'] = f"<b>Thống kê:</b> {max_row['CountReviewer']} người cho cao nhất ({max_row['ReviewScore']}đ), {min_row['CountReviewer']} người cho thấp nhất ({min_row['ReviewScore']}đ)."
            else:
                result['summary'] = "Chưa có dữ liệu đánh giá chéo."

        elif criteria_id == 'KPI_KT_THU_04':
            avg_delay = sum([safe_float(r.get('SoNgayTre', 0)) for r in data]) / len(data) if data else 0
            result['summary'] = f"<b>Chi tiết trễ:</b> Tổng {len(data)} hóa đơn trễ hạn. Trung bình trễ <span class='text-danger'>{avg_delay:.1f} ngày</span>."

        elif criteria_id == 'KPI_KT_THU_02':
            result['summary'] = f"<b>Hóa đơn treo:</b> Hiện có <span class='text-warning'>{len(data)} chứng từ</span> đang chờ rà soát đối chiếu nợ."

        elif criteria_id == 'KPI_KT_KTT_02':
            avg_sla = sum([safe_float(r.get('SoGioDuyet', 0)) for r in data]) / len(data) if data else 0
            result['summary'] = f"<b>SLA Phê duyệt:</b> Trung bình xử lý <span class='text-primary'>{avg_sla:.1f} giờ</span> / yêu cầu."

        return result            


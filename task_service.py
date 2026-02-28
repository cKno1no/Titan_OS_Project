from flask import current_app
from db_manager import DBManager, safe_float
import datetime as dt 
from datetime import datetime, timedelta 
import config
import math
import pandas as pd 

class TaskService:
    """Xử lý toàn bộ logic nghiệp vụ liên quan đến quản lý đầu việc (Task Management)."""
    
    def __init__(self, db_manager: DBManager):
        self.db = db_manager
        self.TASK_TABLE = config.TASK_TABLE if hasattr(config, 'TASK_TABLE') else 'dbo.Task_Master'
        self.TASK_LOG_TABLE = config.TASK_LOG_TABLE 
        self.STATUS_BLOCKED = 'BLOCKED'
        self.LOG_TYPE_PROGRESS = 'PROGRESS'
        self.LOG_TYPE_BLOCKED = 'BLOCKED'
        self.LOG_TYPE_HELP_CALL = 'HELP_CALL'
        self.LOG_TYPE_REQUEST_CLOSE = 'REQUEST_CLOSE'
        self.LOG_TYPE_SUPERVISOR_NOTE = 'SUPERVISOR_NOTE'

    # =====================================================================
    # [KHỐI 1: HELPER VÀ CHUẨN HÓA DỮ LIỆU] (GIỮ NGUYÊN + BỔ SUNG TRỤ CỘT)
    # =====================================================================
    # =====================================================================
    # [KHỐI 1: HELPER VÀ CHUẨN HÓA DỮ LIỆU]
    # =====================================================================
    def _standardize_task_data(self, tasks): 
        if not tasks:
            return []
        
        standardized_tasks = []
        for task in tasks:
            # 1. Chuẩn hóa TaskDate
            task_date = task.get('TaskDate')
            if isinstance(task_date, (dt.datetime, dt.date)): 
                task['TaskDateDisplay'] = task_date.strftime('%d/%m')
            else:
                task['TaskDateDisplay'] = task.get('TaskDate')
            
            # 2. Chuẩn hóa các cột DATETIME khác
            for key in ['CompletedDate', 'NoteTimestamp', 'StartDate', 'DueDate']:
                value = task.get(key)
                if isinstance(value, (dt.datetime, dt.date)):
                    task[key] = value.isoformat()
                else:
                    # Ép cứng về None nếu không phải ngày tháng, để JSON dịch thành null
                    task[key] = None
            
            # 3. Chuẩn hóa các cột chuỗi NULLABLE
            for key in ['ObjectID', 'DetailContent', 'NoteCapTren', 'SupervisorCode', 'Attachments', 'ParentTaskID', 'ClientName', 'AssigneeShortName']:
                val = task.get(key)
                if val is None or str(val).strip().lower() in ['nan', 'nat', 'none', '']:
                     task[key] = None
                else:
                     task[key] = val

            # 4. [FIX LỖI CRASH JS] Chuẩn hóa chặt chẽ các cột SỐ (Tránh lỗi JSON NaN)
            for num_col in ['ProgressPercentage', 'LogCount']:
                val = task.get(num_col)
                try:
                    f_val = float(val)
                    # Nếu là số thực nhưng mang giá trị NaN (Not a Number) -> Đưa về 0
                    task[num_col] = 0 if math.isnan(f_val) else int(f_val)
                except (ValueError, TypeError):
                    task[num_col] = 0
                
            standardized_tasks.append(task)
        return standardized_tasks
    
    def _is_admin_user(self, user_code):
        query = f"SELECT [ROLE] FROM {config.TEN_BANG_NGUOI_DUNG} WHERE USERCODE = ? AND RTRIM([ROLE]) = ?"
        return bool(self.db.get_data(query, (user_code, config.ROLE_ADMIN)))
    
    def _is_helper_subordinate(self, helper_code, supervisor_code):
        if not helper_code or not supervisor_code: return False
        if self._is_admin_user(supervisor_code): return True
        
        query = f"SELECT [CAP TREN] FROM {config.TEN_BANG_NGUOI_DUNG} WHERE USERCODE = ?"
        data = self.db.get_data(query, (helper_code,))
        if data and data[0].get('CAP TREN'):
            return data[0]['CAP TREN'].strip().upper() == supervisor_code.strip().upper()
        return False
    
    def _enrich_tasks_with_client_name(self, tasks):
        object_ids = [t['ObjectID'] for t in tasks if t.get('ObjectID') and t['ObjectID'].strip()]
        if not object_ids:
            for task in tasks: task['ClientName'] = None
            return tasks

        object_ids_str = ", ".join(f"'{o.strip()}'" for o in set(object_ids))
        query = f"SELECT RTRIM(ObjectID) AS ObjectID, ShortObjectName AS ClientName FROM {config.ERP_IT1202} WHERE ObjectID IN ({object_ids_str})"
        name_data = self.db.get_data(query)
        name_dict = {row['ObjectID']: row['ClientName'] for row in name_data}

        for task in tasks: task['ClientName'] = name_dict.get(task.get('ObjectID', '').strip(), None)
        return tasks
    
    def _enrich_tasks_with_user_info(self, tasks):
        user_codes = [t['UserCode'] for t in tasks if t.get('UserCode') and t['UserCode'].strip()]
        if not user_codes:
            for task in tasks: task['AssigneeShortName'] = None
            return tasks

        user_codes_str = ", ".join(f"'{u.strip()}'" for u in set(user_codes))
        query = f"SELECT [USERCODE], [SHORTNAME] AS AssigneeShortName FROM {config.TEN_BANG_NGUOI_DUNG} WHERE USERCODE IN ({user_codes_str})"
        name_data = self.db.get_data(query)
        name_dict = {row['USERCODE']: row['AssigneeShortName'] for row in name_data}

        for task in tasks: task['AssigneeShortName'] = name_dict.get(task.get('UserCode', '').strip(), task.get('UserCode'))
        return tasks

    def _get_time_filter_params(self, days_ago=30):
        date_limit = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m-%d')
        today_date = datetime.now().strftime('%Y-%m-%d')
        return date_limit, today_date

    # =====================================================================
    # [KHỐI 2: TẠO TASK & CHẶN TASK RÁC] 
    # =====================================================================
    def validate_task_creation(self, user_code, object_id, task_type):
        """[TRỤ CỘT MỚI] Chặn tạo nhiều task cho cùng 1 mục tiêu/khách hàng."""
        if not object_id: return True, None 
        check_sql = f"""
            SELECT TaskID FROM {self.TASK_TABLE} 
            WHERE ObjectID = ? AND TaskType = ? AND UserCode = ? AND Status IN ('OPEN', 'PENDING', 'HELP_NEEDED', 'WAITING_CONFIRM')
        """
        existing = self.db.get_data(check_sql, (object_id, task_type, user_code))
        return (False, existing[0]['TaskID']) if existing else (True, None)
        
    def create_new_task(self, user_code, title, supervisor_code, task_type, attachments=None, object_id=None, detail_content=None, parent_task_id=None, start_date=None, due_date=None):
        conn = None
        try:
            conn = self.db.get_transaction_connection()
            cursor = conn.cursor()
            
            insert_query = f"""
                INSERT INTO {self.TASK_TABLE} 
                (UserCode, TaskDate, Status, Title, CapTren, Attachments, TaskType, ObjectID, LastUpdated, ProgressPercentage, DetailContent, ParentTaskID, StartDate, DueDate)
                OUTPUT INSERTED.TaskID 
                VALUES (?, GETDATE(), 'OPEN', ?, ?, ?, ?, ?, GETDATE(), 0, ?, ?, ?, ?)
            """
            params = (user_code, title, supervisor_code, attachments, task_type.upper(), object_id, detail_content, parent_task_id, start_date, due_date)
            cursor.execute(insert_query, params)
            row = cursor.fetchone()
            
            if row:
                new_task_id = row[0]
                initial_note = f"Khởi tạo công việc: {detail_content}" if detail_content else "Khởi tạo công việc mới."
                log_query = f"""
                    INSERT INTO {self.TASK_LOG_TABLE} (TaskID, UserCode, UpdateDate, ProgressPercentage, UpdateContent, TaskLogType)
                    VALUES (?, ?, GETDATE(), 0, ?, 'CREATE')
                """
                cursor.execute(log_query, (new_task_id, user_code, initial_note))
                conn.commit()
                return True
            else:
                conn.rollback()
                return False
        except Exception as e:
            if conn: conn.rollback()
            current_app.logger.error(f"LỖI TẠO TASK: {e}")
            return False
        finally:
            if conn: conn.close()

    # =====================================================================
    # [KHỐI 3: TRUY VẤN HIỂN THỊ - KANBAN, HISTORY, KPI] (GIỮ NGUYÊN 100%)
    # =====================================================================
    def get_kanban_tasks(self, user_code, is_admin=False, days_ago=3, view_mode='USER'):
        date_limit = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m-%d')
        base_conditions = []
        if view_mode == 'SUPERVISOR':
            if is_admin: base_conditions.append("1=1") 
            else: base_conditions.append(f"CapTren = '{user_code}'")
        else: base_conditions.append(f"UserCode = '{user_code}'")
        
        user_filter = " AND ".join(base_conditions)
        query = f"""
            SELECT T1.*, (SELECT COUNT(LogID) FROM {self.TASK_LOG_TABLE} T2 WHERE T2.TaskID = T1.TaskID) AS LogCount
            FROM {self.TASK_TABLE} AS T1
            WHERE ({user_filter}) AND (
                (TaskDate >= '{date_limit}') OR 
                (Status IN ('OPEN', 'PENDING', 'BLOCKED', 'HELP_NEEDED', 'WAITING_CONFIRM'))
            )
            ORDER BY LastUpdated DESC, TaskDate DESC
        """
        data = self.db.get_data(query)
        return self._standardize_task_data(self._enrich_tasks_with_user_info(self._enrich_tasks_with_client_name(data)))
    
    def get_filtered_tasks(self, user_code, filter_type='RISK', is_admin=False, days_ago=30, view_mode='USER', text_search_term=None): 
        date_limit, today_date = self._get_time_filter_params(days_ago)
        where_conditions = [f"TaskDate BETWEEN '{date_limit}' AND '{today_date}'"]
        if view_mode == 'SUPERVISOR':
            if not is_admin: where_conditions.append(f"CapTren = '{user_code}'")
        else: where_conditions.append(f"UserCode = '{user_code}'")

        if filter_type == 'COMPLETED': where_conditions.append("Status = 'COMPLETED'")
        elif filter_type == 'RISK': where_conditions.append("Status IN ('PENDING', 'HELP_NEEDED', 'OPEN', 'WAITING_CONFIRM')")
        elif filter_type == 'HELP': where_conditions.append("Status = 'HELP_NEEDED'")
        elif filter_type == 'PENDING': where_conditions.append("Status IN ('PENDING', 'OPEN', 'WAITING_CONFIRM')")
        
        if text_search_term and text_search_term.strip():
            terms = [t.strip() for t in text_search_term.split(';') if t.strip()]
            if terms:
                search_conditions = [f"(Title LIKE '%{t}%' OR DetailContent LIKE '%{t}%' OR ObjectID LIKE '%{t}%')" for t in terms]
                where_conditions.append("(" + " OR ".join(search_conditions) + ")")

        query = f"""
            SELECT T1.*, (SELECT COUNT(LogID) FROM {self.TASK_LOG_TABLE} T2 WHERE T2.TaskID = T1.TaskID) AS LogCount
            FROM {self.TASK_TABLE} AS T1
            WHERE {' AND '.join(where_conditions)}
            ORDER BY TaskDate DESC, LastUpdated DESC
        """
        data = self.db.get_data(query)
        return self._standardize_task_data(self._enrich_tasks_with_user_info(self._enrich_tasks_with_client_name(data)))

    def get_kpi_summary(self, user_code, is_admin=False, days_ago=30, view_mode='USER'):
        date_limit, today_date = self._get_time_filter_params(days_ago)
        where_conditions = [f"TaskDate BETWEEN '{date_limit}' AND '{today_date}'"]
        if view_mode == 'SUPERVISOR':
            if not is_admin: where_conditions.append(f"CapTren = '{user_code}'")
        else: where_conditions.append(f"UserCode = '{user_code}'")

        query = f"""
            SELECT COUNT(TaskID) AS TotalTasks,
                SUM(CASE WHEN Status = 'COMPLETED' THEN 1 ELSE 0 END) AS Completed,
                SUM(CASE WHEN Status IN ('OPEN', 'PENDING', 'WAITING_CONFIRM') THEN 1 ELSE 0 END) AS Pending,
                SUM(CASE WHEN Status = 'HELP_NEEDED' THEN 1 ELSE 0 END) AS HelpNeeded
            FROM {self.TASK_TABLE} WHERE {' AND '.join(where_conditions)}
        """
        data = self.db.get_data(query)
        summary = data[0] if data else {'TotalTasks': 0, 'Completed': 0, 'Pending': 0, 'HelpNeeded': 0}
        total, completed = summary['TotalTasks'] or 0, summary['Completed'] or 0
        summary['CompletedPercent'] = round((completed / total) * 100) if total > 0 else 0
        return summary

    def get_user_tasks(self, user_code, month=None, is_admin=False):
        where_conditions = ["1 = 1"]
        if not is_admin: where_conditions.append(f"UserCode = '{user_code}'")
        query = f"""
            SELECT TaskID, UserCode, TaskDate, Status, Priority, Title, ObjectID, DetailContent, NoteCapTren, NoteTimestamp, LastUpdated, CompletedDate
            FROM {self.TASK_TABLE} WHERE {' AND '.join(where_conditions)} ORDER BY TaskDate DESC, Priority DESC
        """
        data = self.db.get_data(query)
        if data:
            for task in data:
                task['TaskDateDisplay'] = task['TaskDate'].strftime('%d/%m') if isinstance(task.get('TaskDate'), (datetime, dt.date)) else task.get('TaskDate')
        return data

    def get_task_by_id(self, task_id):
        query = f"SELECT * FROM {self.TASK_TABLE} WHERE TaskID = ?"
        data = self.db.get_data(query, (task_id,))
        standardized_data = self._standardize_task_data(data)
        return standardized_data[0] if standardized_data else None

    # =====================================================================
    # [KHỐI 4: LOG TIẾN ĐỘ, AUDIT VÀ GAMIFICATION] (BẢN CHUẨN XÁC NHẤT)
    # =====================================================================
    # =====================================================================
    # [KHỐI 4: LOG TIẾN ĐỘ, AUDIT, FILE VÀ GAMIFICATION] 
    # =====================================================================
    # CHÚ Ý: Đã thêm tham số attachment_url=None
    def log_task_progress(self, task_id, user_code, progress_percent, content, log_type, helper_codes=None, ip_address=None, object_id=None, attachment_url=None):
        from flask import current_app 
        original_task = self.get_task_by_id(task_id)
        if not original_task: return False
        
        # 1. Xử lý Logic Phân Quyền
        if log_type == self.LOG_TYPE_BLOCKED:
             new_status = self.STATUS_BLOCKED
        elif log_type == self.LOG_TYPE_REQUEST_CLOSE:
             is_authorized = user_code == original_task.get('CapTren') or self._is_admin_user(user_code) or user_code == original_task.get('UserCode')
             if is_authorized:
                 new_status = 'COMPLETED'
                 progress_percent = 100 
             else:
                 new_status = 'WAITING_CONFIRM' 
                 progress_percent = 100
             if not content: content = "Đã hoàn thành, yêu cầu đóng công việc."
        elif log_type == self.LOG_TYPE_HELP_CALL:
             new_status = 'HELP_NEEDED'
        else:
             new_status = 'PENDING' 
        
        # 2. Ghi Log vào TPL
        first_helper = helper_codes[0] if isinstance(helper_codes, list) and helper_codes else helper_codes
        if isinstance(first_helper, list): first_helper = None
        log_id = self.db.log_progress_entry(task_id, user_code, progress_percent, content, log_type, first_helper)
        if not log_id: return False
        
        # 3. AUDIT LOG & GAMIFICATION XP
        if new_status == 'COMPLETED':
            if original_task.get('Status') == 'HELP_NEEDED':
                if hasattr(current_app, 'gamification_service'): current_app.gamification_service.log_activity(user_code, 'TASK_HELP_COMPLETED')
                if ip_address: self.db.write_audit_log(user_code, 'TASK_HELP_COMPLETED', 'INFO', f"Vượt khó: Hoàn thành task #{task_id}", ip_address)
            else:
                if hasattr(current_app, 'gamification_service'):
                    activity_code = 'COMPLETE_TASK_SELF' if str(user_code).strip().upper() == str(original_task.get('UserCode')).strip().upper() else 'COMPLETE_TASK_ASSIGNED'
                    current_app.gamification_service.log_activity(user_code, activity_code)
                if ip_address: self.db.write_audit_log(user_code, 'TASK_COMPLETED', 'INFO', f"Hoàn thành công việc #{task_id}", ip_address)
        elif new_status == 'WAITING_CONFIRM':
            if ip_address: self.db.write_audit_log(user_code, 'TASK_WAITING', 'INFO', f"Báo cáo 100% Task #{task_id}, chờ duyệt", ip_address)
        elif log_type == self.LOG_TYPE_HELP_CALL:
            if ip_address: self.db.write_audit_log(user_code, 'HELP_CALL', 'WARNING', f"Yêu cầu hỗ trợ Task #{task_id}", ip_address)
        else:
            if ip_address: self.db.write_audit_log(user_code, f'TASK_{log_type}', 'INFO', f"Cập nhật tiến độ Task #{task_id} ({progress_percent}%)", ip_address)

        # 4. GỌI MULTICAST NẾU CÓ
        if log_type == self.LOG_TYPE_HELP_CALL and helper_codes:
             if isinstance(helper_codes, str): helper_codes = [helper_codes]
             self.process_help_request_multicast(helper_codes_list=helper_codes, original_task_id=task_id, current_user_code=user_code, detail_content=content)
        
        # 5. CẬP NHẬT MASTER & LƯU FILE
        final_object_id = object_id if object_id else original_task.get('ObjectID')
        completed_clause = ", CompletedDate = GETDATE()" if new_status == 'COMPLETED' else ""
        
        attachment_clause = ""
        params = [progress_percent, new_status, content, final_object_id]
        
        # Nếu có file mới đẩy lên, cập nhật đè lên cột Attachments
        if attachment_url:
            attachment_clause = ", Attachments = ?"
            params.append(attachment_url)
            
        params.append(task_id)

        update_master_query = f"""
            UPDATE {self.TASK_TABLE}
            SET LastUpdated = GETDATE(), ProgressPercentage = ?, Status = ?, DetailContent = ?, ObjectID = ? 
            {completed_clause}
            {attachment_clause}
            WHERE TaskID = ?
        """
        self.db.execute_non_query(update_master_query, tuple(params))
        return log_id

    # =====================================================================
    # [KHỐI 5: SẾP DUYỆT VÀ FEEDBACK]
    # =====================================================================
    def approve_task(self, task_id, supervisor_code, is_approved, feedback, ip_address=None):
        from flask import current_app
        original_task = self.get_task_by_id(task_id)
        if not original_task: return False
        
        new_status = 'COMPLETED' if is_approved else 'PENDING'
        progress_percent = 100 if is_approved else 90
        log_type = 'APPROVE_CLOSE' if is_approved else 'REJECT_CLOSE'
        content = f"[{'ĐÃ DUYỆT' if is_approved else 'TỪ CHỐI'}]: {feedback}"

        self.db.log_progress_entry(task_id, supervisor_code, progress_percent, content, log_type, None)
        
        completed_clause = ", CompletedDate = GETDATE()" if is_approved else ""
        update_query = f"""
            UPDATE {self.TASK_TABLE}
            SET Status = ?, ProgressPercentage = ?, LastUpdated = GETDATE(), NoteCapTren = ?, SupervisorCode = ? {completed_clause}
            WHERE TaskID = ?
        """
        success = self.db.execute_non_query(update_query, (new_status, progress_percent, feedback, supervisor_code, task_id))
        
        if success:
            if is_approved:
                if hasattr(current_app, 'gamification_service'): current_app.gamification_service.log_activity(original_task.get('UserCode'), 'COMPLETE_TASK_ASSIGNED')
                if ip_address: self.db.write_audit_log(supervisor_code, 'TASK_APPROVED', 'INFO', f"Duyệt hoàn thành Task #{task_id}", ip_address)
            else:
                if ip_address: self.db.write_audit_log(supervisor_code, 'TASK_REJECTED', 'WARNING', f"Từ chối Task #{task_id}, trả về PENDING", ip_address)
        return success

    def add_supervisor_feedback(self, log_id, supervisor_code, feedback, ip_address=None):
        success = self.db.execute_update_log_feedback(log_id, supervisor_code, feedback)
        if success:
            sync_query = f"""
                UPDATE {self.TASK_TABLE} 
                SET NoteCapTren = ?, NoteTimestamp = GETDATE(), SupervisorCode = ?
                WHERE TaskID = (SELECT TaskID FROM {self.TASK_LOG_TABLE} WHERE LogID = ?)
            """
            self.db.execute_non_query(sync_query, (feedback, supervisor_code, log_id))
            if ip_address: self.db.write_audit_log(supervisor_code, 'TASK_FEEDBACK', 'INFO', f"Gửi chỉ đạo vào Log #{log_id}", ip_address)
        return success

    # =====================================================================
    # [KHỐI 6: CÁC HÀM TIỆN ÍCH KHÁC] (GIỮ NGUYÊN)
    # =====================================================================
    def update_task_progress(self, task_id, object_id, content, status, helper_code=None, completed_date=None):
        pass # Đã Deprecated, nhưng giữ lại vỏ để tránh crash nếu code cũ vô tình gọi tới.

    def update_task_priority(self, task_id, new_priority):
        try: return self.db.execute_non_query(f"UPDATE {self.TASK_TABLE} SET Priority = ?, LastUpdated = GETDATE() WHERE TaskID = ?", (new_priority.upper(), task_id))
        except: return False

    def get_eligible_helpers(self, division=None):
        params = []
        query = f"SELECT [USERCODE], [SHORTNAME] FROM {config.TEN_BANG_NGUOI_DUNG} WHERE [PHONG BAN] IS NOT NULL AND RTRIM([PHONG BAN]) <> '9. DU HOC'"
        if division:
            query += " AND [Division] = ?"
            params.append(division)
        query += " ORDER BY [SHORTNAME]"
        return self.db.get_data(query, tuple(params))

    def create_help_request_task(self, helper_code, original_task_id, current_user_code, original_title, original_object_id, original_detail_content, new_task_type):
        is_delegated = self._is_helper_subordinate(helper_code, current_user_code)
        new_priority = 'HIGH' if is_delegated else 'ALERT'
        prefix = "Y/c từ cấp trên" if is_delegated else "HELP"
        
        insert_query = f"""
            INSERT INTO {self.TASK_TABLE} (UserCode, TaskDate, Status, Priority, Title, CapTren, ObjectID, DetailContent, LastUpdated, SupervisorCode, TaskType, ParentTaskID)
            VALUES (?, GETDATE(), 'HELP_NEEDED', ?, ?, ?, ?, ?, GETDATE(), 'KD000', ?, ?)
        """
        params = (helper_code, new_priority, f"{prefix} - [{current_user_code}] - {original_title}", current_user_code, original_object_id, original_detail_content, new_task_type, original_task_id)
        try: return self.db.execute_non_query(insert_query, params)
        except: return False

    def process_help_request_multicast(self, helper_codes_list, original_task_id, current_user_code, detail_content):
        original_task = self.get_task_by_id(original_task_id)
        if not original_task: return False
        
        final_helpers = set()
        for code in helper_codes_list:
            if code.startswith('DEPT_'): 
                final_helpers.update(self.get_users_by_department(code.replace('DEPT_', '')))
            else:
                final_helpers.add(code)
        if current_user_code in final_helpers: final_helpers.remove(current_user_code)

        count = 0
        for helper in final_helpers:
            self.create_help_request_task(
                helper_code=helper, original_task_id=original_task_id, current_user_code=current_user_code,
                original_title=original_task.get('Title', 'N/A'), original_object_id=original_task.get('ObjectID', None),
                original_detail_content=detail_content, new_task_type='NOI_BO' 
            )
            count += 1
        return count 

    def get_users_by_department(self, dept_code):
        data = self.db.get_data(f"SELECT USERCODE FROM {config.TEN_BANG_NGUOI_DUNG} WHERE [BO PHAN] = ?", (dept_code,))
        return [row['USERCODE'] for row in data] if data else []

    def get_task_history_logs(self, task_id):
        query = f"""
            SELECT T1.LogID, T1.UpdateDate, T1.UserCode, T1.SupervisorCode, T1.ProgressPercentage, T1.UpdateContent, T1.TaskLogType, 
                   T1.SupervisorFeedback, T1.FeedbackDate, T1.HelperRequestCode, T2.SHORTNAME AS UserShortName
            FROM {self.TASK_LOG_TABLE} AS T1
            LEFT JOIN {config.TEN_BANG_NGUOI_DUNG} AS T2 ON T1.UserCode = T2.USERCODE
            WHERE T1.TaskID = ? ORDER BY T1.UpdateDate DESC
        """
        data = self.db.get_data(query, (task_id,))
        if not data: return []

        # [FIX CRASH]: Xử lý an toàn cho cả kiểu String và Datetime
        for log in data:
            # Xử lý UpdateDate
            up_date = log.get('UpdateDate')
            if isinstance(up_date, (datetime, dt.date)):
                log['UpdateDate'] = up_date.isoformat()
            elif pd.isna(up_date):
                log['UpdateDate'] = None
            # Nếu đã là chuỗi thì giữ nguyên không làm gì cả
                
            # Xử lý FeedbackDate
            fb_date = log.get('FeedbackDate')
            if isinstance(fb_date, (datetime, dt.date)):
                log['FeedbackDate'] = fb_date.isoformat()
            elif pd.isna(fb_date):
                log['FeedbackDate'] = None

        return data

    def get_recently_updated_tasks(self, user_code, is_admin=False, view_mode='USER', minutes_ago=15):
        minutes_ago_str = (datetime.now() - timedelta(minutes=minutes_ago)).strftime('%Y-%m-%d %H:%M:%S')
        where_conditions = [f"LastUpdated >= '{minutes_ago_str}'", f"Status IN ('OPEN', 'PENDING', 'HELP_NEEDED', 'COMPLETED', 'WAITING_CONFIRM')"]
        
        if view_mode == 'SUPERVISOR': where_conditions.append(f"CapTren = '{user_code}'") 
        elif not is_admin: where_conditions.append(f"UserCode = '{user_code}'") 
        
        query = f"SELECT TaskID, LastUpdated FROM {self.TASK_TABLE} WHERE {' AND '.join(where_conditions)} ORDER BY LastUpdated DESC"
        return [{'TaskID': task['TaskID'], 'LastUpdated': task['LastUpdated']} for task in self.db.get_data(query)]
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
from utils import login_required, permission_required
from datetime import datetime
import config 
import os
import json
from werkzeug.utils import secure_filename

task_bp = Blueprint('task_bp', __name__)

# [BẢO MẬT] Danh sách các đuôi file được phép (KHÔNG CÓ ZIP, RAR)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv', 'txt'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
# [HÀM HELPER CẦN THIẾT]
def get_user_ip():
    if request.headers.getlist("X-Forwarded-For"):
       return request.headers.getlist("X-Forwarded-For")[0]
    else:
       return request.remote_addr

# =====================================================================
# [ROUTES]
# =====================================================================

@task_bp.route('/task_dashboard', methods=['GET', 'POST'])
@login_required
@permission_required('VIEW_TASK')
def task_dashboard():
    """ROUTE: Dashboard Quản lý Đầu việc hàng ngày."""
    
    task_service = current_app.task_service 
    
    user_code = session.get('user_code')
    user_role = session.get('user_role', '').strip().upper()
    
    real_is_admin = (user_role == config.ROLE_ADMIN)
    view_mode = request.args.get('view', 'USER').upper()
    filter_type = request.args.get('filter') or 'ALL'
    text_search_term = request.args.get('search') or request.form.get('search') or ''

    is_admin_for_query = real_is_admin if view_mode != 'USER' else False 
    can_manage_view = real_is_admin or (user_role == config.ROLE_MANAGER)

    # --- XỬ LÝ TẠO TASK MỚI ---
    if request.method == 'POST' and 'create_task' in request.form:
        title = request.form.get('task_title')
        supervisor_code = session.get('cap_tren')
        object_id = request.form.get('object_id') 
        task_type = request.form.get('task_type')
        detail_content = request.form.get('detail_content')
        
        # Nhận thêm tham số Quản trị dự án từ form
        due_date = request.form.get('due_date') or None
        parent_task_id = request.form.get('parent_task_id') or None
        attachments_filename = None 

        if title:
            # 1. Rào cản Anti-Split (Chặn tạo Task trùng lặp)
            can_create, existing_id = task_service.validate_task_creation(user_code, object_id, task_type)
            if not can_create:
                flash(f"Khách hàng này đang có Task #{existing_id} đang xử lý. Vui lòng cập nhật Log vào đó thay vì tạo mới!", "warning")
                return redirect(url_for('task_bp.task_dashboard'))

            # 2. Thực hiện tạo
            if task_service.create_new_task(
                user_code=user_code, 
                title=title, 
                supervisor_code=supervisor_code, 
                attachments=attachments_filename, 
                task_type=task_type, 
                object_id=object_id,
                detail_content=detail_content,
                parent_task_id=parent_task_id, 
                start_date=datetime.now().strftime('%Y-%m-%d'), 
                due_date=due_date 
            ):
                try:
                    current_app.db_manager.write_audit_log(
                        user_code, 'TASK_CREATE', 'INFO', 
                        f"Tạo Task mới: {title} (Type: {task_type}, Obj: {object_id})", get_user_ip()
                    )
                except Exception as e:
                    current_app.logger.error(f"Lỗi ghi log TASK_CREATE: {e}")
                    
                flash("Task mới đã được tạo thành công!", 'success')
            else:
                flash("Lỗi khi tạo Task. Vui lòng thử lại.", 'danger')
            return redirect(url_for('task_bp.task_dashboard'))
    
    # --- GỌI DỮ LIỆU HIỂN THỊ ---
    kpi_summary = task_service.get_kpi_summary(user_code, is_admin=is_admin_for_query, view_mode=view_mode)
    kanban_tasks = task_service.get_kanban_tasks(user_code, is_admin=is_admin_for_query, view_mode=view_mode)
    risk_history_tasks = task_service.get_filtered_tasks(
        user_code, filter_type=filter_type, is_admin=is_admin_for_query, 
        view_mode=view_mode, text_search_term=text_search_term 
    )
    
    return render_template(
        'task_dashboard.html',
        kpi=kpi_summary, kanban_tasks=kanban_tasks, history_tasks=risk_history_tasks, 
        is_admin=real_is_admin, current_date=datetime.now().strftime('%Y-%m-%d'),
        active_filter=filter_type, view_mode=view_mode, can_manage_view=can_manage_view, 
        text_search_term=text_search_term 
    )

# =====================================================================
# [APIs]
# =====================================================================

@task_bp.route('/api/task/log_progress', methods=['POST'])
@login_required
def api_log_task_progress():
    task_service = current_app.task_service 
    user_code = session.get('user_code')
    
    attachment_url = None
    has_attachment = False

    # 1. XỬ LÝ FORM DATA (CÓ UPLOAD FILE)
    if request.content_type and request.content_type.startswith('multipart/form-data'):
        data = request.form
        try: helper_codes = json.loads(data.get('helper_codes', '[]'))
        except: helper_codes = []
        
        file = request.files.get('attachment')
        if file and file.filename:
            # [BẢO MẬT] Kiểm tra đuôi file
            if not allowed_file(file.filename):
                return jsonify({'success': False, 'message': 'Định dạng file không được phép. Chỉ hỗ trợ Hình ảnh, PDF, Word, Excel.'}), 400
                
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            save_name = f"{timestamp}_{filename}"
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'tasks')
            os.makedirs(upload_folder, exist_ok=True)
            file.save(os.path.join(upload_folder, save_name))
            attachment_url = f"/static/uploads/tasks/{save_name}"
            has_attachment = True
    else:
        # 2. XỬ LÝ JSON BÌNH THƯỜNG
        data = request.get_json(silent=True) or {}
        helper_codes = data.get('helper_codes', [])
        has_attachment = data.get('has_attachment') == True

    if not isinstance(helper_codes, list): helper_codes = [helper_codes] if helper_codes else []

    task_id = data.get('task_id')
    content = data.get('content', '')
    progress_percent = data.get('progress_percent') 
    log_type = data.get('log_type') 
    object_id = data.get('object_id') 

    if not task_id or not log_type: return jsonify({'success': False, 'message': 'Thiếu dữ liệu bắt buộc.'}), 400

    # Rào cản Proof of Work
    if log_type == 'REQUEST_CLOSE':
        task_info = task_service.get_task_by_id(task_id)
        if task_info and task_info.get('TaskType') in ['DELIVERY', 'DOCUMENT']:
            if not has_attachment and not task_info.get('Attachments'):
                return jsonify({'success': False, 'message': 'Bắt buộc phải tải lên hình ảnh/file minh chứng.'}), 400

    try:
        # Gọi xuống Service kèm theo attachment_url
        log_id = task_service.log_task_progress(
            task_id=task_id, user_code=user_code,
            progress_percent=int(progress_percent) if progress_percent else 0,
            content=content, log_type=log_type, helper_codes=helper_codes, 
            ip_address=get_user_ip(), object_id=object_id, 
            attachment_url=attachment_url 
        )
        
        if log_id: return jsonify({'success': True, 'message': 'Cập nhật thành công!'})
        return jsonify({'success': False, 'message': 'Lỗi ghi CSDL.'}), 500
    except Exception as e:
        current_app.logger.error(f"LỖI API LOG PROGRESS: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@task_bp.route('/api/task/history/<int:task_id>', methods=['GET'])
@login_required
def api_get_task_history(task_id):
    """API: Lấy lịch sử Log tiến độ chi tiết cho Modal."""
    try:
        logs = current_app.task_service.get_task_history_logs(task_id)
        return jsonify(logs)
    except Exception as e:
        current_app.logger.error(f"LỖI API GET LOG HISTORY: {e}")
        return jsonify({'error': 'Lỗi khi tải lịch sử.'}), 500


@task_bp.route('/api/task/add_feedback', methods=['POST'])
@login_required
def api_add_supervisor_feedback():
    """API: Cấp trên thêm phản hồi trên LogID cụ thể (Đồng bộ Master)."""
    data = request.json
    supervisor_code = session.get('user_code')
    log_id = data.get('log_id')
    feedback = data.get('feedback')
    
    if not log_id or not feedback:
        return jsonify({'success': False, 'message': 'Thiếu LogID hoặc nội dung phản hồi.'}), 400

    try:
        success = current_app.task_service.add_supervisor_feedback(log_id, supervisor_code, feedback, ip_address=get_user_ip())
        if success: return jsonify({'success': True, 'message': 'Đã gửi chỉ đạo thành công.'})
        return jsonify({'success': False, 'message': 'Lỗi CSDL khi lưu phản hồi.'}), 500
    except Exception as e:
        current_app.logger.error(f"LỖI API ADD FEEDBACK: {e}")
        return jsonify({'success': False, 'message': f'Lỗi hệ thống: {str(e)}'}), 500


@task_bp.route('/api/task/toggle_priority/<int:task_id>', methods=['POST'])
@login_required
def api_toggle_task_priority(task_id):
    """API: Thay đổi Priority thành HIGH."""
    task_service = current_app.task_service 
    current_task_data = task_service.get_task_by_id(task_id) 
    
    if not current_task_data: return jsonify({'success': False, 'message': 'Task không tồn tại.'}), 404
        
    current_priority = current_task_data.get('Priority', 'NORMAL')
    new_priority = 'NORMAL' if current_priority == 'HIGH' else 'HIGH'
    
    if task_service.update_task_priority(task_id, new_priority):
        current_app.db_manager.write_audit_log(session.get('user_code'), 'TASK_PRIORITY_TOGGLE', 'WARNING', f"Thay đổi ưu tiên Task #{task_id} thành {new_priority}", get_user_ip())
        return jsonify({'success': True, 'new_priority': new_priority}), 200
    return jsonify({'success': False, 'message': 'Lỗi CSDL khi cập nhật ưu tiên.'}), 500


@task_bp.route('/api/get_eligible_helpers', methods=['GET'])
@login_required
def api_get_eligible_helpers():
    """API: Trả về danh sách Helper."""
    try:
        helpers = current_app.task_service.get_eligible_helpers()
        formatted_helpers = [{'code': h['USERCODE'], 'name': f"{h['USERCODE']} - {h['SHORTNAME']}"} for h in helpers]
        return jsonify(formatted_helpers)
    except Exception as e:
        current_app.logger.error(f"Lỗi API lấy danh sách helper: {e}")
        return jsonify([]), 500


@task_bp.route('/api/task/recent_updates', methods=['GET'])
@login_required
def api_task_recent_updates():
    """API: Refresh Kanban tự động."""
    user_code = session.get('user_code')
    is_admin = session.get('user_role', '').strip().upper() == config.ROLE_ADMIN
    view_mode = request.args.get('view', 'USER').upper()
    minutes_ago = int(request.args.get('minutes', 15))
    
    try:
        updated_tasks = current_app.task_service.get_recently_updated_tasks(user_code, is_admin=is_admin, view_mode=view_mode, minutes_ago=minutes_ago)
        return jsonify(updated_tasks) 
    except Exception as e:
        current_app.logger.error(f"LỖI API GET RECENT UPDATES: {e}")
        return jsonify({'error': 'Lỗi khi tải cập nhật gần nhất.'}), 500

# =====================================================================
# [API MỚI] SẾP DUYỆT TASK (MỞ KHÓA WAITING_CONFIRM)
# =====================================================================
@task_bp.route('/api/task/approve', methods=['POST'])
@login_required
@permission_required('APPROVE_TASK')
def api_approve_task():
    """API: Sếp duyệt hoàn thành hoặc từ chối Task đang chờ."""
    data = request.json
    task_id = data.get('task_id')
    is_approved = data.get('is_approved') == True
    feedback = data.get('feedback', '')
    supervisor_code = session.get('user_code')

    if not task_id: return jsonify({'success': False, 'message': 'Thiếu ID.'}), 400

    success = current_app.task_service.approve_task(task_id, supervisor_code, is_approved, feedback, ip_address=get_user_ip())
    if success: return jsonify({'success': True, 'message': 'Đã duyệt Task.' if is_approved else 'Đã trả Task về PENDING.'})
    return jsonify({'success': False, 'message': 'Lỗi hệ thống.'}), 500
# blueprints/kpi_evaluation_bp.py

from flask import Blueprint, render_template, session, request, jsonify, current_app
from utils import login_required, record_activity, get_user_ip
from datetime import datetime
from db_manager import safe_float
import math # Nhớ thêm import math ở đầu file


# Khởi tạo Blueprint với tên mới và URL prefix mới để không đụng hàng
kpi_evaluation_bp = Blueprint('kpi_evaluation_bp', __name__, url_prefix='/kpi-eval')


@kpi_evaluation_bp.route('/dashboard', methods=['GET'])
@login_required
def kpi_dashboard():
    user_code = session.get('user_code')
    user_role = str(session.get('user_role', '')).strip().upper()
    is_admin = (user_role == 'ADMIN')
    
    # 1. Lấy tham số thời gian
    now = datetime.now()
    default_month = now.month
    default_year = now.year
    
    selected_year = int(request.args.get('year', default_year))
    selected_month = int(request.args.get('month', default_month))
    
    # 2. Xử lý phân quyền
    target_user = request.args.get('target_user', user_code)
    if not is_admin and target_user != user_code:
        target_user = user_code 
        
    db = current_app.db_manager
    kpi_service = current_app.kpi_service
    
    # 3. LẤY THÔNG TIN USER 
    user_info = None
    query_user = """
        SELECT USERCODE AS EmployeeID, SHORTNAME AS EmployeeName, [BO PHAN] AS Title 
        FROM [dbo].[GD - NGUOI DUNG] 
        WHERE USERCODE = ?
    """
    user_data = db.get_data(query_user, (target_user,))
    if user_data:
        user_info = user_data[0]
    else:
        user_info = {'EmployeeID': target_user, 'EmployeeName': target_user, 'Title': 'Chưa cập nhật'}

    # 4. LẤY DANH SÁCH NHÂN SỰ (Sort theo USERCODE theo yêu cầu của sếp)
    user_division = session.get('division', '5000')
    query_users = """
        SELECT USERCODE, SHORTNAME, [BO PHAN] as Department 
        FROM [dbo].[GD - NGUOI DUNG] 
        WHERE Division = ? 
        ORDER BY USERCODE ASC  -- Sửa lại ORDER BY để sort theo mã NV
    """
    all_users = db.get_data(query_users, (user_division,))
        
    # 5. [FIXED] LẤY AVATAR TỪ BẢNG TitanOS_UserProfile (Cột sếp đã check trong SSMS)
    target_avatar = f"https://ui-avatars.com/api/?background=random&color=fff&size=128&bold=true&name={target_user}"
    try:
        query_ava = "SELECT AvatarUrl FROM [dbo].[TitanOS_UserProfile] WHERE LTRIM(RTRIM(UserCode)) = ?"
        ava_data = db.get_data(query_ava, (target_user,))
        if ava_data and ava_data[0].get('AvatarUrl'):
            target_avatar = ava_data[0]['AvatarUrl']
    except Exception as e:
        current_app.logger.error(f"Lỗi lấy avatar: {e}")

    # 6. LẤY KẾT QUẢ KPI (Bổ sung đầy đủ cột để HTML render không crash)
    query_results = """
        SELECT 
            R.*, 
            C.CriteriaName, C.CalculationType, C.Unit, C.IsHigherBetter, 
            C.CalculationFormula, -- QUAN TRỌNG: Phải lấy cột này
            C.DataSource,
            P.Weight, 
            P.Threshold_100, P.Threshold_85, P.Threshold_70, 
            P.Threshold_50, P.Threshold_30, P.Threshold_0
        FROM dbo.KPI_MONTHLY_RESULT R
        INNER JOIN dbo.KPI_CRITERIA_MASTER C ON R.CriteriaID = C.CriteriaID
        INNER JOIN dbo.KPI_USER_PROFILE P ON R.UserCode = P.UserCode AND R.CriteriaID = P.CriteriaID
        WHERE R.UserCode = ? AND R.EvalYear = ? AND R.EvalMonth = ?
    """
    kpi_results = db.get_data(query_results, (target_user, selected_year, selected_month))
    
    # 7. Tính tổng điểm
    total_score = sum([safe_float(r.get('WeightedScore', 0)) for r in kpi_results]) if kpi_results else 0
    grade = 'N/A'
    if kpi_results:
        if total_score >= 131: grade = 'SS'
        elif total_score >= 101: grade = 'S'
        elif total_score >= 86: grade = 'A'
        elif total_score >= 76: grade = 'B'
        elif total_score >= 61: grade = 'C'
        else: grade = 'D'

    return render_template(
        'kpi_evaluation.html',
        kpi_results=kpi_results,
        user_info=user_info,
        target_user=target_user,
        target_avatar=target_avatar, # Đã truyền Avatar sang HTML
        selected_year=selected_year,
        selected_month=selected_month,
        is_admin=is_admin,
        all_users=all_users,
        total_score=total_score,
        grade=grade
    )

@kpi_evaluation_bp.route('/api/evaluate', methods=['POST'])
@login_required
def evaluate_kpi():
         
    data = request.json
    target_user = data.get('user_code')
    year = data.get('year')
    month = data.get('month')
    
    if not all([target_user, year, month]):
        return jsonify({'success': False, 'message': 'Thiếu tham số bắt buộc.'}), 400
        
    kpi_service = current_app.kpi_service
    result = kpi_service.evaluate_monthly_kpi(target_user, int(year), int(month))
    
    # --- [THÊM LOG Ở ĐÂY] ---
    if result.get('success'):
        executor = session.get('user_code')
        ip = get_user_ip()
        # SỬA DÒNG NÀY:
        current_app.db_manager.write_audit_log(executor, 'KPI_CALC', 'INFO', f"Chốt điểm KPI cho {target_user} (Tháng {month}/{year})", ip)

    return jsonify(result)

# --- TRONG FILE blueprints/kpi_evaluation_bp.py ---

@kpi_evaluation_bp.route('/manual-scoring', methods=['GET'])
@login_required
def manual_scoring_page():
    """Giao diện dành cho Quản lý chấm điểm tay"""
    user_code = session.get('user_code')
    user_role = str(session.get('user_role', '')).strip().upper()
    is_admin = (user_role == 'ADMIN')
    
    # Mặc định chọn tháng trước
    now = datetime.now()
    year = int(request.args.get('year', now.year))
    month = int(request.args.get('month', now.month))
    
    # 1. Lấy danh sách nhân viên để chấm điểm
    db = current_app.db_manager
    kpi_service = current_app.kpi_service
    
    # Tạm thời Admin thấy hết, Manager thấy phòng ban (nếu cần phân quyền sâu hơn thì làm ở đây)
    query_users = "SELECT USERCODE, SHORTNAME, [BO PHAN] as Department FROM [dbo].[GD - NGUOI DUNG] WHERE [TRANG THAI] = N'Đang làm việc' OR [TRANG THAI] IS NULL ORDER BY [BO PHAN], SHORTNAME"
    all_users = db.get_data(query_users)
    
    target_user = request.args.get('target_user', all_users[0]['USERCODE'] if all_users else user_code)

    # 2. Lấy các tiêu chí cần chấm tay của nhân viên đó
    manual_criteria = kpi_service.get_manual_criteria_for_evaluation(target_user, year, month)

    return render_template(
        'kpi_manual_scoring.html',
        all_users=all_users,
        target_user=target_user,
        selected_year=year,
        selected_month=month,
        manual_criteria=manual_criteria
    )

@kpi_evaluation_bp.route('/api/save-manual-scores', methods=['POST'])
@login_required
def api_save_manual_scores():
    """API lưu kết quả chấm điểm"""
    data = request.json
    target_user = data.get('target_user')
    year = data.get('year')
    month = data.get('month')
    scores_data = data.get('scores', []) # Format: [{'criteria_id': '...', 'actual_value': 8, 'note': '...'}, ...]
    
    if not scores_data:
        return jsonify({'success': False, 'message': 'Không có dữ liệu điểm để lưu.'}), 400
    
    executor = session.get('user_code') # BỔ SUNG DÒNG NÀY (Định nghĩa biến executor)    
    kpi_service = current_app.kpi_service
    result = kpi_service.save_manual_evaluations(target_user, int(year), int(month), scores_data, session.get('user_code'))
    
    # --- [THÊM LOG Ở ĐÂY] ---
    if result.get('success'):
        ip = get_user_ip()
        # SỬA DÒNG NÀY:
        current_app.db_manager.write_audit_log(executor, 'KPI_MANUAL_SCORE', 'INFO', f"Chấm điểm tay cho {target_user} (Tháng {month}/{year}) - {len(scores_data)} tiêu chí", ip)

    return jsonify(result)

@kpi_evaluation_bp.route('/peer-review', methods=['GET'])
@login_required
def peer_review_page():
    """Giao diện Đánh giá chéo 360 độ (S-A-B-C-D)"""
    db = current_app.db_manager
    user_division = session.get('division', '5000') # Lấy division hiện tại của user
    
    # [FIXED]: Lấy danh sách bộ phận lọc theo Division và chuẩn hóa loại trừ (Khác NULL, Khác 9. DU HOC)
    query_deps = """
        SELECT DISTINCT [BO PHAN] as Department 
        FROM [dbo].[GD - NGUOI DUNG] 
        WHERE Division = ? 
          AND [BO PHAN] IS NOT NULL 
          AND REPLACE([BO PHAN], ' ', '') <> '9.DUHOC'
        ORDER BY [BO PHAN]
    """
    deps = db.get_data(query_deps, (user_division,))
    return render_template('kpi_peer_review.html', departments=deps, current_division=user_division)

@kpi_evaluation_bp.route('/api/get-users-by-dept', methods=['GET'])
@login_required
def get_users_by_dept():
    dept = request.args.get('dept')
    user_division = session.get('division', '5000')
    current_user = session.get('user_code')
    
    now = datetime.now()
    year = int(request.args.get('year', now.year))
    month = int(request.args.get('month', now.month))
    
    db = current_app.db_manager
    
    # [FIXED]: Áp dụng chuẩn lọc user: Bộ phận lọc = tham số truyền xuống, kèm quy tắc Division, Not NULL, <> 9.DU HOC
    query = """
        SELECT 
            U.USERCODE, 
            ISNULL(U.USERNAME, U.SHORTNAME) as FullName, 
            U.SHORTNAME, 
            ISNULL(U.[CHUC VU], N'Nhân viên') as JobTitle,
            ISNULL(P.AvatarUrl, 'https://ui-avatars.com/api/?background=random&color=fff&name=' + REPLACE(U.SHORTNAME, ' ', '+')) as AvatarUrl,
            R.Score as EvaluatedScore
        FROM [dbo].[GD - NGUOI DUNG] U
        LEFT JOIN [dbo].[TitanOS_UserProfile] P ON LTRIM(RTRIM(U.USERCODE)) = LTRIM(RTRIM(P.UserCode))
        LEFT JOIN [dbo].[KPI_PEER_REVIEW] R 
            ON LTRIM(RTRIM(U.USERCODE)) = LTRIM(RTRIM(R.TargetUser)) 
            AND LTRIM(RTRIM(R.EvaluatorUser)) = LTRIM(RTRIM(?)) 
            AND R.EvalYear = ? 
            AND R.EvalMonth = ?
        WHERE U.[BO PHAN] = ? 
          AND U.Division = ?
          AND U.[BO PHAN] IS NOT NULL 
          AND REPLACE(U.[BO PHAN], ' ', '') <> '9.DUHOC'
        ORDER BY U.SHORTNAME
    """
    
    
    try:
        users = db.get_data(query, (current_user, year, month, dept, user_division))
        
        # [FIXED]: Xử lý triệt để None, chuỗi rỗng '', hoặc chuỗi không thể ép kiểu
        for u in users:
            score = u.get('EvaluatedScore')
            
            # Nếu là None, hoặc là chuỗi rỗng/chỉ chứa khoảng trắng
            if score is None or str(score).strip() == '':
                u['EvaluatedScore'] = None
            # Nếu là kiểu float nhưng lại là NaN (Not a Number)
            elif isinstance(score, float) and math.isnan(score):
                u['EvaluatedScore'] = None
            else:
                # Ép kiểu an toàn bằng try...except
                try:
                    u['EvaluatedScore'] = float(score)
                except ValueError:
                    u['EvaluatedScore'] = None # Gán về None nếu vướng ký tự lạ không ép được số

        return jsonify(users)
    except Exception as e:
        current_app.logger.error(f"Lỗi lấy danh sách user chấm điểm: {e}")
        return jsonify([])

@kpi_evaluation_bp.route('/api/submit-peer-review', methods=['POST'])
@login_required
def submit_peer_review():
    data = request.json
    now = datetime.now()
    # Mặc định chấm cho tháng hiện tại (hoặc có thể truyền tham số lên)

    # KHAI BÁO CÁC BIẾN TẠI ĐÂY TRƯỚC
    evaluator = session.get('user_code')
    target = data['target_user']
    score = safe_float(data['score'])
    note = data.get('note', '')

    result = current_app.kpi_service.save_peer_review(
        target_user=target,
        evaluator_user=evaluator,
        year=now.year,
        month=now.month,
        score=score,
        note=note
    )

    # --- [THÊM LOG Ở ĐÂY] ---
    if result.get('success'):
        ip = get_user_ip()
        current_app.db_manager.write_audit_log(evaluator, 'KPI_PEER_REVIEW', 'INFO', f"Đánh giá chéo đồng nghiệp {target} - Cho {score} điểm", ip)

    return jsonify(result)

# ==========================================================
# API LẤY CHI TIẾT KPI (DÀNH CHO POPUP MODAL)
# ==========================================================
@kpi_evaluation_bp.route('/api/kpi-detail', methods=['GET'])
@login_required
def api_kpi_detail():
    criteria_id = request.args.get('criteria_id')
    target_user = request.args.get('target_user')
    year = int(request.args.get('year', datetime.now().year))
    month = int(request.args.get('month', datetime.now().month))
    
    # 1. Kiểm tra quyền: Chỉ Admin hoặc chính chủ mới được xem
    user_code = session.get('user_code')
    user_role = str(session.get('user_role', '')).strip().upper()
    if user_role != 'ADMIN' and target_user != user_code:
        return jsonify({"success": False, "message": "Không có quyền truy cập."}), 403

    db = current_app.db_manager
    kpi_service = current_app.kpi_service
    
    # 2. Gọi logic lấy dữ liệu
    try:
        detail_data = kpi_service.get_criteria_detail(criteria_id, target_user, year, month)
        return jsonify({"success": True, "data": detail_data})
    except Exception as e:
        current_app.logger.error(f"Lỗi lấy detail KPI {criteria_id}: {e}")
        return jsonify({"success": False, "message": "Lỗi truy xuất dữ liệu từ server."}), 500
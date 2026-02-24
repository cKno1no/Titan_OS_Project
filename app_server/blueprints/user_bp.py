from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash, current_app
from utils import login_required, permission_required, record_activity, get_user_ip # Thêm record_activity, get_user_ip
import config
import pandas as pd # <--- [THÊM] Import thư viện này để xử lý lỗi ngày tháng
from datetime import datetime, date


user_bp = Blueprint('user_bp', __name__)

def check_admin_access():
    return session.get('user_role', '').strip().upper() == config.ROLE_ADMIN

@user_bp.route('/user_management', methods=['GET'])
@login_required
def user_management_page():
    if not check_admin_access():
        flash("Bạn không có quyền truy cập trang quản trị.", "danger")
        return redirect(url_for('index'))
    return render_template('user_management.html', feature_groups=config.SYSTEM_FEATURES_GROUPS)

# --- API ENDPOINTS ---


@user_bp.route('/api/users/list', methods=['GET'])
@login_required
def api_get_users():
    if not check_admin_access(): return jsonify([]), 403
    user_division = session.get('division')
    users = current_app.user_service.get_all_users(division=user_division)
    
    # --- [ĐOẠN CODE CẦN THÊM ĐỂ SỬA LỖI] ---
    # Chuyển đổi NaT (của Pandas) thành None để jsonify không bị lỗi
    for u in users:
        # Kiểm tra nếu CreatedDate là NaT (Not a Time)
        if 'CreatedDate' in u and pd.isna(u['CreatedDate']):
            u['CreatedDate'] = None
    # ---------------------------------------

    return jsonify(users)

@user_bp.route('/api/users/detail/<string:user_code>', methods=['GET'])
@login_required
def api_get_user_detail(user_code):
    if not check_admin_access(): return jsonify({}), 403
    user = current_app.user_service.get_user_detail(user_code)
    return jsonify(user)

@user_bp.route('/api/users/update', methods=['POST'])
@login_required
def api_update_user():
    if not check_admin_access(): return jsonify({'success': False}), 403
    data = request.json
    success = current_app.user_service.update_user(data)
    return jsonify({'success': success})

@user_bp.route('/api/permissions/matrix', methods=['GET'])
@login_required
def api_get_permissions():
    if not check_admin_access(): return jsonify({}), 403
    roles = current_app.user_service.get_all_roles()
    matrix = current_app.user_service.get_permissions_matrix()
    return jsonify({'roles': roles, 'matrix': matrix})

@user_bp.route('/api/permissions/save', methods=['POST'])
@login_required
def api_save_permissions():
    if not check_admin_access(): return jsonify({'success': False}), 403
    data = request.json
    role_id = data.get('role_id')
    features = data.get('features', [])
    success = current_app.user_service.update_permissions(role_id, features)
    return jsonify({'success': success})

@user_bp.route('/api/user/set_theme', methods=['POST'])
@login_required
def api_set_user_theme():
    data = request.json
    theme = data.get('theme', 'light')
    user_code = session.get('user_code')
    current_app.user_service.update_user_theme_preference(user_code, theme)
    session['theme'] = theme
    return jsonify({'success': True})

@user_bp.route('/api/pet/status', methods=['GET'])
@login_required
def get_pet_status():
    return jsonify({
        'skin': 'iron_man_robot',
        'mood': 'happy',
        'points': 1500
    })

@user_bp.route('/profile')
@login_required
def profile():
    user_code = session.get('user_code')
    user_data = current_app.user_service.get_user_profile(user_code)
    
    if not user_data:
        flash("Không tìm thấy thông tin người dùng.", "danger")
        return redirect(url_for('index'))
    
    # [FIX] Ép kiểu Level để tránh lỗi so sánh template
    try:
        user_data['Level'] = int(user_data.get('Level', 1))
    except:
        user_data['Level'] = 1

    inventory_sql = """
        SELECT 
            T1.*, 
            T2.ItemType, 
            T2.ItemName,
            T2.MinLevel 
        FROM TitanOS_UserInventory T1
        LEFT JOIN TitanOS_SystemItems T2 ON T1.ItemCode = T2.ItemCode
        WHERE T1.UserCode = ? AND T1.IsActive = 1
    """
    inventory = current_app.db_manager.get_data(inventory_sql, (user_code,))
    
    items = current_app.db_manager.get_data(
        "SELECT * FROM TitanOS_SystemItems WHERE IsActive = 1 ORDER BY Price ASC"
    )

    return render_template(
        'user_profile.html', 
        user=user_data,
        inventory=inventory,
        items=items
    )

@user_bp.route('/api/user/buy_item', methods=['POST'])
@login_required
def buy_item():
    user_code = session.get('user_code')
    item_code = request.json.get('item_code')
    result = current_app.user_service.buy_item(user_code, item_code)
    return jsonify(result)

@user_bp.route('/api/user/equip_item', methods=['POST'])
@login_required
def equip_item():
    user_code = session.get('user_code')
    item_code = request.json.get('item_code')
    result = current_app.user_service.equip_item(user_code, item_code)
    if result.get('success') and item_code in ['light', 'dark', 'fantasy', 'adorable']:
        session['theme'] = item_code
        current_app.user_service.update_user_theme_preference(user_code, item_code)
    return jsonify(result)

@user_bp.route('/api/user/upload_avatar', methods=['POST'])
@login_required
def upload_avatar():
    if 'avatar' not in request.files: return jsonify({'success': False, 'message': 'Không có file'})
    file = request.files['avatar']
    if file.filename == '': return jsonify({'success': False, 'message': 'Chưa chọn file'})
    if file:
        result = current_app.user_service.update_avatar(session.get('user_code'), file)
        if result['success']: session['avatar_url'] = result['url']
        return jsonify(result)

@user_bp.route('/api/user/change_password', methods=['POST'])
@login_required
def change_password():
    data = request.json
    result = current_app.user_service.change_password(
        session.get('user_code'), 
        data.get('current_password'), 
        data.get('new_password')
    )
    return jsonify(result)

# =========================================================================
# 3. API MAILBOX (HÒM THƯ) - [ĐÃ FIX LỖI NaT]
# =========================================================================

@user_bp.route('/api/mailbox', methods=['GET'])
@login_required
def get_mailbox():
    """Lấy danh sách thư (Xử lý triệt để lỗi NaN và NaT)."""
    user_code = session.get('user_code')
    db_manager = current_app.db_manager
    
    # Chỉ lấy 20 thư mới nhất để tối ưu tốc độ
    sql = """
        SELECT TOP 20 MailID, Title, Content, Total_XP, Total_Coins, CreatedTime, IsClaimed, ClaimedTime 
        FROM TitanOS_Game_Mailbox 
        WHERE UserCode = ? 
        ORDER BY IsClaimed ASC, CreatedTime DESC
    """
    
    try:
        rows = db_manager.get_data(sql, (user_code,))
        if not rows: return jsonify([])
            
        clean_mails = []
        for row in rows:
            # [BẮT BUỘC] Ép kiểu số để tránh lỗi NaN làm hỏng JSON
            def safe_int(val):
                if val is None or pd.isna(val): return 0
                try: return int(float(val))
                except: return 0

            mail = {
                'MailID': row.get('MailID'),
                'Title': row.get('Title') or "Thông báo",
                'Content': row.get('Content'),
                'Total_XP': safe_int(row.get('Total_XP')),
                'Total_Coins': safe_int(row.get('Total_Coins')),
                'IsClaimed': bool(row.get('IsClaimed')),
                'CreatedTime': row.get('CreatedTime'),
                'ClaimedTime': row.get('ClaimedTime')
            }
            
            # Xử lý ngày tháng NaT/None dùng pd.isna() chuẩn của Pandas
            for date_field in ['CreatedTime', 'ClaimedTime']:
                val = mail[date_field]
                if pd.isna(val) or val is None:
                    mail[date_field] = None
                elif hasattr(val, 'isoformat'):
                    mail[date_field] = val.isoformat()
            
            clean_mails.append(mail)

        return jsonify(clean_mails)
    except Exception as e:
        current_app.logger.error(f"Lỗi lấy hòm thư: {e}")
        return jsonify([]) # Trả về mảng rỗng thay vì lỗi 500


@user_bp.route('/api/mailbox/claim', methods=['POST'])
@login_required
def claim_mail():
    user_code = session.get('user_code')
    mail_id = request.json.get('mail_id')
    
    conn = None
    try:
        conn = current_app.db_manager.get_transaction_connection()
        cursor = conn.cursor()
        
        # [FIXED] Bổ sung thêm cột Title vào câu truy vấn
        cursor.execute("SELECT Total_XP, Total_Coins, Title FROM TitanOS_Game_Mailbox WHERE MailID=? AND UserCode=? AND IsClaimed=0", (mail_id, user_code))
        mail = cursor.fetchone()
        if not mail:
            conn.rollback()
            return jsonify({'success': False, 'msg': 'Thư không tồn tại hoặc đã nhận.'})
            
        xp, coins = mail[0] or 0, mail[1] or 0
        # Định nghĩa biến mail_title
        mail_title = mail[2] or "Hộp thư hệ thống"
        
        cursor.execute("SELECT Level, CurrentXP, TotalCoins FROM TitanOS_UserStats WHERE UserCode=?", (user_code,))
        stats = cursor.fetchone()
        
        if not stats:
            cursor.execute("INSERT INTO TitanOS_UserStats (UserCode, Level, CurrentXP, TotalCoins) VALUES (?, 1, 0, 0)", (user_code,))
            lvl, curr_xp, curr_coins = 1, 0, 0
        else:
            lvl, curr_xp, curr_coins = stats[0], stats[1], stats[2]
            
        new_xp = curr_xp + xp
        new_coins = curr_coins + coins
        new_lvl = lvl
        
        level_up = False
        loop_guard = 0
        while loop_guard < 50:
            cursor.execute("SELECT XP_Required, Coin_Reward FROM TitanOS_Game_Levels WHERE Level=?", (new_lvl,))
            req = cursor.fetchone()
            req_xp = req[0] if req else 999999
            
            if new_xp >= req_xp:
                new_xp -= req_xp
                new_lvl += 1
                new_coins += (req[1] or 0)
                level_up = True
                loop_guard += 1
            else:
                break
                
        cursor.execute("UPDATE TitanOS_UserStats SET Level=?, CurrentXP=?, TotalCoins=? WHERE UserCode=?", (new_lvl, new_xp, new_coins, user_code))
        cursor.execute("UPDATE TitanOS_Game_Mailbox SET IsClaimed=1, ClaimedTime=GETDATE() WHERE MailID=?", (mail_id,))
        
        conn.commit()

        # --- GHI LOG NHẬN THƯỚNG ---
        ip = get_user_ip()
        log_msg = f"Nhận thư '{mail_title}' (+{xp} XP, +{coins} Coins)"
        if level_up:
            log_msg += f" -> Thăng cấp lên Level {new_lvl}!"
            
        # [FIXED] Dùng hàm ghi log chuẩn xác
        current_app.db_manager.write_audit_log(user_code, 'CLAIM_MAILBOX', 'INFO', log_msg, ip)
        
        return jsonify({'success': True, 'level_up': level_up, 'new_level': new_lvl, 'coins_earned': coins})
        
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Lỗi Claim Mail: {e}")
        return jsonify({'success': False, 'msg': str(e)})
    finally:
        if conn: conn.close()

@user_bp.route('/api/user/use_rename_card', methods=['POST'])
@login_required
def api_use_rename_card():
    data = request.json
    new_nickname = data.get('nickname', '').strip()
    
    if not new_nickname:
        return jsonify({'success': False, 'message': 'Tên không được để trống!'})
    if len(new_nickname) > 20:
        return jsonify({'success': False, 'message': 'Tên quá dài (tối đa 20 ký tự).'})

    result = current_app.user_service.use_rename_card(session.get('user_code'), new_nickname)
    
    if result['success']:
        session['user_shortname'] = new_nickname
        
    return jsonify(result)

# Bổ sung vào user_bp.py

@user_bp.route('/admin/audit_logs', methods=['GET'])
@login_required
def audit_logs_dashboard():
    """Giao diện Mắt Thần - Chỉ Admin mới được vào"""
    if session.get('user_role', '').strip().upper() != config.ROLE_ADMIN:
        return jsonify({'error': 'Unauthorized'}), 403
    
    db = current_app.db_manager
    today = date.today().strftime('%Y-%m-%d')
    
    # 1. Lấy 4 chỉ số KPI tổng quan trong ngày (SỬA CreatedAt -> [Timestamp])
    stats = {}
    try:
        stats['total_today'] = db.get_data("SELECT COUNT(1) as Cnt FROM dbo.AUDIT_LOGS WHERE CAST([Timestamp] AS DATE) = ?", (today,))[0]['Cnt']
        
        stats['alerts'] = db.get_data("SELECT COUNT(1) as Cnt FROM dbo.AUDIT_LOGS WHERE CAST([Timestamp] AS DATE) = ? AND Severity IN ('WARNING', 'CRITICAL')", (today,))[0]['Cnt']
        
        stats['failed_logins'] = db.get_data("SELECT COUNT(1) as Cnt FROM dbo.AUDIT_LOGS WHERE CAST([Timestamp] AS DATE) = ? AND ActionType = 'LOGIN_FAILED'", (today,))[0]['Cnt']
        
        stats['active_users'] = db.get_data("SELECT COUNT(DISTINCT UserCode) as Cnt FROM dbo.AUDIT_LOGS WHERE CAST([Timestamp] AS DATE) = ?", (today,))[0]['Cnt']
    except Exception as e:
        current_app.logger.error(f"Lỗi lấy Audit Stats: {e}")
        stats = {'total_today': 0, 'alerts': 0, 'failed_logins': 0, 'active_users': 0}

    return render_template('audit_dashboard.html', stats=stats)


@user_bp.route('/api/admin/logs/stream', methods=['GET'])
@login_required
def api_stream_logs():
    """API Tra cứu Mắt thần - Chế độ Review (Hỗ trợ lọc thời gian)"""
    if session.get('user_role', '').strip().upper() != config.ROLE_ADMIN:
        return jsonify([]), 403
        
    # Nâng limit lên 500 vì sếp xem 2-3 ngày/lần
    limit = int(request.args.get('limit', 500)) 
    severity_filter = request.args.get('severity', '') 
    user_filter = request.args.get('user', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    query = "SELECT TOP (?) LogID, UserCode, ActionType, Severity, Details, IPAddress, [Timestamp] AS CreatedAt FROM dbo.AUDIT_LOGS WHERE 1=1 "
    params = [limit]
    
    if severity_filter:
        query += " AND Severity = ?"
        params.append(severity_filter)
        
    if user_filter:
        query += " AND (UserCode LIKE ? OR Details LIKE ?)"
        params.extend([f"%{user_filter}%", f"%{user_filter}%"])
        
    # Thêm bộ lọc Ngày tháng
    if date_from:
        query += " AND CAST([Timestamp] AS DATE) >= ?"
        params.append(date_from)
    if date_to:
        query += " AND CAST([Timestamp] AS DATE) <= ?"
        params.append(date_to)
        
    query += " ORDER BY [Timestamp] DESC"
    
    logs = current_app.db_manager.get_data(query, tuple(params))
    
    # Chuẩn hóa ngày tháng
    for log in logs:
        if log.get('CreatedAt'):
            log['CreatedAt'] = log['CreatedAt'].strftime('%H:%M:%S %d/%m/%Y')
            
    return jsonify(logs)
# app_server/seed_kpi_profiles.py
from db_manager import DBManager

def seed_kpi_data():
    db = DBManager()
    
    print("🚀 ĐANG DỌN DẸP DỮ LIỆU CŨ...")
    db.execute_non_query("DELETE FROM dbo.KPI_MONTHLY_RESULT")
    db.execute_non_query("DELETE FROM dbo.KPI_USER_PROFILE")
    db.execute_non_query("DELETE FROM dbo.KPI_CRITERIA_MASTER")

    # =====================================================================
    # PHẦN 1: KHỞI TẠO NGÂN HÀNG TIÊU CHÍ (KPI_CRITERIA_MASTER)
    # =====================================================================
    print("⏳ Đang nạp Ngân hàng tiêu chí...")
    criteria_master = [
        # --- KINH DOANH & TKKD ---
        ('KPI_KD_01', 'Tỷ lệ hoàn thành Doanh số Tổng', 'KD', 'AUTO_ERP', 1),
        ('KPI_KD_02', 'Doanh số Khách hàng Mới', 'KD', 'AUTO_ERP', 1),
        ('KPI_KD_03', 'Tỷ lệ Công nợ quá hạn (>180 ngày)', 'KD', 'AUTO_ERP', 0),
        ('KPI_TK_01', 'Tỷ lệ hoàn thành Doanh số hỗ trợ', 'TKKD', 'AUTO_ERP', 1),
        ('KPI_TK_02', 'Doanh số Văn phòng', 'TKKD', 'AUTO_ERP', 1),
        ('KPI_TK_03', 'Tỷ lệ Đơn hàng giao trễ do chứng từ', 'TKKD', 'AUTO_ERP', 0),
        ('KPI_TK_04', 'Tỷ lệ Báo giá thành công', 'TKKD', 'AUTO_ERP', 1),

        # --- KẾ TOÁN ---
        ('KPI_KT_01', 'SLA Phê duyệt / Thanh toán (Giờ)', 'KT', 'AUTO_TITAN', 0),
        ('KPI_KT_02', 'Tỷ lệ kiểm soát Ngân sách (Độ lệch %)', 'KT', 'AUTO_ERP', 0),
        ('KPI_KT_03', 'Lỗi nghiệp vụ toàn phòng', 'KT', 'AUTO_ERP', 0),
        ('KPI_KT_04', 'Tỷ lệ Công nợ quá hạn toàn công ty', 'KT', 'AUTO_ERP', 0),
        ('KPI_KT_05', 'Tỷ lệ giảm Nợ quá hạn', 'KT', 'AUTO_ERP', 1),
        ('KPI_KT_06', 'Tốc độ luân chuyển dòng tiền', 'KT', 'AUTO_ERP', 1),
        ('KPI_KT_07', 'Số lỗi Âm Kho ảo do hạch toán sai', 'KT', 'AUTO_ERP', 0),
        ('KPI_KT_08', 'Số phiếu nhập thiếu Hóa đơn đầu vào', 'KT', 'AUTO_ERP', 0),
        ('KPI_KT_09', 'Tốc độ lập Lệnh (Giờ)', 'KT', 'AUTO_ERP', 0),
        ('KPI_KT_10', 'Độ trễ xuất Hóa đơn > 36h', 'KT', 'AUTO_ERP', 0),
        ('KPI_KT_11', 'Số lượng Hóa đơn Hủy/Sửa', 'KT', 'AUTO_ERP', 0),
        ('KPI_KT_12', 'Tốc độ đối chiếu Thu/Chi', 'KT', 'AUTO_ERP', 0),

        # --- KHO & GIAO NHẬN ---
        ('KPI_KH_01', 'OTIF Tổng Kho', 'KHO', 'AUTO_ERP', 1),
        ('KPI_KH_02', 'Giá trị hàng thất thoát/hư hỏng', 'KHO', 'AUTO_ERP', 0),
        ('KPI_KH_03', 'Kiểm soát Ngân sách vận hành kho', 'KHO', 'AUTO_ERP', 0),
        ('KPI_KH_04', 'Năng suất Soạn hàng (Số Lines)', 'KHO', 'AUTO_WMS', 1),
        ('KPI_KH_05', 'Thời gian chuẩn bị hàng (Leadtime)', 'KHO', 'AUTO_WMS', 0),
        ('KPI_KH_06', 'Tỷ lệ tuân thủ Barcode/App', 'KHO', 'AUTO_WMS', 1),
        ('KPI_KH_07', 'Năng suất Nhập hàng (Số Lines)', 'KHO', 'AUTO_WMS', 1),
        ('KPI_KH_08', 'Thời gian Put-away (Giờ)', 'KHO', 'AUTO_WMS', 0),
        ('KPI_KH_09', 'Tỷ lệ giao đúng hạn (OTIF Tài xế)', 'KHO', 'AUTO_ERP', 1),
        
        # --- HỆ THỐNG TITAN & MANUAL (CHẤM TAY) ---
        ('KPI_SYS_01', 'Chỉ số Hiện diện & Báo cáo CRM', 'ALL', 'AUTO_TITAN', 1),
        ('KPI_SYS_02', 'Tỷ lệ xử lý Task đúng hạn', 'ALL', 'AUTO_TITAN', 1),
        ('KPI_SYS_03', 'Điểm Đào tạo & Gamification (XP)', 'ALL', 'AUTO_TITAN', 1),
        ('KPI_SYS_04', 'Điểm KPI TB của 3 Tổ (Dành cho Sếp)', 'ALL', 'AUTO_TITAN', 1),
        
        ('KPI_MAN_01', 'Điểm Đánh giá chéo / Phối hợp', 'ALL', 'MANUAL', 1),
        ('KPI_MAN_02', 'Lỗi hạch toán cấn trừ / Quỹ TM', 'KT', 'MANUAL', 0),
        ('KPI_MAN_03', 'Độ chính xác tồn kho (Lệch kiểm kê)', 'KHO', 'MANUAL', 0),
        ('KPI_MAN_04', 'Tỷ lệ lưu trữ chứng từ gốc', 'KT', 'MANUAL', 1),
        ('KPI_MAN_05', 'Điểm an toàn & 5S', 'KHO', 'MANUAL', 1),
        ('KPI_MAN_06', 'Lỗi soạn sai hàng / thiếu hàng', 'KHO', 'MANUAL', 0),
        ('KPI_MAN_07', 'Lỗi kiểm nghiệm thu (Bỏ lót NCC)', 'KHO', 'MANUAL', 0),
        ('KPI_MAN_08', 'Tỷ lệ dán tem quy chuẩn', 'KHO', 'MANUAL', 1),
        ('KPI_MAN_09', 'Lỗi hư hỏng lúc vận chuyển', 'KHO', 'MANUAL', 0),
        ('KPI_MAN_10', 'Hiệu suất chuyến (Số KM / PXK)', 'KHO', 'MANUAL', 0),
        ('KPI_MAN_11', 'Tỷ lệ thu hồi chứng từ gốc (48h)', 'KHO', 'MANUAL', 1),
        ('KPI_MAN_12', 'Khiếu nại về thái độ giao hàng', 'KHO', 'MANUAL', 0)
    ]

    insert_master_query = """
        INSERT INTO dbo.KPI_CRITERIA_MASTER (CriteriaID, CriteriaName, DepartmentType, CalculationType, IsHigherBetter)
        VALUES (?, ?, ?, ?, ?)
    """
    for item in criteria_master:
        db.execute_non_query(insert_master_query, item)

    # =====================================================================
    # PHẦN 2: CẤU HÌNH KPI CHO 10 NHÂN SỰ CHỦ CHỐT
    # Mảng Threshold: [Mốc_100, Mốc_85, Mốc_70, Mốc_50, Mốc_30, Mốc_0]
    # =====================================================================
    apply_month = '2026-03'
    
    user_profiles = [
        # 1. NHÓM KINH DOANH (Đại diện: KD010)
        {
            "UserCode": "KD010",
            "Criteria": [
                {"ID": "KPI_KD_01",  "Weight": 0.30, "Thresh": [100, 90, 80, 60, 40, 0]},   # % Doanh số
                {"ID": "KPI_KD_02",  "Weight": 0.15, "Thresh": [50, 40, 30, 20, 10, 0]},    # DS KH mới (Triệu)
                {"ID": "KPI_KD_03",  "Weight": 0.15, "Thresh": [5, 8, 12, 15, 20, 100]},    # Nợ quá hạn (%) -> Càng thấp càng tốt
                {"ID": "KPI_SYS_01", "Weight": 0.10, "Thresh": [10, 8, 6, 4, 2, 0]},        # Báo cáo CRM
                {"ID": "KPI_SYS_02", "Weight": 0.10, "Thresh": [100, 90, 80, 60, 40, 0]},   # % Task
                {"ID": "KPI_SYS_03", "Weight": 0.05, "Thresh": [100, 80, 60, 40, 20, 0]},   # XP Đào tạo
                {"ID": "KPI_MAN_01", "Weight": 0.15, "Thresh": [10, 8, 7, 5, 3, 0]}         # Đánh giá chéo
            ]
        },
        
        # 2. NHÓM THƯ KÝ KINH DOANH (Đại diện: KD011)
        {
            "UserCode": "KD011",
            "Criteria": [
                {"ID": "KPI_TK_01",  "Weight": 0.20, "Thresh": [100, 90, 80, 60, 40, 0]},   # % DS Hỗ trợ
                {"ID": "KPI_TK_02",  "Weight": 0.10, "Thresh": [100, 80, 60, 40, 20, 0]},   # DS Văn phòng
                {"ID": "KPI_TK_03",  "Weight": 0.15, "Thresh": [0, 1, 2, 3, 5, 10]},        # Đơn giao trễ
                {"ID": "KPI_TK_04",  "Weight": 0.10, "Thresh": [70, 60, 50, 40, 30, 0]},    # % BG Thành công
                {"ID": "KPI_SYS_01", "Weight": 0.15, "Thresh": [20, 15, 10, 7, 5, 0]},      # BC Chăm sóc CRM
                {"ID": "KPI_SYS_02", "Weight": 0.10, "Thresh": [100, 90, 80, 60, 40, 0]},   # % Task
                {"ID": "KPI_SYS_03", "Weight": 0.05, "Thresh": [100, 80, 60, 40, 20, 0]},   # XP Đào tạo
                {"ID": "KPI_MAN_01", "Weight": 0.15, "Thresh": [10, 8, 7, 5, 3, 0]}         # Đánh giá chéo
            ]
        },

        # 3.1. KẾ TOÁN TRƯỞNG (Ví dụ: KT_Truong)
        {
            "UserCode": "KT_Truong",
            "Criteria": [
                {"ID": "KPI_KT_01",  "Weight": 0.20, "Thresh": [4, 8, 12, 24, 48, 100]},    # SLA Duyệt (Giờ)
                {"ID": "KPI_SYS_02", "Weight": 0.15, "Thresh": [100, 90, 80, 60, 40, 0]},   # Task/BC đúng hạn
                {"ID": "KPI_KT_02",  "Weight": 0.15, "Thresh": [2, 4, 6, 8, 10, 20]},       # % Lệch Ngân sách
                {"ID": "KPI_KT_03",  "Weight": 0.15, "Thresh": [0, 2, 4, 6, 8, 15]},        # Lỗi toàn phòng
                {"ID": "KPI_KT_04",  "Weight": 0.10, "Thresh": [5, 8, 10, 12, 15, 100]},    # Nợ Q/H toàn cty
                {"ID": "KPI_SYS_03", "Weight": 0.05, "Thresh": [100, 80, 60, 40, 20, 0]},   # XP Đào tạo
                {"ID": "KPI_MAN_01", "Weight": 0.20, "Thresh": [10, 8, 7, 5, 3, 0]}         # Đánh giá 360
            ]
        },

        # 3.2. KẾ TOÁN CÔNG NỢ (Ví dụ: KT_CongNo)
        {
            "UserCode": "KT_CongNo",
            "Criteria": [
                {"ID": "KPI_KT_05",  "Weight": 0.20, "Thresh": [10, 8, 5, 3, 1, 0]},        # Tỷ lệ giảm nợ %
                {"ID": "KPI_KT_06",  "Weight": 0.15, "Thresh": [95, 90, 85, 80, 70, 0]},    # Thu nợ đúng hạn %
                {"ID": "KPI_SYS_01", "Weight": 0.10, "Thresh": [15, 12, 10, 8, 5, 0]},      # Tần suất nhắc nợ CRM
                {"ID": "KPI_SYS_02", "Weight": 0.15, "Thresh": [100, 90, 80, 60, 40, 0]},   # Task / Hồ sơ NH
                {"ID": "KPI_MAN_02", "Weight": 0.15, "Thresh": [0, 1, 2, 3, 4, 5]},         # Lỗi cấn trừ
                {"ID": "KPI_SYS_02", "Weight": 0.05, "Thresh": [100, 90, 80, 60, 40, 0]},   # Task chung
                {"ID": "KPI_SYS_03", "Weight": 0.05, "Thresh": [100, 80, 60, 40, 20, 0]},   # XP Đào tạo
                {"ID": "KPI_MAN_01", "Weight": 0.15, "Thresh": [10, 8, 7, 5, 3, 0]}         # Đánh giá chéo
            ]
        },

        # 3.3. KẾ TOÁN VẬT TƯ / KHO (Ví dụ: KT_VatTu)
        {
            "UserCode": "KT_VatTu",
            "Criteria": [
                {"ID": "KPI_KT_07",  "Weight": 0.20, "Thresh": [0, 1, 3, 5, 8, 15]},        # Lỗi âm kho
                {"ID": "KPI_KT_08",  "Weight": 0.15, "Thresh": [0, 2, 4, 6, 8, 10]},        # Phiếu thiếu HĐ
                {"ID": "KPI_KT_09",  "Weight": 0.10, "Thresh": [1, 2, 4, 8, 12, 24]},       # Tốc độ lập lệnh (Giờ)
                {"ID": "KPI_MAN_03", "Weight": 0.20, "Thresh": [0, 1, 2, 4, 6, 10]},        # Sai lệch kiểm kê
                {"ID": "KPI_SYS_02", "Weight": 0.10, "Thresh": [100, 90, 80, 60, 40, 0]},   # Xử lý BB/Task
                {"ID": "KPI_SYS_03", "Weight": 0.05, "Thresh": [100, 80, 60, 40, 20, 0]},   # XP Đào tạo
                {"ID": "KPI_SYS_02", "Weight": 0.05, "Thresh": [100, 90, 80, 60, 40, 0]},   # Task chung
                {"ID": "KPI_MAN_01", "Weight": 0.15, "Thresh": [10, 8, 7, 5, 3, 0]}         # Đánh giá chéo
            ]
        },

        # 3.4. KẾ TOÁN THU CHI / HÓA ĐƠN (Ví dụ: KT_HoaDon)
        {
            "UserCode": "KT_HoaDon",
            "Criteria": [
                {"ID": "KPI_KT_10",  "Weight": 0.20, "Thresh": [0, 2, 4, 6, 8, 15]},        # Trễ XHĐ > 36h
                {"ID": "KPI_KT_11",  "Weight": 0.15, "Thresh": [0, 1, 2, 4, 6, 10]},        # HĐ Hủy/Sửa
                {"ID": "KPI_KT_12",  "Weight": 0.15, "Thresh": [1, 4, 8, 12, 24, 48]},      # Tốc độ đối chiếu (Giờ)
                {"ID": "KPI_MAN_02", "Weight": 0.15, "Thresh": [0, 1, 2, 3, 4, 5]},         # Lỗi quỹ TM/Bank
                {"ID": "KPI_MAN_04", "Weight": 0.10, "Thresh": [100, 95, 90, 80, 70, 0]},   # Lưu CT gốc
                {"ID": "KPI_SYS_03", "Weight": 0.05, "Thresh": [100, 80, 60, 40, 20, 0]},   # XP Đào tạo
                {"ID": "KPI_SYS_02", "Weight": 0.05, "Thresh": [100, 90, 80, 60, 40, 0]},   # Task
                {"ID": "KPI_MAN_01", "Weight": 0.15, "Thresh": [10, 8, 7, 5, 3, 0]}         # Đánh giá chéo
            ]
        },

        # 4.1. THỦ KHO (Ví dụ: KH_ThuKho)
        {
            "UserCode": "KH_ThuKho",
            "Criteria": [
                {"ID": "KPI_MAN_03", "Weight": 0.20, "Thresh": [0, 1, 2, 4, 6, 10]},        # Lệch kiểm kê
                {"ID": "KPI_KH_01",  "Weight": 0.20, "Thresh": [100, 95, 90, 80, 70, 0]},   # OTIF Tổng
                {"ID": "KPI_KH_02",  "Weight": 0.15, "Thresh": [0, 1, 3, 5, 10, 20]},       # Hàng thất thoát (Trđ)
                {"ID": "KPI_KH_03",  "Weight": 0.10, "Thresh": [0, 2, 4, 6, 10, 20]},       # Vượt NS Kho (%)
                {"ID": "KPI_MAN_05", "Weight": 0.10, "Thresh": [10, 8, 7, 5, 3, 0]},        # 5S
                {"ID": "KPI_SYS_02", "Weight": 0.10, "Thresh": [100, 90, 80, 60, 40, 0]},   # Task
                {"ID": "KPI_SYS_03", "Weight": 0.05, "Thresh": [100, 80, 60, 40, 20, 0]},   # XP Đào tạo
                {"ID": "KPI_SYS_04", "Weight": 0.10, "Thresh": [90, 80, 70, 60, 50, 0]}     # Điểm TB 3 Tổ
            ]
        },

        # 4.2. TỔ XUẤT HÀNG (Ví dụ: KH_Xuat)
        {
            "UserCode": "KH_Xuat",
            "Criteria": [
                {"ID": "KPI_KH_04",  "Weight": 0.20, "Thresh": [500, 400, 300, 200, 100, 0]},# Năng suất Lines
                {"ID": "KPI_KH_05",  "Weight": 0.20, "Thresh": [2, 4, 6, 8, 12, 24]},       # Leadtime (Giờ)
                {"ID": "KPI_KH_06",  "Weight": 0.10, "Thresh": [100, 95, 90, 80, 70, 0]},   # Tuân thủ App
                {"ID": "KPI_MAN_06", "Weight": 0.15, "Thresh": [0, 1, 2, 3, 4, 5]},         # Lỗi soạn sai
                {"ID": "KPI_MAN_05", "Weight": 0.10, "Thresh": [10, 8, 7, 5, 3, 0]},        # 5S & Bảo quản
                {"ID": "KPI_SYS_03", "Weight": 0.05, "Thresh": [100, 80, 60, 40, 20, 0]},   # XP Đào tạo
                {"ID": "KPI_SYS_02", "Weight": 0.05, "Thresh": [100, 90, 80, 60, 40, 0]},   # Task
                {"ID": "KPI_MAN_01", "Weight": 0.15, "Thresh": [10, 8, 7, 5, 3, 0]}         # Đánh giá chéo
            ]
        },

        # 4.3. TỔ NHẬP HÀNG (Ví dụ: KH_Nhap)
        {
            "UserCode": "KH_Nhap",
            "Criteria": [
                {"ID": "KPI_KH_07",  "Weight": 0.20, "Thresh": [500, 400, 300, 200, 100, 0]},# Năng suất Nhập Lines
                {"ID": "KPI_KH_08",  "Weight": 0.15, "Thresh": [4, 8, 12, 24, 48, 72]},     # Put-away (Giờ)
                {"ID": "KPI_MAN_07", "Weight": 0.20, "Thresh": [0, 1, 2, 3, 4, 5]},         # Lỗi lọt NCC
                {"ID": "KPI_MAN_08", "Weight": 0.10, "Thresh": [100, 95, 90, 80, 70, 0]},   # Dán tem chuẩn
                {"ID": "KPI_MAN_05", "Weight": 0.10, "Thresh": [10, 8, 7, 5, 3, 0]},        # 5S
                {"ID": "KPI_SYS_03", "Weight": 0.05, "Thresh": [100, 80, 60, 40, 20, 0]},   # XP Đào tạo
                {"ID": "KPI_SYS_02", "Weight": 0.05, "Thresh": [100, 90, 80, 60, 40, 0]},   # Task
                {"ID": "KPI_MAN_01", "Weight": 0.15, "Thresh": [10, 8, 7, 5, 3, 0]}         # Đánh giá chéo
            ]
        },

        # 4.4. TỔ GIAO HÀNG (Ví dụ: KH_Giao)
        {
            "UserCode": "KH_Giao",
            "Criteria": [
                {"ID": "KPI_KH_09",  "Weight": 0.20, "Thresh": [100, 95, 90, 80, 70, 0]},   # OTIF Tài xế
                {"ID": "KPI_MAN_09", "Weight": 0.20, "Thresh": [0, 1, 2, 3, 4, 5]},         # Hư hỏng VC
                {"ID": "KPI_MAN_10", "Weight": 0.10, "Thresh": [15, 20, 25, 30, 40, 100]},  # Hiệu suất KM/Chuyến
                {"ID": "KPI_MAN_11", "Weight": 0.15, "Thresh": [100, 95, 90, 80, 70, 0]},   # Thu hồi CT gốc
                {"ID": "KPI_MAN_12", "Weight": 0.10, "Thresh": [0, 1, 2, 3, 4, 5]},         # Khiếu nại
                {"ID": "KPI_SYS_02", "Weight": 0.05, "Thresh": [100, 90, 80, 60, 40, 0]},   # Bảo dưỡng/Task
                {"ID": "KPI_SYS_03", "Weight": 0.05, "Thresh": [100, 80, 60, 40, 20, 0]},   # XP Đào tạo
                {"ID": "KPI_MAN_01", "Weight": 0.15, "Thresh": [10, 8, 7, 5, 3, 0]}         # Đánh giá chéo
            ]
        }
    ]

    print("⏳ Bắt đầu nạp cấu hình User...")
    insert_profile_query = """
        INSERT INTO dbo.KPI_USER_PROFILE 
        (UserCode, CriteriaID, Weight, Threshold_100, Threshold_85, Threshold_70, Threshold_50, Threshold_30, Threshold_0, ApplyFromMonth, IsActive)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
    """

    count = 0
    conn = db.get_transaction_connection()
    cursor = conn.cursor()

    try:
        for user in user_profiles:
            for crit in user["Criteria"]:
                t = crit["Thresh"] 
                params = (
                    user["UserCode"], crit["ID"], crit["Weight"], 
                    t[0], t[1], t[2], t[3], t[4], t[5], 
                    apply_month
                )
                cursor.execute(insert_profile_query, params)
                count += 1
        
        conn.commit()
        print(f"✅ HOÀN TẤT! Đã nạp thành công {count} dòng cấu hình KPI vào cơ sở dữ liệu.")
    except Exception as e:
        conn.rollback()
        print(f"❌ LỖI: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    seed_kpi_data()
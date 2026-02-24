
CREATE PROCEDURE [dbo].[sp_KPI_acc_GetMetrics]
    @TranYear INT, 
    @TranMonth INT, 
    @UserCode VARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;

    -- Biến lưu trữ KPIs Kế toán
    DECLARE @ACC_Voucher_Count INT = 0;
    DECLARE @ACC_Overdue_Rate FLOAT = 0;
    DECLARE @CRM_Report_Count INT = 0;
    DECLARE @Task_Score FLOAT = 0;

    -- ==============================================================================
    -- 1. NĂNG SUẤT XỬ LÝ CHỨNG TỪ (Đếm số Phiếu Thu / Phiếu Chi đã hạch toán)
    -- ==============================================================================
    SELECT @ACC_Voucher_Count = COUNT(DISTINCT VoucherNo)
    FROM [OMEGA_STDD].[dbo].[GT9000] WITH (NOLOCK)
    WHERE TranYear = @TranYear AND TranMonth = @TranMonth
      AND EmployeeID = @UserCode -- Hoặc CreateUserID tùy thuộc vào cách bạn lưu người lập phiếu
      AND VoucherTypeID IN ('PT', 'PC', 'BN', 'BC'); -- Các loại chứng từ tiền mặt/ngân hàng

    -- ==============================================================================
    -- 2. HIỆU QUẢ KIỂM SOÁT CÔNG NỢ (Tỷ lệ nợ quá hạn trên tổng nợ của toàn công ty)
    -- Giả định: Kế toán bị đánh giá trên sức khỏe tài chính chung. 
    -- Nếu Kế toán quản lý theo KH riêng, bạn có thể JOIN thêm bảng phân quyền.
    -- ==============================================================================
    DECLARE @Total_Debt DECIMAL(18,2) = 0, @Overdue_Debt DECIMAL(18,2) = 0;
    
    SELECT 
        @Total_Debt = ISNULL(SUM(TotalDebt), 0), 
        @Overdue_Debt = ISNULL(SUM(TotalOverdueDebt), 0) 
    FROM [dbo].[CRM_AR_AGING_SUMMARY] WITH (NOLOCK);
    
    IF @Total_Debt > 0 
        SET @ACC_Overdue_Rate = (@Overdue_Debt / @Total_Debt) * 100;

    -- ==============================================================================
    -- 3. KỶ LUẬT BÁO CÁO CRM & TASK (Giống khối Kinh doanh)
    -- ==============================================================================
    -- A. Báo cáo CRM
    SELECT @CRM_Report_Count = COUNT(*)
    FROM [dbo].[HD_BAO CAO] WITH (NOLOCK)
    WHERE YEAR([NGAY]) = @TranYear AND MONTH([NGAY]) = @TranMonth AND [nguoi] = @UserCode;

    -- B. Task (70% Giao - 30% Tự tạo)
    DECLARE @Assigned_Total INT = 0, @Assigned_Done INT = 0, @Self_Total INT = 0;
    DECLARE @Expected_Self_Tasks INT = 154; 

    SELECT @Assigned_Total = COUNT(*), @Assigned_Done = SUM(CASE WHEN [Status] = 'Completed' THEN 1 ELSE 0 END)
    FROM [dbo].[Task_Master] WITH (NOLOCK)
    WHERE [UserCode] = @UserCode AND YEAR([TaskDate]) = @TranYear AND MONTH([TaskDate]) = @TranMonth
      AND ([CapTren] IS NOT NULL OR [SupervisorCode] IS NOT NULL);

    SELECT @Self_Total = COUNT(*)
    FROM [dbo].[Task_Master] WITH (NOLOCK)
    WHERE [UserCode] = @UserCode AND YEAR([TaskDate]) = @TranYear AND MONTH([TaskDate]) = @TranMonth
      AND [CapTren] IS NULL AND [SupervisorCode] IS NULL;

    DECLARE @Score_70 FLOAT = 70; 
    IF @Assigned_Total > 0 SET @Score_70 = (@Assigned_Done * 1.0 / @Assigned_Total) * 70;
    DECLARE @Score_30 FLOAT = (@Self_Total * 1.0 / @Expected_Self_Tasks) * 30;
    IF @Score_30 > 30 SET @Score_30 = 30;
    SET @Task_Score = @Score_70 + @Score_30;

    -- ==============================================================================
    -- XUẤT KẾT QUẢ ĐỂ PYTHON (SERVICE) BẮT LẤY
    -- ==============================================================================
    SELECT 
        ISNULL(@ACC_Voucher_Count, 0) AS ACC_Voucher_Count, 
        ISNULL(@ACC_Overdue_Rate, 0) AS ACC_Overdue_Rate, 
        ISNULL(@CRM_Report_Count, 0) AS CRM_Report_Count,
        ISNULL(@Task_Score, 0) AS Task_Completion_Rate;
END;

GO

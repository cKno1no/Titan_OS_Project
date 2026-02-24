
CREATE PROCEDURE [dbo].[sp_KPI_whs_GetMetrics]
    @TranYear INT, 
    @TranMonth INT, 
    @UserCode VARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;

    -- Biến lưu trữ KPIs Kho vận
    DECLARE @WHS_Receipt_Count INT = 0;     -- Năng suất Nhập kho
    DECLARE @WHS_Dispatch_Count INT = 0;    -- Năng suất Xuất kho
    DECLARE @Late_Dispatch_Count INT = 0;   -- Lỗi xuất trễ
    DECLARE @CRM_Report_Count INT = 0;
    DECLARE @Task_Score FLOAT = 0;

    -- ==============================================================================
    -- 1. NĂNG SUẤT XUẤT / NHẬP KHO (Đếm số Phiếu trên WT2006)
    -- ==============================================================================
    -- Đếm số Phiếu Nhập Kho (PN)
    SELECT @WHS_Receipt_Count = COUNT(DISTINCT VoucherNo)
    FROM [OMEGA_STDD].[dbo].[WT2006] WITH (NOLOCK)
    WHERE TranYear = @TranYear AND TranMonth = @TranMonth
      AND EmployeeID = @UserCode
      AND VoucherTypeID = 'PN'; 

    -- Đếm số Phiếu Xuất Kho (PX, XK, VC)
    SELECT @WHS_Dispatch_Count = COUNT(DISTINCT VoucherNo)
    FROM [OMEGA_STDD].[dbo].[WT2006] WITH (NOLOCK)
    WHERE TranYear = @TranYear AND TranMonth = @TranMonth
      AND EmployeeID = @UserCode
      AND VoucherTypeID IN ('XK', 'PX', 'VC');

    -- ==============================================================================
    -- 2. CAM KẾT LEADTIME KHO (Số phiếu xuất trễ so với yêu cầu)
    -- ==============================================================================
    SELECT @Late_Dispatch_Count = COUNT(DISTINCT W.VoucherNo)
    FROM [OMEGA_STDD].[dbo].[OT2001] O WITH (NOLOCK)
    INNER JOIN [OMEGA_STDD].[dbo].[OT2002] OD WITH (NOLOCK) ON O.SOrderID = OD.SOrderID
    INNER JOIN [OMEGA_STDD].[dbo].[WT2007] WD WITH (NOLOCK) ON OD.TransactionID = WD.OTransactionID
    INNER JOIN [OMEGA_STDD].[dbo].[WT2006] W WITH (NOLOCK) ON WD.VoucherID = W.VoucherID
    WHERE W.TranYear = @TranYear AND W.TranMonth = @TranMonth
      AND W.VoucherTypeID IN ('XK', 'VC', 'PX')
      AND W.EmployeeID = @UserCode -- Tính lỗi trễ cho người lập phiếu kho
      AND OD.Date01 IS NOT NULL
      AND DATEDIFF(day, OD.Date01, W.VoucherDate) > 3; -- Kho quy định xuất trễ > 3 ngày là phạt

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
        ISNULL(@WHS_Receipt_Count, 0) AS WHS_Receipt_Count, 
        ISNULL(@WHS_Dispatch_Count, 0) AS WHS_Dispatch_Count, 
        ISNULL(@Late_Dispatch_Count, 0) AS WHS_Late_Dispatch_Count,
        ISNULL(@CRM_Report_Count, 0) AS CRM_Report_Count,
        ISNULL(@Task_Score, 0) AS Task_Completion_Rate;
END;

GO
